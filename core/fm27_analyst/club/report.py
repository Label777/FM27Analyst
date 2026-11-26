"""Скаутский отчёт (17.6), рыночный вердикт (17.4), сравнение (17.5), wonderkids (17.3)."""

from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta

from .. import reference as ref
from .db import ClubDNA
from .fit import DISCLAIMER, FitResult, best_fit, formation_slots, profiles_for, tactical_fit
from .importer import ScoutPlayer, attribute_groups
from .values import POSITION_RU

GRADES = ["Elite Signing", "Excellent Signing", "Good Signing", "Risky Signing", "Not Recommended"]
GRADE_RU = {
    "Elite Signing": "Элитное приобретение",
    "Excellent Signing": "Отличное приобретение",
    "Good Signing": "Хорошее приобретение",
    "Risky Signing": "Рискованное приобретение",
    "Not Recommended": "Не рекомендуется",
}
VERDICT_RU = {"BUY": "Покупать", "WATCH": "Наблюдать", "AVOID": "Избегать", "SELL": "Продавать",
              "LOAN": "Отдать в аренду", "KEEP": "Оставить"}


def style_names(dna: ClubDNA) -> list[str]:
    from .fit import profiles_data

    mods = profiles_data()["style_modifiers"]
    return [mods[x]["name_ru"] if x in mods else x for x in dna.style]


def money(v: float | None, cur: str | None = None) -> str:
    if v is None:
        return "нет данных"
    sym = {"EUR": "€", "GBP": "£", "USD": "$", "UAH": "₴"}.get(cur or "", "")
    if v >= 1e6:
        return f"{sym}{v / 1e6:.1f} млн".replace(".0 ", " ")
    if v >= 1e3:
        return f"{sym}{v / 1e3:.0f} тыс."
    return f"{sym}{v:.0f}"


def _src(p: ScoutPlayer) -> str:
    t = datetime.fromtimestamp(p.source.imported_at).strftime("%d.%m.%Y %H:%M")
    return f"{p.source.file}, импорт {t}"


def group_averages(p: ScoutPlayer) -> dict[str, float | None]:
    out = {}
    for g, attrs in attribute_groups().items():
        vals = [p.attr(a) for a in attrs if p.attr(a) is not None]
        out[g] = round(sum(vals) / len(vals), 1) if vals else None
    return out


def own_slot_benchmark(own: list[ScoutPlayer], position: str, dna: ClubDNA) -> list[tuple[ScoutPlayer, int]]:
    """Наши игроки на позиции, отсортированные по соответствию."""
    ranked = []
    for p in own:
        fr = best_fit(p, dna, position)
        if fr and fr.score is not None and (position in p.positions or fr.components and any(
                c.name == "Позиция" and c.score >= 65 for c in fr.components)):
            ranked.append((p, fr.score))
    return sorted(ranked, key=lambda x: -x[1])


def market_value_check(p: ScoutPlayer, fit: FitResult | None, market: list[ScoutPlayer], dna: ClubDNA) -> dict:
    if p.value_mid is None:
        return {"verdict": "unknown", "text": "Стоимость в выгрузке не указана"}
    pos = set(p.positions)
    peers = [m for m in market if m.key != p.key and m.value_mid and set(m.positions) & pos
             and (p.age is None or m.age is None or abs(m.age - p.age) <= 3)]
    if fit and fit.score is not None:
        tmp = []
        for m in peers:
            mf = best_fit(m, dna, next(iter(set(m.positions) & pos)))
            if mf and mf.score is not None and abs(mf.score - fit.score) <= 7:
                tmp.append(m)
        peers = tmp
    if len(peers) < 3:
        return {"verdict": "unknown", "peers": len(peers),
                "text": f"Сравнить не с кем: похожих игроков в базе — {len(peers)}. Импортируйте больше результатов поиска."}
    med = statistics.median(m.value_mid for m in peers)
    ratio = p.value_mid / med if med else 1
    if ratio <= 0.7:
        v, t = "below", "дешевле похожих игроков"
    elif ratio >= 1.4:
        v, t = "above", "дороже похожих игроков"
    else:
        v, t = "fair", "в пределах рынка"
    return {"verdict": v, "ratio": round(ratio, 2), "peers": len(peers), "median": med,
            "text": f"{money(p.value_mid, p.currency)} — {t} (медиана {len(peers)} сопоставимых: {money(med, p.currency)})"}


def scouting_report(p: ScoutPlayer, dna: ClubDNA, own: list[ScoutPlayer], market: list[ScoutPlayer],
                    history: list[tuple[float, dict]] | None = None) -> dict:
    gd = dna.game_date or date.today()
    # 2. позиции и профили
    fits: list[FitResult] = []
    for pos in p.positions:
        for prof in profiles_for(pos):
            if all(f.profile_id != prof["id"] for f in fits):
                fits.append(tactical_fit(p, prof["id"], dna, [pos]))
    fits = sorted([f for f in fits if f.score is not None], key=lambda f: -f.score) or fits
    top = fits[0] if fits else None
    # 6. соответствие нашей схеме
    slots = {s[0] for s in formation_slots(dna.formation)}
    slot = next((pos for pos in p.positions if pos in slots), None)
    slot_fit = best_fit(p, dna, slot) if slot else None
    bench = own_slot_benchmark(own, slot, dna) if slot else []
    squad_line = "Позиции игрока нет в нашей схеме " + dna.formation if not slot else (
        "На этой позиции у нас нет игроков в базе — импортируйте состав" if not bench else
        "; ".join(f"{q.name} — {s}" for q, s in bench[:3]))
    improves = None
    if slot_fit and slot_fit.score is not None and bench:
        improves = slot_fit.score - bench[0][1]
    groups = group_averages(p)
    value = market_value_check(p, slot_fit or top, market, dna)
    # 9. риски
    risks = []
    if p.certainty and p.certainty < 0.7:
        risks.append("Атрибуты известны диапазонами — нужен полный отчёт скаута в игре")
    if not p.attributes:
        risks.append("В выгрузке нет атрибутов — оценка невозможна")
    if p.age is not None and p.age >= 30:
        risks.append(f"Возраст {p.age}: короткое окно пика, низкая перепродажа")
    if dna.max_signing_age and p.age and p.age > dna.max_signing_age:
        risks.append(f"Противоречит возрастной политике клуба (до {dna.max_signing_age})")
    if slot_fit and any(c.name == "Позиция" and c.score < 100 for c in slot_fit.components):
        risks.append("Потребуется адаптация к позиции в нашей схеме")
    if dna.transfer_budget and p.value_low and p.value_low > dna.transfer_budget:
        risks.append(f"Стоимость выше трансферного бюджета ({money(dna.transfer_budget, dna.currency)})")
    if dna.wage_budget_week and p.wage_week and p.wage_week > dna.wage_budget_week:
        risks.append("Зарплата выше зарплатного лимита клуба на игрока")
    if p.contract_until and p.contract_until <= gd + timedelta(days=365):
        risks.append("Контракт истекает в течение года — можно торговаться или подписать бесплатно позже")
    if value.get("verdict") == "above":
        risks.append("Переплата относительно сопоставимых игроков")
    # 7. развитие
    dev = []
    if p.current_stars:
        dev.append(f"Текущий уровень: {p.current_stars[0]:g}–{p.current_stars[1]:g}★" if p.current_stars[0] != p.current_stars[1] else f"Текущий уровень: {p.current_stars[0]:g}★")
    if p.potential_stars:
        dev.append(f"Потенциал: {p.potential_stars[0]:g}–{p.potential_stars[1]:g}★" if p.potential_stars[0] != p.potential_stars[1] else f"Потенциал: {p.potential_stars[0]:g}★")
    if p.age is not None:
        dev.append("Возраст активного роста" if p.age <= 21 else ("Близок к пику" if p.age <= 27 else "Пик или спад"))
    if history and len(history) >= 2:
        first, last = history[0][1], history[-1][1]
        ch = {a: (sum(last[a]) - sum(first[a])) / 2 for a in last if a in first}
        grown = sorted(((v, a) for a, v in ch.items() if v >= 1), reverse=True)[:4]
        if grown:
            dev.append("Рост между выгрузками: " + ", ".join(f"{ref.attr_ru(a)} +{v:g}" for v, a in grown))
    if not dev:
        dev.append("Данных о потенциале в выгрузке нет — добавьте колонку потенциала в вид")
    grade, verdict, why = grade_player(p, slot_fit or top, improves, value, risks, dna)
    return {
        "player_id": p.id,
        "title": f"PLAYER SCOUTING REPORT — {p.name}",
        "disclaimer": DISCLAIMER + ". Все значения — из выгрузки: " + _src(p),
        "sections": [
            {"n": 1, "title": "Основная информация", "rows": [
                ["Возраст", p.age if p.age is not None else "нет данных"],
                ["Клуб", p.club or "нет данных"], ["Гражданство", p.nationality or "нет данных"],
                ["Лига", p.division or "нет данных"],
                ["Контракт до", p.contract_until.strftime("%d.%m.%Y") if p.contract_until else "нет данных"],
                ["Стоимость", money(p.value_low, p.currency) if p.value_low == p.value_high else f"{money(p.value_low, p.currency)} – {money(p.value_high, p.currency)}"],
                ["Зарплата в неделю", money(p.wage_week, p.currency)],
            ]},
            {"n": 2, "title": "Позиция и игровые профили", "rows": [["Позиции", ", ".join(POSITION_RU.get(x, x) for x in p.positions) or (p.position_raw or "нет данных")]]
             + [[f.profile_name, f"{f.score}/100" if f.score is not None else "мало данных"] for f in fits[:3]]},
            {"n": 3, "title": "Сильные качества", "items": (top.strengths if top else []) or ["Нет атрибутов ≥14 среди ключевых для профиля"]},
            {"n": 4, "title": "Слабые качества", "items": (top.weaknesses if top else []) or ["Явных провалов среди ключевых атрибутов нет"]},
            {"n": 5, "title": "Статистический профиль", "rows": [
                ["Техника (среднее)", groups.get("technical") or "—"], ["Ментальные (среднее)", groups.get("mental") or "—"],
                ["Физика (среднее)", groups.get("physical") or "—"],
            ] + ([["Вратарские (среднее)", groups["goalkeeping"]]] if groups.get("goalkeeping") and "GK" in p.positions else [])
              + [[k, v] for k, v in list(p.extra.items())[:8]],
             "note": "Матчевая статистика попадёт сюда, если добавить её колонки в вид перед выгрузкой"},
            {"n": 6, "title": f"Тактическая совместимость ({dna.formation}" + (", " + ", ".join(style_names(dna)) if dna.style else "") + ")",
             "fit": slot_fit.model_dump() if slot_fit else None,
             "rows": [["Наши игроки на позиции", squad_line]]
             + ([["Против нашего лучшего", f"{improves:+d} к соответствию"]] if improves is not None else [])},
            {"n": 7, "title": "Потенциал развития", "items": dev},
            {"n": 8, "title": "Оценка стоимости", "items": [value["text"]]},
            {"n": 9, "title": "Риски трансфера", "items": risks or ["Существенных рисков по данным не видно"]},
            {"n": 10, "title": "Итоговая рекомендация", "grade": grade, "grade_ru": GRADE_RU[grade],
             "verdict": verdict, "verdict_ru": VERDICT_RU[verdict], "items": why},
        ],
        "grade": grade,
        "verdict": verdict,
    }


def grade_player(p: ScoutPlayer, fit: FitResult | None, improves: int | None, value: dict, risks: list[str],
                 dna: ClubDNA) -> tuple[str, str, list[str]]:
    why: list[str] = []
    if fit is None or fit.score is None:
        return "Risky Signing", "WATCH", ["Недостаточно атрибутов для оценки — нужен отчёт скаута в игре"]
    s, conf = fit.score, fit.confidence
    why.append(f"Соответствие задаче «{fit.profile_name}»: {s}/100 (достоверность {conf:.0%})")
    if s >= 82 and conf >= 0.7 and (improves is None or improves > 0):
        g = 0
    elif s >= 75:
        g = 1
    elif s >= 65:
        g = 2
    elif s >= 55:
        g = 3
    else:
        g = 4
    if conf < 0.5 and g < 3:
        g = 3
        why.append("Данные приблизительные — оценка снижена до «рискованной»")
    if improves is not None:
        why.append(("Сильнее" if improves > 0 else "Слабее") + f" нашего лучшего на позиции на {abs(improves)}")
        if improves < -10 and g < 3:
            g += 1
    over_budget = bool(dna.transfer_budget and p.value_low and p.value_low > dna.transfer_budget)
    age_bad = bool(dna.max_signing_age and p.age and p.age > dna.max_signing_age)
    if over_budget:
        why.append("Выше бюджета")
    if age_bad:
        why.append("Не подходит под возрастную политику")
        g = min(4, g + 1)
    if value.get("verdict") == "below":
        why.append("Цена ниже рынка для такого уровня")
    elif value.get("verdict") == "above":
        why.append("Цена выше рынка")
    grade = GRADES[g]
    if g <= 2 and not over_budget and conf >= 0.5 and value.get("verdict") != "above":
        verdict = "BUY"
    elif g <= 3:
        verdict = "WATCH"
    else:
        verdict = "AVOID"
    if p.is_free_agent() and g <= 2:
        why.append("Свободный агент — можно подписать без трансферной суммы")
        verdict = "BUY"
    return grade, verdict, why


def own_player_verdict(p: ScoutPlayer, rank: int | None, dna: ClubDNA) -> tuple[str, str]:
    """Для игроков своего состава: KEEP / LOAN / SELL."""
    gd = dna.game_date or date.today()
    if p.age is not None and p.age <= 21 and (rank is None or rank >= 2):
        return "LOAN", "Молодой и не входит в двух лучших на позиции — нужна игровая практика"
    if p.age is not None and p.age >= 30 and (rank is None or rank >= 2):
        return "SELL", f"Возраст {p.age} и не основной — пока есть стоимость"
    if p.contract_until and p.contract_until <= gd + timedelta(days=365) and (rank is None or rank >= 1):
        return "SELL", "Контракт истекает, не основной — продать, пока не ушёл бесплатно"
    return "KEEP", "Нужен команде"


def compare(players: list[ScoutPlayer], dna: ClubDNA, own: list[ScoutPlayer], market: list[ScoutPlayer]) -> dict:
    """Сравнение 2+ игроков + ответ «кого брать для моей команды»."""
    common = set.intersection(*(set(p.positions) for p in players)) if players else set()
    slots = {s[0] for s in formation_slots(dna.formation)}
    pos = next((x for x in common if x in slots), None) or next(iter(common), None)
    rows = []
    for p in players:
        fit = best_fit(p, dna, pos) if pos else best_fit(p, dna)
        rep = scouting_report(p, dna, own, market)
        rows.append({
            "id": p.id, "name": p.name, "age": p.age, "value": money(p.value_mid, p.currency),
            "wage": money(p.wage_week, p.currency), "groups": group_averages(p),
            "fit": fit.score if fit else None, "profile": fit.profile_name if fit else None,
            "confidence": fit.confidence if fit else 0, "strengths": fit.strengths if fit else [],
            "weaknesses": fit.weaknesses if fit else [], "grade": rep["grade"], "verdict": rep["verdict"],
            "potential": p.potential_stars, "contract": p.contract_until.isoformat() if p.contract_until else None,
        })
    by_id = {p.id: p for p in players}

    def pot(r: dict) -> float:
        return r["potential"][1] if r["potential"] else 0.0

    def val(r: dict) -> float:
        return by_id[r["id"]].value_mid or 0.0

    # Сначала соответствие задаче; при разнице < 3 решают потенциал, цена, возраст
    ranked = sorted(rows, key=lambda r: -(r["fit"] or 0))
    if len(ranked) > 1 and (ranked[0]["fit"] or 0) - (ranked[1]["fit"] or 0) < 3:
        close = [r for r in ranked if (ranked[0]["fit"] or 0) - (r["fit"] or 0) < 3]
        close.sort(key=lambda r: (-pot(r), val(r), r["age"] or 99))
        ranked = close + [r for r in ranked if r not in close]
    best = ranked[0] if ranked else None
    answer = None
    if best and len(ranked) > 1:
        second = ranked[1]
        reasons = []
        fd = (best["fit"] or 0) - (second["fit"] or 0)
        if fd >= 3:
            reasons.append(f"лучше подходит под задачу ({best['fit']} против {second['fit']})")
        else:
            reasons.append(f"соответствие почти равное ({best['fit']} и {second['fit']})")
            if pot(best) > pot(second):
                reasons.append(f"выше потенциал ({pot(best):g}★ против {pot(second):g}★)")
            if val(best) and val(second) and val(best) < val(second) * 0.9:
                reasons.append(f"дешевле ({money(val(best), by_id[best['id']].currency)} против {money(val(second), by_id[second['id']].currency)})")
            if best["age"] and second["age"] and best["age"] < second["age"]:
                reasons.append(f"моложе ({best['age']} против {second['age']}) — дольше пик и выше перепродажа")
        if best["confidence"] > second["confidence"] + 0.1:
            reasons.append("данные о нём надёжнее")
        answer = f"Для нашей схемы {dna.formation} — {best['name']}: " + ", ".join(reasons) + "."
        if dna.transfer_budget and all(by_id[r["id"]].value_low and by_id[r["id"]].value_low > dna.transfer_budget for r in ranked):
            answer += f" Но все варианты дороже бюджета ({money(dna.transfer_budget, dna.currency)}) — нужен торг или продажа."
    return {"position": POSITION_RU.get(pos, pos) if pos else None, "players": rows, "answer": answer,
            "disclaimer": DISCLAIMER}


WONDERKID_CATEGORIES = {
    "elite": "Элитные таланты", "future_stars": "Будущие звёзды", "hidden_gems": "Скрытые жемчужины",
    "low_cost": "Недорогие таланты", "defenders": "Защитники с высоким потенциалом",
    "tech_mids": "Технические полузащитники", "phys_strikers": "Физически мощные нападающие",
    "underrated": "Недооценённые перспективные",
}


def wonderkids(market: list[ScoutPlayer], dna: ClubDNA, max_age: int = 21) -> dict:
    young = [p for p in market if p.age is not None and p.age <= max_age]
    values = sorted(p.value_mid for p in young if p.value_mid)
    cheap_cut = values[len(values) // 4] if len(values) >= 4 else None
    median_v = statistics.median(values) if values else None
    cats: dict[str, list[dict]] = {k: [] for k in WONDERKID_CATEGORIES}
    has_potential = any(p.potential_stars for p in young)
    for p in young:
        fit = best_fit(p, dna)
        fs = fit.score if fit and fit.score is not None else None
        pot = p.potential_stars[1] if p.potential_stars else None
        cur = p.current_stars[1] if p.current_stars else None
        item = {"id": p.id, "name": p.name, "age": p.age, "positions": [POSITION_RU.get(x, x) for x in p.positions],
                "fit": fs, "profile": fit.profile_name if fit else None, "potential": p.potential_stars,
                "current": p.current_stars, "value": money(p.value_mid, p.currency), "why": []}

        def add(cat: str, why: str) -> None:
            cats[cat].append({**item, "why": [why]})

        if pot is not None and pot >= 4.5:
            add("elite", f"потенциал {pot:g}★")
        elif pot is not None and pot >= 4.0:
            add("future_stars", f"потенциал {pot:g}★")
        if cur is not None and cur <= 2.5 and ((pot or 0) >= 3.5 or (fs or 0) >= 62):
            add("hidden_gems", "низкий текущий уровень, но " + (f"потенциал {pot:g}★" if pot else f"атрибуты под задачу на {fs}"))
        if cheap_cut and p.value_mid and p.value_mid <= cheap_cut and ((pot or 0) >= 3.5 or (fs or 0) >= 60):
            add("low_cost", f"в нижней четверти по цене ({money(p.value_mid, p.currency)})")
        if set(p.positions) & {"D_C", "D_L", "D_R", "WB_L", "WB_R", "DM"} and ((pot or 0) >= 3.5 or (fs or 0) >= 65):
            add("defenders", f"потенциал {pot:g}★" if pot else f"соответствие {fs}")
        g = group_averages(p)
        tech = [p.attr(a) for a in ("passing", "first_touch", "technique", "vision") if p.attr(a) is not None]
        if set(p.positions) & {"M_C", "AM_C", "DM"} and len(tech) >= 3 and sum(tech) / len(tech) >= 13:
            add("tech_mids", f"пас/касание/техника/видение в среднем {sum(tech) / len(tech):.1f}")
        phys = [p.attr(a) for a in ("pace", "acceleration", "strength", "jumping_reach") if p.attr(a) is not None]
        if "ST" in p.positions and len(phys) >= 3 and sum(phys) / len(phys) >= 13:
            add("phys_strikers", f"физика в среднем {sum(phys) / len(phys):.1f}")
        if fs is not None and fs >= 65 and ((cur is not None and cur <= 2.5) or (median_v and p.value_mid and p.value_mid < median_v)):
            add("underrated", f"соответствие {fs} при скромной оценке/цене")
        _ = g
    for k in cats:
        cats[k].sort(key=lambda x: -((x["potential"][1] if x["potential"] else 0) * 20 + (x["fit"] or 0)))
        cats[k] = cats[k][:10]
    notes = [DISCLAIMER]
    if not has_potential:
        notes.append("В выгрузке нет колонки потенциала — категории по потенциалу пустые. Добавьте её в вид.")
    return {"categories": [{"id": k, "title": WONDERKID_CATEGORIES[k], "players": v} for k, v in cats.items()],
            "notes": notes, "pool": len(young)}
