from __future__ import annotations

import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from fm27_analyst.club import demo_data
from fm27_analyst.club.db import ClubDB, ClubDNA
from fm27_analyst.club.fit import best_fit, tactical_fit
from fm27_analyst.club.importer import import_table
from fm27_analyst.club.report import grade_player, scouting_report, wonderkids
from fm27_analyst.club.search import parse_query, run_search
from fm27_analyst.club.squad import squad_plan
from fm27_analyst.club.values import parse_attr, parse_money, parse_positions, parse_stars
from fm27_analyst.reasoner import Reasoner
from fm27_analyst.server import create_app


# --- разбор значений ---
@pytest.mark.parametrize("raw,exp", [("14", (14, 14)), ("9-11", (9, 11)), ("11 – 9", (9, 11)), ("-", None), ("25", None), ("", None)])
def test_parse_attr(raw, exp):
    assert parse_attr(raw) == exp


def test_parse_money_variants():
    assert parse_money("€15M")["low"] == 15e6
    m = parse_money("€10M - €14M")
    assert (m["low"], m["high"]) == (10e6, 14e6)
    w = parse_money("€1.2K p/w")
    assert w["low"] == 1200 and w["per"] == "week"
    assert parse_money("15 млн €")["low"] == 15e6
    assert parse_money("Not for Sale") is None


def test_parse_positions_en_and_ru():
    assert parse_positions("D (RC), DM") == {"D_R", "D_C", "DM"}
    assert parse_positions("M/AM (L)") == {"M_L", "AM_L"}
    assert parse_positions("ST (C)") == {"ST"}
    assert parse_positions("АП (Л)") == {"AM_L"}


def test_parse_stars_range():
    assert parse_stars("3.0-4.0") == (3.0, 4.0)
    assert parse_stars("4,5") == (4.5, 4.5)


# --- импорт ---
def test_csv_semicolon_with_ambiguous_headers():
    csv_text = "Name;Position;Age;Nat;Pos;Acc;Dri;Transfer Value\nИван Тест;AM (L);19;UKR;12;15;14-16;€2M\n"
    res = import_table(csv_text, "export.csv")
    p = res.players[0]
    assert res.mapped["Nat"] == "nationality"  # текст → гражданство
    assert res.mapped["Pos"] == "attr:positioning"  # числа → выбор позиции
    assert p.attributes["dribbling"] == (14, 16) and p.value_low == 2e6 and p.positions == ["AM_L"]


def test_import_warns_without_attributes():
    res = import_table("Name,Age\nA,20\n", "x.csv")
    assert res.players and any("Ctrl+F8" in w for w in res.warnings)


def test_import_without_name_column_fails_clearly():
    res = import_table("Foo,Bar\n1,2\n", "x.csv")
    assert not res.players and "имен" in res.warnings[0]


@pytest.fixture
def db():
    c = ClubDB(sqlite3.connect(":memory:"))
    c.save_import(import_table(demo_data.market_export(), "m.html"), "market", "m.html")
    c.save_import(import_table(demo_data.squad_export(), "s.html", scope="own"), "own", "s.html")
    return c


DNA = ClubDNA(style=["high_fullbacks", "high_press"], transfer_budget=15e6, game_date=date(2026, 7, 15))


# --- Tactical Fit ---
def test_fit_is_explained_and_labelled(db):
    p = next(x for x in db.players("market") if "D_C" in x.positions)
    fr = tactical_fit(p, "cb_stopper", DNA, ["D_C"])
    assert fr.score is not None and 0 <= fr.score <= 100
    assert {c.name for c in fr.components} >= {"Атрибуты под задачу", "Позиция"}
    assert "не рейтинг FM27" in fr.disclaimer
    assert any("высокие крайние защитники" in n for n in fr.notes)  # стиль влияет и это видно


def test_fit_refuses_without_data():
    res = import_table("Name;Position;Acc\nX;ST (C);15\n", "x.csv")
    fr = tactical_fit(res.players[0], "st_poacher", ClubDNA(), ["ST"])
    assert fr.score is None and any("слишком мало" in n for n in fr.notes)


def test_ranges_lower_confidence():
    exact = import_table("Name;Position;Fin;OtB;Ant;Cmp;Acc\nA;ST (C);15;15;15;15;15\n", "a.csv").players[0]
    ranged = import_table("Name;Position;Fin;OtB;Ant;Cmp;Acc\nB;ST (C);13-17;13-17;13-17;13-17;13-17\n", "b.csv").players[0]
    a, b = best_fit(exact, ClubDNA(), "ST"), best_fit(ranged, ClubDNA(), "ST")
    assert a.score == b.score and b.confidence < a.confidence


# --- поиск по запросу ---
def test_query_from_spec():
    f, und = parse_query("Найди мне молодого левого вингера до 21 года, с хорошим дриблингом, ускорением "
                         "и потенциалом для игры в АПЛ. Бюджет 15 миллионов")
    assert set(f.positions) == {"AM_L", "M_L"} and f.age_max == 21 and f.max_value == 15e6
    assert set(f.min_attrs) == {"dribbling", "acceleration"} and f.min_potential_stars == 4.0
    assert any("АПЛ" in u for u in und)  # трактовка показана пользователю


def test_search_respects_filters(db):
    f, _ = parse_query("левый вингер до 23 лет, бюджет 20 млн")
    hits = run_search(db.players("market"), f, DNA)
    assert hits
    for h in hits:
        assert h.player.age <= 23 and set(h.player.positions) & {"AM_L", "M_L"}
        assert h.player.value_low is None or h.player.value_low <= 20e6
    scores = [h.fit.score for h in hits if h.fit and h.fit.score is not None]
    assert scores == sorted(scores, reverse=True)


def test_free_agents_and_expiring(db):
    f, _ = parse_query("свободные агенты")
    assert all(h.player.is_free_agent() for h in run_search(db.players("market"), f, DNA))
    f, _ = parse_query("игроки с истекающим контрактом")
    for h in run_search(db.players("market"), f, DNA):
        assert h.player.contract_until <= date(2027, 7, 15)


# --- отчёт и вердикт ---
def test_report_has_ten_sections_and_source(db):
    p = db.players("market")[3]
    rep = scouting_report(p, DNA, db.players("own"), db.players("market"))
    assert [s["n"] for s in rep["sections"]] == list(range(1, 11))
    assert "m.html" in rep["disclaimer"]
    assert rep["grade"] in {"Elite Signing", "Excellent Signing", "Good Signing", "Risky Signing", "Not Recommended"}
    assert rep["verdict"] in {"BUY", "WATCH", "AVOID"}


def test_over_budget_never_buy(db):
    rich = [p for p in db.players("market") if p.value_low and p.value_low > 15e6]
    for p in rich:
        assert scouting_report(p, DNA, db.players("own"), db.players("market"))["verdict"] != "BUY"


def test_low_data_is_risky_not_elite():
    g, v, why = grade_player(import_table("Name\nA\n", "a.csv").players[0], None, None, {}, [], ClubDNA())
    assert g == "Risky Signing" and v == "WATCH"


# --- состав ---
def test_squad_plan_flags_weak_centre_back(db):
    plan = squad_plan(db.players("own"), DNA)
    assert plan["priorities"] and "Центральный защитник" in plan["priorities"][0]
    gk = next(s for s in plan["slots"] if s["code"] == "GK")
    assert gk["starters"]  # вратари оцениваются по вратарским атрибутам


def test_wonderkids_only_young(db):
    wk = wonderkids(db.players("market"), DNA)
    ages = [p["age"] for c in wk["categories"] for p in c["players"]]
    assert ages and max(ages) <= 21


# --- API ---
def test_club_api_flow(tmp_path):
    c = TestClient(create_app(tmp_path, Reasoner(None)))
    assert c.post("/api/club/demo-import").status_code == 409  # нет сейва
    c.post("/api/saves", json={"club": "Динамо", "save_name": "К"})
    assert c.post("/api/club/demo-import").status_code == 200
    r = c.post("/api/scout/search", json={"query": "центральный защитник до 25 лет"}).json()
    assert r["parsed_by"] == "rules" and r["hits"]
    pid = r["hits"][0]["id"]
    assert len(c.get(f"/api/scout/report/{pid}").json()["sections"]) == 10
    ids = [h["id"] for h in r["hits"][:2]]
    assert c.post("/api/scout/compare", json={"ids": ids}).json()["answer"]
    assert c.get("/api/squad/plan").json()["priorities"]
    dna = c.get("/api/club/dna").json()
    dna["formation"] = "4-3-3"
    assert c.put("/api/club/dna", json=dna).json()["formation"] == "4-3-3"
    assert c.get("/api/squad/plan").json()["formation"] == "4-3-3"
    # сейвы не смешиваются
    c.post("/api/saves", json={"club": "Шахтёр", "save_name": "К"})
    assert c.get("/api/club/players?scope=own").json() == []


def test_each_player_starts_once(db):
    plan = squad_plan(db.players("own"), DNA)
    names = [x["name"] for s in plan["slots"] for x in s["starters"]]
    assert len(names) == len(set(names))
    starters = set(names)
    for s in plan["slots"]:
        for r in (s["second"], s["backup"]):
            assert r is None or r["name"] not in starters


def test_compare_explains_close_call(db):
    from fm27_analyst.club.report import compare
    f, _ = parse_query("левый вингер до 23 лет")
    hits = run_search(db.players("market"), f, DNA)
    res = compare([h.player for h in hits[:2]], DNA, db.players("own"), db.players("market"))
    assert res["answer"] and "разница минимальна" not in res["answer"]
