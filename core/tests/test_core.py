from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from fm27_analyst import advisor, demo
from fm27_analyst.engine import Engine
from fm27_analyst.gate import AdviceGate
from fm27_analyst.models import Fatigue, PlayerState, Severity, Signal, TeamStats
from fm27_analyst.reasoner import Reasoner, validate_recommendation
from fm27_analyst.rules import evaluate
from fm27_analyst.storage import SaveStore, list_saves
from fm27_analyst.timeline import Timeline, build_facts

from .conftest import make_snap


# --- модели: невозможные данные отбрасываются ---
def test_shots_on_target_cannot_exceed_shots():
    with pytest.raises(ValidationError):
        TeamStats(shots=2, shots_on_target=3)


def test_possession_must_sum_to_100():
    s = make_snap(10)
    data = s.model_dump()
    data["away"]["stats"]["possession"] = 70
    with pytest.raises(ValidationError):
        type(s).model_validate(data)


def test_attribute_range():
    with pytest.raises(ValidationError):
        PlayerState(name="X", attributes={"pace": 25})


# --- таймлайн ---
def test_minute_and_score_cannot_go_back():
    tl = Timeline()
    tl.add(make_snap(30, goals=(1, 0)))
    with pytest.raises(ValueError):
        tl.add(make_snap(25, goals=(1, 0)))
    with pytest.raises(ValueError):
        tl.add(make_snap(35, goals=(0, 0)))


def test_xg_window_uses_snapshot_15_minutes_back():
    tl = Timeline()
    tl.add(make_snap(30, xg=(0.5, 0.2)))
    tl.add(make_snap(40, xg=(0.6, 0.4)))
    tl.add(make_snap(45, xg=(0.7, 0.9)))
    assert tl.xg_window("us") == pytest.approx(0.2)
    assert tl.xg_window("them") == pytest.approx(0.7)


def test_diff_detects_opponent_formation_change_and_dugout():
    tl = Timeline()
    tl.add(make_snap(55))
    ch = tl.add(make_snap(61, them_formation="4-2-3-1", dugout=["Соперник перешёл на 4-2-3-1"]))
    kinds = {c.kind for c in ch}
    assert "formation_them" in kinds and "dugout" in kinds


def test_facts_skip_low_confidence():
    tl = Timeline()
    s = make_snap(20)
    s.confidence = 0.4
    tl.add(s)
    assert build_facts(tl) == []


def test_facts_do_not_invent_missing_stats():
    tl = Timeline()
    s = make_snap(20)
    s.home.stats.xg = None
    tl.add(s)
    ids = {f.id for f in build_facts(tl)}
    assert "xg@20" not in ids


# --- правила ---
def test_sterile_possession_fires():
    tl = Timeline()
    tl.add(make_snap(40, poss=65, xg=(0.30, 0.2)))
    tl.add(make_snap(57, goals=(0, 1), poss=66, xg=(0.38, 0.9)))
    ids = {s.rule_id for s in evaluate(tl)}
    assert "sterile_possession" in ids


def test_tactic_working_when_leading_and_creating():
    tl = Timeline()
    tl.add(make_snap(40, goals=(1, 0), xg=(0.8, 0.2)))
    tl.add(make_snap(57, goals=(1, 0), xg=(1.4, 0.3)))
    ids = {s.rule_id for s in evaluate(tl)}
    assert "tactic_working" in ids and "sterile_possession" not in ids


def test_injury_is_critical():
    tl = Timeline()
    tl.add(make_snap(30, players=[PlayerState(name="А", position="ЦЗ", injured=True)]))
    sig = [s for s in evaluate(tl) if s.rule_id == "injury"]
    assert sig and sig[0].severity == Severity.CRITICAL


def test_rating_drop_needs_three_points():
    tl = Timeline()
    for m, r in ((55, 6.8), (60, 6.6), (65, 6.4)):
        tl.add(make_snap(m, players=[PlayerState(name="Б", position="ПВ", rating=r)]))
    assert any(s.rule_id == "rating_drop" for s in evaluate(tl))


# --- гейт ---
def _sig(rule, sev=Severity.WARNING, player=None, m=60):
    return Signal(rule_id=rule, severity=sev, title=rule, minute=m, fact_ids=[f"{rule}@{m}"], player=player)


def test_gate_min_gap_and_critical_bypass():
    g = AdviceGate()
    first = g.select([_sig("sterile_possession")], 60)
    g.mark_shown(first, 60)
    assert g.select([_sig("xg_against_surge", m=62)], 62) == []
    crit = g.select([_sig("injury", Severity.CRITICAL, "А", 62)], 62)
    assert crit and crit[0].rule_id == "injury"


def test_gate_keeps_working_tactic():
    g = AdviceGate()
    out = g.select([_sig("tactic_working", Severity.INFO), _sig("xg_against_surge")], 60)
    assert out == []
    out = g.select([_sig("tactic_working", Severity.INFO), _sig("rating_drop", player="Б")], 60)
    assert [s.rule_id for s in out] == ["rating_drop"]


def test_gate_does_not_repeat_rejected():
    g = AdviceGate()
    g.mark_rejected(["sterile_possession"])
    assert g.select([_sig("sterile_possession")], 70) == []


# --- замены ---
def test_substitute_picked_by_line_profile():
    starter = PlayerState(name="Олейник", position="ПВ", fatigue=Fatigue.EXHAUSTED)
    bench = [
        PlayerState(name="Слабый", position="ЛВ", on_pitch=False, attributes={"acceleration": 10, "dribbling": 10}),
        PlayerState(name="Сильный", position="ПВ", on_pitch=False, attributes={"acceleration": 16, "dribbling": 15}),
        PlayerState(name="Защитник", position="ЦЗ", on_pitch=False, attributes={"acceleration": 20}),
    ]
    p, why = advisor.pick_substitute(starter, bench)
    assert p.name == "Сильный"
    assert "Ускорение 16" in why


def test_substitute_missing_bench_asks_for_screenshot():
    starter = PlayerState(name="Олейник", position="ПВ")
    p, why = advisor.pick_substitute(starter, [])
    assert p is None and "скриншот" in why


# --- проверка ответа LLM ---
def test_llm_hallucinations_are_dropped():
    tl = Timeline()
    snap = make_snap(60, poss=65, xg=(0.3, 0.6),
                     bench=[PlayerState(name="Поляков", position="ПВ", on_pitch=False)])
    tl.add(snap)
    facts = build_facts(tl)
    raw = {
        "problem": "Нет моментов",
        "evidence_fact_ids": ["possession@60", "fake@60"],
        "actions": [
            {"text": "ok", "kind": "tactical_tweak", "setting": "exploit_width"},
            {"text": "выдуманная правка", "kind": "tactical_tweak", "setting": "super_attack"},
            {"text": "выдуманный игрок", "kind": "substitution", "setting": "Иванов->Месси"},
            {"text": "выдуманная роль", "kind": "role", "setting": "Теневой нападающий"},
        ],
        "expected_effect": "x",
        "risks": "y",
        "confidence": "medium",
    }
    rec = validate_recommendation(raw, facts, snap, "live")
    assert rec is not None
    assert [a.setting for a in rec.actions] == ["exploit_width"]
    assert rec.evidence_fact_ids == ["possession@60"]


class FakeProvider:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def complete(self, system, user, model, max_tokens):
        self.calls += 1
        assert "FACTS:" in user and "ALLOWED:" in user
        return self.text


def test_reasoner_falls_back_on_bad_json():
    tl = Timeline()
    tl.add(make_snap(40, poss=65, xg=(0.30, 0.2)))
    tl.add(make_snap(57, goals=(0, 1), poss=66, xg=(0.38, 0.9)))
    sigs = evaluate(tl)
    r = Reasoner(FakeProvider("извините, не могу"))
    recs = r.recommend(tl, build_facts(tl), sigs)
    assert recs and recs[0].generated_by == "rules"


def test_reasoner_uses_valid_llm_answer():
    tl = Timeline()
    tl.add(make_snap(40, poss=65, xg=(0.30, 0.2)))
    tl.add(make_snap(57, goals=(0, 1), poss=66, xg=(0.38, 0.9)))
    payload = {"recommendations": [{
        "problem": "Мяч у нас, моментов нет", "evidence_fact_ids": ["possession@57"],
        "actions": [{"text": "Играть шире", "kind": "tactical_tweak", "setting": "exploit_width"}],
        "expected_effect": "Больше атак с флангов", "risks": "Контратаки", "confidence": "medium",
    }]}
    r = Reasoner(FakeProvider("Вот: " + json.dumps(payload, ensure_ascii=False)))
    recs = r.recommend(tl, build_facts(tl), evaluate(tl))
    assert recs[0].generated_by == "llm"


# --- память: сейвы не смешиваются ---
def test_saves_are_isolated(tmp_path):
    a = SaveStore(tmp_path, "Динамо", "Карьера 1")
    b = SaveStore(tmp_path, "Шахтёр", "Карьера 1")
    assert a.path != b.path
    a.start_match("X", "home")
    assert b.matches() == []
    names = {s["club"] for s in list_saves(tmp_path)}
    assert names == {"Динамо", "Шахтёр"}


# --- весь цикл на демо-матче ---
def test_demo_match_end_to_end(tmp_path):
    e = Engine(tmp_path)
    e.open_save("Демо", "s")
    e.start_match("Соперник")
    issued = []
    for s in demo.scenario():
        issued += [(s.minute, r) for r in e.ingest(s).recommendations]
    minutes = [m for m, _ in issued]
    # Не чаще одного «пакета» советов за 5 минут (кроме критичных)
    assert all(b - a >= 5 for a, b in zip(sorted(set(minutes)), sorted(set(minutes))[1:]))
    subs = [(m, r) for m, r in issued if r.actions[0].kind == "substitution"]
    assert subs and subs[0][1].actions[0].setting == "Олейник->Поляков"
    # Каждый совет ссылается на существующие факты и содержит риски
    assert all(r.evidence_fact_ids and r.risks for _, r in issued)
    # Никакой совет не повторяется дословно
    keys = [tuple(a.text for a in r.actions) for _, r in issued]
    assert len(keys) == len(set(keys))


def test_outcome_recorded_after_accept(tmp_path):
    e = Engine(tmp_path)
    e.open_save("Демо", "s")
    e.start_match("Соперник")
    rec_id = None
    for s in demo.scenario():
        r = e.ingest(s)
        if r.recommendations and rec_id is None:
            rec_id = int(r.recommendations[0].id)
            e.feedback(rec_id, "accepted")
    item = next(x for x in e.store.recommendations() if x["recommendation"].id == str(rec_id))
    assert item["outcome"] is not None and item["outcome"]["window"] >= 15
    assert any("принят" in line for line in e.store.memory_lines())
