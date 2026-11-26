"""Tactical Fit Score 0–100: соответствие игрока задаче в тактике клуба.

Это условная оценка помощника, НЕ рейтинг FM27. Каждая оценка
раскладывается на факторы, чтобы было видно, откуда взялось число.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

from pydantic import BaseModel

from .. import reference as ref
from .db import ClubDNA
from .importer import ScoutPlayer
from .values import POSITION_RU, attr_certainty

DISCLAIMER = "Условная оценка помощника, не рейтинг FM27"
MIN_COVERAGE = 0.5  # меньше половины веса профиля без данных — оценку не выдаём

COMPONENT_WEIGHTS = {"attributes": 0.75, "position": 0.15, "age": 0.10}
ATTR_FLOOR, ATTR_CEIL = 6.0, 18.0  # шкала атрибутов FM 1–20: 6 — слабый, 18 — элита


@lru_cache(maxsize=1)
def profiles_data() -> dict:
    with resources.files("fm27_analyst.data").joinpath("role_profiles.json").open(encoding="utf-8") as f:
        return json.load(f)


def profile(pid: str) -> dict:
    for p in profiles_data()["profiles"]:
        if p["id"] == pid:
            return p
    raise KeyError(pid)


def profiles_for(position: str) -> list[dict]:
    return [p for p in profiles_data()["profiles"] if position in p["positions"]]


def formation_slots(formation: str) -> list[tuple[str, str]]:
    f = profiles_data()["formations"]
    return [tuple(x) for x in f.get(formation, f["4-2-3-1"])]


class FitComponent(BaseModel):
    name: str
    score: float  # 0–100
    weight: float
    detail: str


class FitResult(BaseModel):
    player_id: int | None
    profile_id: str
    profile_name: str
    score: int | None  # None — данных недостаточно
    confidence: float  # 0–1
    components: list[FitComponent]
    attribute_rows: list[dict]  # атрибут, значение, вес, вклад
    strengths: list[str]
    weaknesses: list[str]
    notes: list[str]
    disclaimer: str = DISCLAIMER


def effective_weights(prof: dict, dna: ClubDNA) -> tuple[dict[str, float], list[str]]:
    w = {k: float(v) for k, v in prof["weights"].items()}
    notes = []
    mods = profiles_data()["style_modifiers"]
    for style in dna.style:
        m = mods.get(style)
        if not m:
            continue
        add = m["groups"].get(prof["group"])
        if add:
            for k, v in add.items():
                w[k] = w.get(k, 0) + v
            notes.append(f"Стиль «{m['name_ru']}» усиливает: " + ", ".join(ref.attr_ru(k) for k in add))
    for t in dna.preferred_traits:
        if t in w:
            w[t] += 1
    return w, notes


def _foot_level(text: str | None) -> int | None:
    if not text:
        return None
    t = text.strip().lower()
    scale = [
        (("very strong", "очень сильн"), 5), (("fairly strong", "довольно сильн"), 4), (("strong", "сильн"), 4),
        (("reasonable", "средн", "нормальн"), 3), (("very weak", "очень слаб"), 1), (("weak", "слаб"), 2),
    ]
    for keys, lvl in scale:
        if any(k in t for k in keys):
            return lvl
    if t.isdigit():
        return max(1, min(5, int(t) // 4 + 1))
    return None


def position_score(player: ScoutPlayer, wanted: list[str]) -> tuple[float, str] | None:
    if not player.positions:
        return None
    if set(player.positions) & set(wanted):
        return 100.0, "Играет на этой позиции (по выгрузке)"
    adj = profiles_data()["adjacent_positions"]
    for pos in player.positions:
        if set(adj.get(pos, [])) & set(wanted):
            return 65.0, f"Смежная позиция: {POSITION_RU.get(pos, pos)} — потребуется привыкание"
    return 25.0, "Позиция не совпадает — переучивание долгое и рискованное"


def age_score(player: ScoutPlayer, dna: ClubDNA) -> tuple[float, str] | None:
    if player.age is None:
        return None
    s, parts = 70.0, []
    if dna.max_signing_age is not None:
        if player.age <= dna.max_signing_age:
            s, parts = 100.0, [f"возраст {player.age} в рамках политики клуба (до {dna.max_signing_age})"]
        else:
            s, parts = 30.0, [f"возраст {player.age} выше политики клуба (до {dna.max_signing_age})"]
    else:
        s = 100.0 if player.age <= 27 else (75.0 if player.age <= 30 else 45.0)
        parts = [f"возраст {player.age}"]
    if player.potential_stars and player.current_stars:
        gap = player.potential_stars[0] - player.current_stars[1]
        if gap >= 1:
            s = min(100.0, s + 10)
            parts.append("потенциал заметно выше текущего уровня")
    return s, "; ".join(parts)


def tactical_fit(player: ScoutPlayer, profile_id: str, dna: ClubDNA, wanted_positions: list[str] | None = None) -> FitResult:
    prof = profile(profile_id)
    w, notes = effective_weights(prof, dna)
    total_w = sum(w.values())
    rows, present_w, acc, cert_acc = [], 0.0, 0.0, 0.0
    for a, wt in sorted(w.items(), key=lambda kv: -kv[1]):
        r = player.attributes.get(a)
        if r is None:
            rows.append({"attr": a, "name": ref.attr_ru(a), "value": None, "weight": wt, "contribution": None})
            continue
        mid = (r[0] + r[1]) / 2
        present_w += wt
        acc += wt * mid / 20
        cert_acc += wt * attr_certainty(r)
        rows.append({"attr": a, "name": ref.attr_ru(a), "value": f"{r[0]}" if r[0] == r[1] else f"{r[0]}–{r[1]}",
                     "mid": mid, "weight": wt, "contribution": round(wt * mid / 20 / total_w * 100, 1)})
    coverage = present_w / total_w if total_w else 0
    components: list[FitComponent] = []
    if coverage >= MIN_COVERAGE:
        # Среднее ключевых атрибутов по шкале: 6 и ниже → 0, 18 и выше → 100
        mean_attr = acc / present_w * 20
        attr_score = max(0.0, min(100.0, (mean_attr - ATTR_FLOOR) / (ATTR_CEIL - ATTR_FLOOR) * 100))
        # Нога: для вингеров учитываем, на какой фланг смещается игрок
        foot_note = None
        if prof.get("foot") and wanted_positions:
            side = "L" if any(p.endswith("_L") for p in wanted_positions) else ("R" if any(p.endswith("_R") for p in wanted_positions) else None)
            lf, rf = _foot_level(player.foot_left), _foot_level(player.foot_right)
            if side and lf and rf:
                need = (rf if side == "L" else lf) if prof["foot"] == "inverted" else (lf if side == "L" else rf)
                if need >= 4:
                    attr_score = min(100, attr_score + 3)
                    foot_note = "Рабочая нога подходит под задачу (+3)"
                elif need <= 2:
                    attr_score -= 6
                    foot_note = "Нужная для задачи нога слабая (−6)"
        components.append(FitComponent(
            name="Атрибуты под задачу", score=round(attr_score, 1), weight=COMPONENT_WEIGHTS["attributes"],
            detail=f"Взвешенное среднее {len([r for r in rows if r['value']])} ключевых атрибутов = {mean_attr:.1f} из 20 "
            f"(шкала: {ATTR_FLOOR:g} → 0, {ATTR_CEIL:g} → 100)"
            + (f"; {foot_note}" if foot_note else ""),
        ))
    if wanted_positions is None:
        wanted_positions = prof["positions"]
    ps = position_score(player, wanted_positions)
    if ps:
        components.append(FitComponent(name="Позиция", score=ps[0], weight=COMPONENT_WEIGHTS["position"], detail=ps[1]))
    ag = age_score(player, dna)
    if ag:
        components.append(FitComponent(name="Возраст и развитие", score=ag[0], weight=COMPONENT_WEIGHTS["age"], detail=ag[1]))

    present = [r for r in rows if r["value"] is not None]
    strengths = [f"{r['name']} {r['value']}" for r in sorted(present, key=lambda r: -r["mid"]) if r["mid"] >= 14][:4]
    weaknesses = [f"{r['name']} {r['value']}" for r in sorted(present, key=lambda r: r["mid"]) if r["mid"] <= 10 and r["weight"] >= 2][:4]
    missing = [r["name"] for r in rows if r["value"] is None and r["weight"] >= 2]
    if missing:
        notes.append("Нет данных: " + ", ".join(missing[:5]))
    if coverage < MIN_COVERAGE:
        return FitResult(
            player_id=player.id, profile_id=profile_id, profile_name=prof["name_ru"], score=None, confidence=0.0,
            components=components, attribute_rows=rows, strengths=strengths, weaknesses=weaknesses,
            notes=notes + [f"Атрибутов под задачу слишком мало ({coverage:.0%} веса) — оценка не выдаётся"],
        )
    tw = sum(c.weight for c in components)
    score = sum(c.score * c.weight for c in components) / tw
    confidence = round((cert_acc / present_w) * coverage, 2)
    if confidence < 0.6:
        notes.append("Атрибуты известны диапазонами — оценка ориентировочная; поможет отчёт скаута в игре")
    return FitResult(
        player_id=player.id, profile_id=profile_id, profile_name=prof["name_ru"], score=round(score),
        confidence=confidence, components=components, attribute_rows=rows, strengths=strengths,
        weaknesses=weaknesses, notes=notes,
    )


def best_fit(player: ScoutPlayer, dna: ClubDNA, position: str | None = None) -> FitResult | None:
    """Лучший профиль для позиции (или для любой позиции игрока)."""
    positions = [position] if position else (player.positions or [])
    candidates: list[FitResult] = []
    seen = set()
    for pos in positions:
        for prof in profiles_for(pos):
            if prof["id"] in seen:
                continue
            seen.add(prof["id"])
            candidates.append(tactical_fit(player, prof["id"], dna, [pos]))
    scored = [c for c in candidates if c.score is not None]
    if scored:
        return max(scored, key=lambda c: c.score)
    return candidates[0] if candidates else None
