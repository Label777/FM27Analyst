from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from fm27_analyst.bridge.gamedate import find_game_date, parse_date
from fm27_analyst.bridge.state import suggest_scope
from fm27_analyst.reasoner import Reasoner
from fm27_analyst.server import create_app

HEADERS = ["Имя", "Возраст", "Позиция", "Клуб", "Стоимость", "Дриблинг", "Навесы", "Опека"]
ROWS = [
    ["Иван Петров", "22", "З (П), ПЗ (П)", "Динамо", "1,5 млн €", "12", "14", "9-11"],
    ["Олег Сидоров", "29", "Н (Ц)", "Динамо", "3 млн €", "15", "8", "5"],
]


def client(tmp_path):
    return TestClient(create_app(tmp_path, Reasoner(None)))


def plugin_online(c):
    assert c.post("/api/bridge/hello", json={"plugin_version": "0.1.0", "game_version": "27.1.0"}).json()["ok"]
    assert c.get("/api/bridge/poll").json() == {"commands": [], "auto_screen": False, "auto_interval_sec": 3.0}


def test_parse_dates_ru_en():
    assert parse_date("Чт 26 ноя 2026") == date(2026, 11, 26)
    assert parse_date("26 ноября 2026 г.") == date(2026, 11, 26)
    assert parse_date("1 мая 2027") == date(2027, 5, 1)
    assert parse_date("Thu 26 Nov 2026") == date(2026, 11, 26)
    assert parse_date("November 26, 2026") == date(2026, 11, 26)
    assert parse_date("26.11.2026") == date(2026, 11, 26)
    assert parse_date("31.02.2026") is None          # несуществующая дата
    assert parse_date("Счёт 2 - 1, 67'") is None
    assert parse_date("Контракт до 30.06.1900") is None  # вне разумного диапазона
    assert find_game_date(["Продолжить", "Ср 15 июл 2026", "30.06.2028"]) == (date(2026, 7, 15), "Ср 15 июл 2026")


def test_scope_suggestion_is_only_a_hint():
    assert suggest_scope("Player Search") == "market"
    assert suggest_scope("Shortlist") == "market"
    assert suggest_scope("Squad") == "own"
    assert suggest_scope("Match") is None


def test_request_needs_game_online(tmp_path):
    c = client(tmp_path)
    r = c.post("/api/bridge/request", json={"type": "grab_table"})
    assert r.status_code == 409 and "FM27" in r.json()["detail"]
    assert c.get("/api/bridge/status").json()["online"] is False


def test_grab_table_import_with_game_date(tmp_path):
    c = client(tmp_path)
    c.post("/api/saves", json={"club": "Динамо", "save_name": "Карьера"})
    plugin_online(c)
    st = c.get("/api/bridge/status").json()
    assert st["online"] and st["plugin"]["game_version"] == "27.1.0"

    cmd = c.post("/api/bridge/request", json={"type": "grab_table"}).json()
    again = c.post("/api/bridge/request", json={"type": "grab_table"}).json()
    assert again["id"] == cmd["id"]  # двойной клик не плодит команды
    poll = c.get("/api/bridge/poll").json()
    assert poll["commands"] == [{"id": cmd["id"], "type": "grab_table"}]
    assert c.get("/api/bridge/poll").json()["commands"] == []
    assert c.get(f"/api/bridge/command/{cmd['id']}").json()["status"] == "sent"

    c.post("/api/bridge/table", json={
        "command_id": cmd["id"], "screen": "Squad", "headers": HEADERS, "rows": ROWS,
        "expected_rows": 2, "context_texts": ["Динамо", "Чт 26 ноя 2026", "Продолжить"],
    })
    assert c.get(f"/api/bridge/command/{cmd['id']}").json()["status"] == "done"
    st = c.get("/api/bridge/status").json()
    assert st["game_date"] == "2026-11-26"
    assert st["last_table"]["suggested_scope"] == "own" and st["last_table"]["row_count"] == 2
    assert "rows" not in st["last_table"] and len(st["last_table"]["preview"]) == 2

    imp = c.post("/api/bridge/import", json={"scope": "own"}).json()
    assert imp["rows"] == 2 and imp["added"] == 2 and imp["game_date"] == "2026-11-26"
    players = c.get("/api/club/players", params={"scope": "own"}).json()
    names = {p["name"] for p in players}
    assert names == {"Иван Петров", "Олег Сидоров"}
    assert all(p["source"] == "game:Squad" for p in players)
    from fm27_analyst.club.db import ClubDB

    db = ClubDB(c.app.state.engine.store.db)
    ivan = next(p for p in db.players("own") if p.name == "Иван Петров")
    assert tuple(ivan.attributes["marking"]) == (9, 11)  # диапазон из игры не «округляем»
    assert db.attribute_history_full(ivan.key)[-1]["game_date"] == date(2026, 11, 26)
    assert c.get("/api/club/dna").json()["game_date"] == "2026-11-26"


def test_opponent_import_needs_name_and_fails_without_save(tmp_path):
    c = client(tmp_path)
    plugin_online(c)
    c.post("/api/bridge/table", json={"screen": "Squad", "headers": HEADERS, "rows": ROWS})
    assert c.post("/api/bridge/import", json={"scope": "own"}).status_code == 409
    c.post("/api/saves", json={"club": "Динамо", "save_name": "Карьера"})
    assert c.post("/api/bridge/import", json={"scope": "opp"}).status_code == 422
    r = c.post("/api/bridge/import", json={"scope": "opp", "opponent": "Шахтёр"}).json()
    assert r["scope"].startswith("opp:") and r["rows"] == 2
    assert any("дата" in n.lower() for n in r["notes"])  # даты не было — честно говорим
    assert any(o["name"] == "Шахтёр" for o in c.get("/api/opposition/list").json())


def test_table_without_names_is_rejected(tmp_path):
    c = client(tmp_path)
    c.post("/api/saves", json={"club": "Динамо", "save_name": "Карьера"})
    plugin_online(c)
    c.post("/api/bridge/table", json={"screen": "Fixtures", "headers": ["Дата", "Соперник"], "rows": [["1.08", "Шахтёр"]]})
    r = c.post("/api/bridge/import", json={"scope": "market"})
    assert r.status_code == 422 and "имен" in r.json()["detail"].lower()


def test_auto_screen_and_dumps(tmp_path):
    c = client(tmp_path)
    plugin_online(c)
    c.post("/api/bridge/auto", json={"enabled": True, "interval_sec": 0.2})
    poll = c.get("/api/bridge/poll").json()
    assert poll["auto_screen"] is True and poll["auto_interval_sec"] == 1.0
    with c.websocket_connect("/ws") as ws:
        ws.receive_json()
        c.post("/api/bridge/screen", json={
            "auto": True, "screen": "Match", "hash": "abc",
            "texts": [{"t": "Пт 27 ноя 2026", "path": "#Header", "x": 1, "y": 1, "w": 10, "h": 10},
                      {"t": "2 - 1", "path": "#Score", "x": 400, "y": 20, "w": 40, "h": 20}],
        })
        ev = ws.receive_json()
        assert ev["type"] == "bridge_screen" and ev["data"]["text_count"] == 2
    assert c.get("/api/bridge/status").json()["game_date"] == "2026-11-27"
    assert c.get("/api/bridge/screen/last").json()["texts"][1]["t"] == "2 - 1"
    dumps = list((tmp_path / "bridge_dumps").glob("*-screen-*.json"))
    assert len(dumps) == 1


def test_plugin_error_result_marks_command(tmp_path):
    c = client(tmp_path)
    plugin_online(c)
    cmd = c.post("/api/bridge/request", json={"type": "grab_table"}).json()
    c.get("/api/bridge/poll")
    c.post("/api/bridge/result", json={"command_id": cmd["id"], "ok": False, "message": "На экране нет таблицы."})
    got = c.get(f"/api/bridge/command/{cmd['id']}").json()
    assert got["status"] == "failed" and "нет таблицы" in got["message"]


def test_real_fm27_squad_overview_headers(tmp_path):
    """Заголовки вида «Обзор» состава из настоящей FM27 Demo 27.1.1 (русский интерфейс)."""
    from fm27_analyst.club.importer import import_rows

    header = ["Выбран", "Инф", "Имя", "Позиции", "Сост", "Гот", "Нас", "Довольство временем в игре",
              "Форма", "Игры", "Гол", "ГПас", "Сред.", "Жк", "Кк"]
    row = ["", "", "Иван Петров", "З (П)", "95%", "Высокая", "Хорошее", "Доволен", "WWDLW", "8", "1", "2", "7.05", "1", "-"]
    res = import_rows([header, row], "game:Squad", scope="own", kind="game")
    assert res.unmapped == []
    p = res.players[0]
    assert p.positions and p.position_raw == "З (П)"
    assert p.status["condition"] == "95%" and p.status["avg_rating"] == "7.05" and "red" not in p.status
    assert "Выбран" not in res.mapped and "Инф" not in res.mapped
    assert any("атрибут" in w for w in res.warnings)
