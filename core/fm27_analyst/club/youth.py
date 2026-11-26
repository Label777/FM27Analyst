"""Развитие молодёжи (раздел 20): статус, динамика атрибутов, застой, индивидуальный план.

Помощник не знает скрытый потенциал FM — только звёзды потенциала из
выгрузки и реальный рост атрибутов между выгрузками. Поэтому для динамики
нужны минимум две выгрузки состава с разной датой в сейве.
"""

from __future__ import annotations

from datetime import date

from .. import reference as ref
from .db import ClubDNA
from .director import _slot_for
from .fit import best_fit, profile
from .importer import ScoutPlayer, attribute_groups
from .squad import squad_plan
from .values import POSITION_RU

GROUP_RU = {"technical": "Техническое", "physical": "Физическое", "mental": "Ментальное", "goalkeeping": "Вратарское"}
STAGNATION_MONTHS = 6


def _months(a: date | None, b: date | None) -> int | None:
    if not a or not b:
        return None
    return (b.year - a.year) * 12 + (b.month - a.month)


def development(history: list[dict], profile_attrs: list[str], goalkeeper: bool = False) -> dict:
    """Рост атрибутов между первой и последней выгрузкой."""
    if len(history) < 2:
        return {"snapshots": len(history), "text": "Одна выгрузка — динамики пока нет. Повторите выгрузку состава через 1–2 месяца игры."}
    first, last = history[0], history[-1]
    months = _months(first["game_date"], last["game_date"])
    changes = {}
    gk_attrs = set(attribute_groups()["goalkeeping"])
    for a, r in last["attrs"].items():
        if (a in gk_attrs) != goalkeeper and a not in ("kicking", "first_touch", "passing"):
            continue  # вратарские атрибуты полевого игрока (и наоборот) не показательны
        if a in first["attrs"]:
            d = (r[0] + r[1]) / 2 - (first["attrs"][a][0] + first["attrs"][a][1]) / 2
            if d:
                changes[a] = d
    total = sum(changes.values())
    prof_total = sum(v for a, v in changes.items() if a in profile_attrs)
    grown = sorted(((v, a) for a, v in changes.items() if v > 0), reverse=True)[:5]
    fell = sorted(((v, a) for a, v in changes.items() if v < 0))[:3]
    text = f"За {months} мес. в сейве" if months is not None else f"Между {len(history)} выгрузками (даты в сейве не заданы)"
    text += f": сумма атрибутов {total:+g}, ключевые для профиля {prof_total:+g}"
    return {
        "snapshots": len(history), "months": months, "total": total, "profile_total": prof_total,
        "grown": [f"{ref.attr_ru(a)} +{v:g}" for v, a in grown], "fell": [f"{ref.attr_ru(a)} {v:g}" for v, a in fell],
        "text": text,
    }


def idp(p: ScoutPlayer, profile_id: str) -> dict:
    """Индивидуальный план: самые слабые важные атрибуты в каждой группе."""
    prof = profile(profile_id)
    weights = prof["weights"]
    groups = attribute_groups()
    plan = {}
    for g, attrs in groups.items():
        if g == "goalkeeping" and "GK" not in p.positions:
            continue
        known = [a for a in attrs if p.attr(a) is not None]
        key_attrs = [a for a in known if weights.get(a, 0) > 0]
        pool, general = (key_attrs, False) if key_attrs else (known, True)
        if g == "physical" and general:
            pool = [a for a in known if a in ("stamina", "natural_fitness", "strength", "acceleration", "agility", "balance")]
        cands = sorted((p.attr(a), -weights.get(a, 0), a) for a in pool)
        weak = [(v, w, a) for v, w, a in cands if v < 14]  # развиваем слабое, сильное поддерживаем
        focus = [f"{ref.attr_ru(a)} ({v:g})" for v, _w, a in weak[:3]]
        if not focus and cands:
            focus = ["ключевые атрибуты уже 14+ — поддерживать уровень"]
        if focus:
            plan[g] = {"title": GROUP_RU.get(g, g), "focus": focus,
                       "note": "общее развитие — для профиля эти атрибуты не ключевые" if general else "ключевые для профиля"}
    plan["tactical"] = {"title": "Тактическое", "focus": [f"Развивать как «{prof['name_ru']}»"]}
    return plan


def youth_report(own: list[ScoutPlayer], dna: ClubDNA, history_of, max_age: int = 21) -> dict:
    plan = squad_plan(own, dna)
    ranks: dict[str, int] = plan["ranks"]
    slot_info = {s["code"]: s for s in plan["slots"]}
    mentors = [q for q in own if (q.age or 0) >= 27 and (q.attr("determination") or 0) >= 15]
    out = []
    for p in own:
        if p.age is None or p.age > max_age:
            continue
        slot = _slot_for(p, dna)
        fit = best_fit(p, dna, slot) if slot else best_fit(p, dna)
        if fit is None:
            continue
        starter_fit = None
        if slot and slot_info.get(slot) and slot_info[slot]["starters"]:
            starter_fit = min(x["fit"] for x in slot_info[slot]["starters"])
        gap = (fit.score - starter_fit) if (fit.score is not None and starter_fit is not None) else None
        hist = history_of(p.key)
        dev = development(hist, list(profile(fit.profile_id)["weights"]), "GK" in p.positions)
        r = ranks.get(p.name)
        flags, actions = [], []
        if r == 0:
            status = "Игрок основы"
        elif gap is not None and gap >= -8:
            status = "Готов к первой команде"
            actions.append("Давать минуты в ротации: разница с основным в пределах 8")
        elif r == 1:
            status = "Ротация"
            actions.append("Второй номер — регулярные выходы со скамейки и кубковые матчи")
        elif p.age >= 18:
            status = "Нужна аренда"
            actions.append("Не входит в двух лучших на позиции — аренда в клуб, где будет играть")
        else:
            status = "Развитие в академии"
            actions.append("До 18 лет — тренировки и матчи молодёжной команды")
        stagnant = (dev.get("months") or 0) >= STAGNATION_MONTHS and dev.get("profile_total", 1) <= 1
        if stagnant:
            flags.append(f"Застой: за {dev['months']} мес. ключевые атрибуты почти не выросли")
            if status in ("Готов к первой команде", "Ротация", "Игрок основы"):
                actions.append("Сменить фокус индивидуальных тренировок и дать больше игрового времени")
            else:
                actions.append("Сменить фокус индивидуальных тренировок; игровая практика — через аренду")
        if p.potential_stars and p.current_stars and p.potential_stars[0] - p.current_stars[1] >= 1.5:
            flags.append("Большой запас потенциала по звёздам из выгрузки")
        if mentors and (p.attr("determination") or 20) < 14:
            m = max(mentors, key=lambda q: q.attr("determination") or 0)
            actions.append(f"Наставник: {m.name} (целеустремлённость {m.attr('determination'):g}) — "
                           "в FM наставничество влияет на характер молодого игрока")
        out.append({
            "id": p.id, "name": p.name, "age": p.age, "position": POSITION_RU.get(slot, slot) if slot else ", ".join(p.positions),
            "fit": fit.score, "profile": fit.profile_name, "starter_fit": starter_fit, "gap": gap,
            "potential": p.potential_stars, "current": p.current_stars, "status": status, "flags": flags,
            "development": dev, "plan": idp(p, fit.profile_id), "actions": actions,
        })
    out.sort(key=lambda x: (x["status"] != "Готов к первой команде", -(x["fit"] or 0)))
    return {
        "players": out, "count": len(out),
        "note": "Скрытый потенциал FM помощнику неизвестен: оценка — по звёздам потенциала и реальному росту "
                "атрибутов между выгрузками. Для динамики выгружайте состав раз в 1–2 месяца игры и обновляйте дату в «ДНК клуба».",
    }
