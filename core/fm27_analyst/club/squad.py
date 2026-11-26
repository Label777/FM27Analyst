"""Планировщик состава (раздел 19): глубина по позициям схемы и приоритеты окна."""

from __future__ import annotations

from collections import Counter

from .db import ClubDNA
from .fit import DISCLAIMER, best_fit, formation_slots
from .importer import ScoutPlayer
from .report import VERDICT_RU, own_player_verdict
from .values import POSITION_RU

LEVEL_GAP = 12  # насколько основной может отставать от медианы основы

NEED_RU = {"critical": "критично", "high": "высокая", "medium": "средняя", "none": "нет", "unknown": "нет данных"}


def squad_plan(own: list[ScoutPlayer], dna: ClubDNA) -> dict:
    slots = formation_slots(dna.formation)
    need_count = Counter(code for code, _ in slots)
    out_slots = []
    ranks: dict[str, int] = {}  # лучший ранг игрока по позициям схемы
    unique = list(dict.fromkeys(slots))  # уникальные позиции в порядке схемы
    per_slot: dict[str, tuple[list[dict], list[str]]] = {}
    for code, _label in unique:
        ranked, no_data = [], []
        for p in own:
            fr = best_fit(p, dna, code)
            if fr is None:
                continue
            if fr.score is None:
                if code in p.positions:
                    no_data.append(p.name)  # игрок есть, но атрибутов под задачу в выгрузке нет
                continue
            pos_comp = next((c for c in fr.components if c.name == "Позиция"), None)
            if pos_comp and pos_comp.score < 65:
                continue  # не его позиция
            ranked.append({"id": p.id, "name": p.name, "age": p.age, "fit": fr.score, "profile": fr.profile_name,
                           "confidence": fr.confidence, "natural": bool(pos_comp and pos_comp.score == 100)})
        ranked.sort(key=lambda r: -r["fit"])
        per_slot[code] = (ranked, no_data)

    # Основа: каждый игрок стартует только на одной позиции. Жадно — сначала самые сильные пары.
    pairs = sorted(((r["fit"], code, r) for code, (ranked, _) in per_slot.items() for r in ranked),
                   key=lambda x: -x[0])
    assigned: dict[str, list[dict]] = {code: [] for code in per_slot}
    starting: set[int | None] = set()
    for _fit, code, r in pairs:
        if r["id"] in starting or len(assigned[code]) >= need_count[code]:
            continue
        assigned[code].append(r)
        starting.add(r["id"])

    for code, label in unique:
        n = need_count[code]
        ranked, no_data = per_slot[code]
        starters = sorted(assigned[code], key=lambda r: -r["fit"])
        others = [r for r in ranked if r["id"] not in starting]
        second = others[0] if others else None
        backup = others[1] if len(others) > 1 else None
        youth = next((r for r in others[2:] if r["age"] is not None and r["age"] <= 21), None)
        for r in starters:
            ranks[r["name"]] = 0
        for i, r in enumerate(others[:2], 1):
            ranks[r["name"]] = min(ranks.get(r["name"], 99), i)
        reasons, level = [], "none"
        if not starters and no_data:
            level = "unknown"
            reasons = [f"игроки есть ({', '.join(no_data[:3])}), но в выгрузке нет нужных атрибутов — оценить нельзя"]
        elif not starters:
            level, reasons = "critical", ["нет ни одного игрока на позицию"]
        else:
            weakest = min(s["fit"] for s in starters)
            if weakest < 55:
                level = "critical"
                reasons.append(f"основной игрок не соответствует уровню задачи ({weakest}/100)")
            if second is None:
                level = "high" if level == "none" else level
                reasons.append("нет замены основному")
            elif weakest - second["fit"] >= 15:
                level = "high" if level == "none" else level
                reasons.append(f"замена заметно слабее ({second['fit']} против {weakest})")
            old = [s for s in starters if s["age"] is not None and s["age"] >= 32]
            if old:
                level = "high" if level == "none" else level
                reasons.append(f"основному {old[0]['age']} — нужна смена")
            if backup is None and level == "none":
                level, reasons = "medium", reasons + ["только два варианта на позицию"]
        out_slots.append({
            "code": code, "label": label, "name": POSITION_RU.get(code, code), "count": n,
            "starters": starters, "second": second, "backup": backup, "youth": youth,
            "need": level, "need_ru": NEED_RU[level], "reasons": reasons,
        })
    # Основной игрок заметно слабее остальной основы — «не соответствует уровню команды»
    all_starters = [x["fit"] for s in out_slots for x in s["starters"]]
    if len(all_starters) >= 6:
        med = sorted(all_starters)[len(all_starters) // 2]
        for s in out_slots:
            for x in s["starters"]:
                if x["fit"] <= med - LEVEL_GAP:
                    s["reasons"].insert(0, f"{x['name']} заметно слабее остальной основы ({x['fit']} против медианы {med})")
                    if s["need"] in ("none", "medium"):
                        s["need"] = "high"
                    if x["fit"] <= med - 2 * LEVEL_GAP:
                        s["need"] = "critical"
                    s["need_ru"] = NEED_RU[s["need"]]
    order = {"critical": 0, "high": 1, "medium": 2, "unknown": 3, "none": 4}
    priorities = sorted([s for s in out_slots if s["need"] not in ("none", "unknown")],
                        key=lambda s: (order[s["need"]], min((x["fit"] for x in s["starters"]), default=0)))
    texts = []
    for i, s in enumerate(priorities[:3], 1):
        texts.append(f"{s['name'].capitalize()} — приоритет окна №{i}: " + "; ".join(s["reasons"]) + ".")
    ages = Counter()
    for p in own:
        if p.age is None:
            continue
        ages["до 21" if p.age <= 21 else "22–25" if p.age <= 25 else "26–29" if p.age <= 29 else "30+"] += 1
    verdicts = []
    for p in own:
        r = ranks.get(p.name)
        v, why = own_player_verdict(p, r, dna)
        if v != "KEEP":
            verdicts.append({"id": p.id, "name": p.name, "age": p.age, "verdict": v, "verdict_ru": VERDICT_RU[v], "why": why})
    return {
        "formation": dna.formation, "slots": out_slots, "priorities": texts,
        "age_structure": dict(ages), "player_verdicts": verdicts, "squad_size": len(own),
        "ranks": ranks,  # 0 — основной, 1 — второй, 2 — запасной; нет в словаре — вне ротации
        "disclaimer": DISCLAIMER,
    }
