from __future__ import annotations

import sqlite3
import tempfile
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fm27_analyst.club import demo_data
from fm27_analyst.club.db import ClubDB, ClubDNA
from fm27_analyst.club.director import assess_deal, parse_window_request, transfer_window
from fm27_analyst.club.finance import finance_report
from fm27_analyst.club.importer import import_table
from fm27_analyst.club.opposition import opposition_report
from fm27_analyst.club.youth import youth_report
from fm27_analyst.departments import route
from fm27_analyst.reasoner import Reasoner
from fm27_analyst.season import add_result, demo_season, season_answer, season_report
from fm27_analyst.server import create_app
from fm27_analyst.storage import SaveStore

DNA = ClubDNA(style=["high_fullbacks", "high_press"], transfer_budget=15e6, max_signing_age=27,
              wage_budget_total_week=600e3, game_date=date(2027, 1, 15))


@pytest.fixture
def db():
    c = ClubDB(sqlite3.connect(":memory:"))
    c.save_import(import_table(demo_data.market_export(), "m.html"), "market", "m.html")
    c.save_import(import_table(demo_data.squad_export(), "s1.html", scope="own"), "own", "s1.html", game_date=date(2026, 7, 15))
    c.save_import(import_table(demo_data.squad_export_later(), "s2.html", scope="own"), "own", "s2.html", game_date=date(2027, 1, 15))
    c.save_import(import_table(demo_data.opponent_export(), "o.html", scope="opp:x"), "opp:x", "o.html")
    return c


# --- спортивный директор ---
def test_window_request_from_spec():
    r = parse_window_request("У нас 25 миллионов евро. Необходимо усилить центральную защиту и опорную зону.")
    assert r["budget"] == 25e6 and r["needs"] == [["D_C"], ["DM"]]


def test_window_scenarios_respect_caps(db):
    w = transfer_window(DNA, db.players("own"), db.players("market"), 25e6, [["D_C"], ["DM"]])
    safe, bal, amb = w["scenarios"]
    assert safe["total"] <= 25e6 * 0.7 and bal["total"] <= 25e6
    assert amb["total"] <= 25e6 * 1.3 + 1
    for s in w["scenarios"]:
        for p in s["picks"]:
            assert p["improvement"] >= 3  # каждый выбор реально усиливает позицию
    assert all(not p["risks"] for p in safe["picks"])


def test_window_needs_from_squad_plan(db):
    w = transfer_window(DNA, db.players("own"), db.players("market"))
    assert w["needs_source"] == "по карте состава" and w["needs"]


def test_deal_has_negotiation_and_alternatives(db):
    p = max(db.players("market"), key=lambda x: x.value_mid or 0)
    d = assess_deal(p, DNA, db.players("own"), db.players("market"))
    assert d["negotiation"]["opening"] is None or d["negotiation"]["opening"] < (p.value_low or 0)
    assert d["verdict"] in ("BUY", "WATCH", "AVOID") and d["feasibility"]
    assert any("Интерес других клубов" in f for f in d["feasibility"])  # не выдумываем то, чего нет в данных


# --- финансы ---
def test_finance_report(db):
    f = finance_report(db.players("own"), DNA)
    assert f["payroll_week"] and f["budget_line"].startswith("60%")
    assert all(r["months_left"] <= 18 for r in f["renew"])
    assert "Амортизация трансферов" in f["not_available"]


def test_finance_without_wages():
    c = ClubDB(sqlite3.connect(":memory:"))
    c.save_import(import_table("Name;Position;Age\nA;ST (C);25\n", "x.csv", scope="own"), "own", "x.csv")
    assert "error" in finance_report(c.players("own"), ClubDNA())


# --- молодёжь ---
def test_youth_growth_and_stagnation(db):
    y = youth_report(db.players("own"), DNA, db.attribute_history_full)
    assert y["players"] and all(p["age"] <= 21 for p in y["players"])
    assert any(p["development"].get("months") == 6 for p in y["players"])
    stuck = [p for p in y["players"] if any(f.startswith("Застой") for f in p["flags"])]
    grew = [p for p in y["players"] if p["development"].get("profile_total", 0) > 1]
    assert stuck and grew
    for p in y["players"]:
        assert {"technical", "physical", "mental", "tactical"} <= set(p["plan"]) or "GK" in p["position"]


def test_youth_single_import_says_no_dynamics():
    c = ClubDB(sqlite3.connect(":memory:"))
    c.save_import(import_table(demo_data.squad_export(), "s.html", scope="own"), "own", "s.html")
    y = youth_report(c.players("own"), DNA, c.attribute_history_full)
    assert all("динамики пока нет" in p["development"]["text"] for p in y["players"])


# --- разведка соперника ---
def test_opposition_separates_facts_and_hypotheses(db):
    r = opposition_report("ФК Соперник", db.players("opp:x"), db.players("own"), DNA)
    assert r["facts"] and r["hypotheses"] and r["unknown"]
    assert len(r["lineup_guess"]) == 11
    assert any("Петрук" in h["text"] or "быстр" in h["text"] or "медленн" in h["text"] for h in r["hypotheses"])
    assert "гипотез" in r["note"]


# --- сезон ---
def test_season_report_and_answers():
    st = SaveStore(Path(tempfile.mkdtemp()), "Д", "с")
    demo_season(st)
    add_result(st, "Ручной", "away", 0, 1, game_date="2027-01-10", xg_for=0.8, xg_against=0.9)
    r = season_report(st)
    assert r["total"]["played"] == 19 and len(r["form"]) == 5
    assert r["periods"] and r["points_lost"] and r["by_formation"]
    a = season_answer("Почему команда теряет очки?", r)
    assert a["short"] == r["points_lost"][0]["text"] + "."


def test_empty_season():
    st = SaveStore(Path(tempfile.mkdtemp()), "Д", "с")
    assert "error" in season_report(st)


# --- оркестратор ---
@pytest.mark.parametrize("q,dep", [
    ("У нас 25 миллионов евро. Усилить центральную защиту", "sporting_director"),
    ("Почему команда теряет очки?", "season"),
    ("Кому продлить контракт?", "finance"),
    ("Кто из молодых готов к основе?", "youth"),
    ("Как нейтрализовать соперника?", "opposition"),
    ("Найди нападающего до 25 лет", "chief_scout"),
    ("Какие слабые позиции в составе?", "squad_planner"),
])
def test_routing(q, dep):
    assert route(q, live=False) == dep


def test_live_questions_go_to_match_only_during_match():
    assert route("Что сейчас с нашей тактикой?", live=True) == "live_analyst"
    assert route("Что сейчас с нашей тактикой?", live=False) != "live_analyst"


def test_api_dashboard_and_conclusion(tmp_path):
    c = TestClient(create_app(tmp_path, Reasoner(None)))
    assert len(c.get("/api/department/dashboard").json()) == 9  # все отделы, даже без сейва
    c.post("/api/saves", json={"club": "Д", "save_name": "К"})
    c.post("/api/club/demo-import")
    c.post("/api/season/demo")
    dash = c.get("/api/department/dashboard").json()
    assert {d["id"] for d in dash} == {"head_coach", "live_analyst", "chief_scout", "opposition", "sporting_director",
                                        "squad_planner", "youth", "finance", "season"}
    pid = c.post("/api/scout/search", json={"query": "центральный защитник"}).json()["hits"][0]["id"]
    r = c.get(f"/api/department/player/{pid}").json()
    assert r["verdict"] in ("BUY", "WATCH", "AVOID")
    assert {o["dept"] for o in r["opinions"]} >= {"Главный скаут", "Главный тренер", "Спортивный директор", "Аналитик данных"}
    w = c.post("/api/director/window", json={"query": "У нас 25 миллионов, усилить центральную защиту и опорную зону"}).json()
    assert len(w["scenarios"]) == 3 and w["understood"]
    opp = c.get("/api/opposition/list").json()
    assert c.get("/api/opposition/report", params={"scope": opp[0]["scope"]}).status_code == 200
    assert c.post("/api/season/result", json={"opponent": "X", "goals_for": 2, "goals_against": 0}).status_code == 200
    assert c.get("/api/season/report").json()["total"]["played"] == 19
    ans = c.post("/api/department/ask", json={"question": "Кому продлить контракт?"}).json()
    assert ans["department"] == "finance" and ans["short"]


def test_balanced_scenario_respects_age_policy(db):
    w = transfer_window(DNA, db.players("own"), db.players("market"), 25e6, [["D_C"], ["DM"]])
    bal = w["scenarios"][1]
    assert all("старше возрастной политики" not in p["risks"] for p in bal["picks"])


def test_youth_focus_is_on_weaknesses(db):
    y = youth_report(db.players("own"), DNA, db.attribute_history_full)
    import re
    for p in y["players"]:
        for g in ("technical", "physical", "mental"):
            for item in p["plan"].get(g, {}).get("focus", []):
                m = re.search(r"\((\d+)\)", item)
                assert m is None or int(m.group(1)) < 14
