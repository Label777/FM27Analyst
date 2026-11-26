"""Спортивный директор (17.4, 22): оценка сделки, альтернативы, переговоры, сценарии окна.

Все суммы — ориентиры по выгрузке. Итоговую цену и условия определяет FM27
в переговорах; помощник в игре ничего не делает сам.
"""

from __future__ import annotations

import itertools
import re
import statistics
from datetime import date

from .db import ClubDNA
from .fit import DISCLAIMER, best_fit, formation_slots
from .importer import ScoutPlayer
from .report import market_value_check, money, scouting_report
from .search import find_all_positions
from .squad import squad_plan
from .values import POSITION_RU

NOTE = "Суммы — ориентир по выгрузке; итоговые условия определяет FM27 в переговорах."


def wage_structure(own: list[ScoutPlayer]) -> dict | None:
    wages = sorted(p.wage_week for p in own if p.wage_week)
    if not wages:
        return None
    return {
        "median": statistics.median(wages),
        "p75": wages[int(len(wages) * 0.75) - 1] if len(wages) >= 4 else wages[-1],
        "max": wages[-1],
        "total": sum(wages),
        "count": len(wages),
        "sorted": wages,
    }


def months_left(p: ScoutPlayer, gd: date) -> int | None:
    if not p.contract_until:
        return None
    return (p.contract_until.year - gd.year) * 12 + (p.contract_until.month - gd.month)


def _slot_for(p: ScoutPlayer, dna: ClubDNA) -> str | None:
    """Позиция схемы для игрока: родная, иначе смежная (ЦП → опорник/АП в 4-2-3-1)."""
    from .fit import profiles_data

    slots = [s[0] for s in formation_slots(dna.formation)]
    direct = next((x for x in p.positions if x in slots), None)
    if direct:
        return direct
    adj = profiles_data()["adjacent_positions"]
    return next((a for x in p.positions for a in adj.get(x, []) if a in slots), None)


def alternatives(p: ScoutPlayer, dna: ClubDNA, market: list[ScoutPlayer], position: str, fit: int) -> list[dict]:
    if not p.value_mid:
        return []
    out = []
    for m in market:
        if m.key == p.key or position not in m.positions:
            continue
        price = 0.0 if m.is_free_agent() else m.value_mid
        if price is None or price > 0.7 * p.value_mid:
            continue
        fr = best_fit(m, dna, position)
        if not fr or fr.score is None or fr.score < fit - 5:
            continue
        out.append({"id": m.id, "name": m.name, "age": m.age, "fit": fr.score, "confidence": fr.confidence,
                    "value": money(price, m.currency) if price else "свободный агент",
                    "saving": money(p.value_mid - price, p.currency)})
    return sorted(out, key=lambda x: (-x["fit"], x["age"] or 99))[:3]


def negotiation(p: ScoutPlayer, dna: ClubDNA, ws: dict | None, gd: date) -> dict:
    tips: list[str] = []
    if p.is_free_agent():
        return {"opening": None, "walk_away": None, "wage_offer": _wage_offer(p, dna, ws),
                "tips": ["Свободный агент: трансферной суммы нет — торг только по зарплате и бонусу за подпись"]}
    if p.value_low is None:
        return {"opening": None, "walk_away": None, "wage_offer": _wage_offer(p, dna, ws),
                "tips": ["Стоимость в выгрузке не указана — ориентира для торга нет"]}
    ml = months_left(p, gd)
    k = 0.8
    if ml is not None and ml <= 12:
        k = 0.65
        tips.append(f"До конца контракта {ml} мес. — клуб-продавец в слабой позиции, начинайте низко")
    if ml is not None and ml <= 6:
        tips.append("≤6 мес. до конца контракта: проверьте, можно ли договориться о бесплатном переходе "
                    "(в FM обычно можно, правила зависят от лиги)")
    opening = p.value_low * k
    high = p.value_high or p.value_low
    walk = high * 1.1
    if dna.transfer_budget:
        walk = min(walk, dna.transfer_budget)
    tips += [
        "Часть суммы предложите рассрочкой — бюджет текущего окна тратится меньше",
        "Замените часть фиксированной суммы бонусами за матчи/голы",
        "Если игрок молодой — добавьте процент с перепродажи вместо повышения суммы",
    ]
    return {"opening": opening, "walk_away": walk, "wage_offer": _wage_offer(p, dna, ws), "tips": tips,
            "opening_text": money(opening, p.currency), "walk_away_text": money(walk, p.currency)}


def _wage_offer(p: ScoutPlayer, dna: ClubDNA, ws: dict | None) -> dict | None:
    if not ws:
        return None
    cap = ws["p75"] if (p.wage_week is None or p.wage_week <= ws["p75"]) else ws["max"]
    if dna.wage_budget_week:
        cap = min(cap, dna.wage_budget_week)
    start = min(p.wage_week * 1.05, cap) if p.wage_week else ws["median"]
    return {"start": start, "cap": cap, "text": f"начать с {money(start, p.currency)}, потолок {money(cap, p.currency)} в неделю"}


def assess_deal(p: ScoutPlayer, dna: ClubDNA, own: list[ScoutPlayer], market: list[ScoutPlayer]) -> dict:
    gd = dna.game_date or date.today()
    ws = wage_structure(own)
    slot = _slot_for(p, dna)
    fit = best_fit(p, dna, slot) if slot else best_fit(p, dna)
    plan = squad_plan(own, dna) if own else None
    bench_line, improvement = None, None
    if plan and slot and fit and fit.score is not None:
        s = next((x for x in plan["slots"] if x["code"] == slot), None)
        if s and s["starters"]:
            weakest = min(s["starters"], key=lambda r: r["fit"])
            best = max(s["starters"], key=lambda r: r["fit"])
            improvement = fit.score - weakest["fit"]
            bench_line = f"Против слабейшего основного ({weakest['name']}, {weakest['fit']}): {improvement:+d}"
            if best is not weakest:
                bench_line += f"; против лучшего ({best['name']}, {best['fit']}): {fit.score - best['fit']:+d}"
    price = market_value_check(p, fit, market, dna)
    wage = {"text": "Зарплата в выгрузке не указана", "level": "unknown"}
    if p.wage_week and ws:
        rank = sum(1 for w in ws["sorted"] if w > p.wage_week) + 1
        ratio = p.wage_week / ws["median"] if ws["median"] else 1
        level = "high" if p.wage_week > ws["p75"] else "ok"
        wage = {"level": level, "rank": rank, "ratio": round(ratio, 2),
                "text": f"{money(p.wage_week, p.currency)} в неделю — стал бы {rank}-м по зарплате в составе "
                        f"({ratio:.1f}× медианы)"}
        if dna.wage_budget_week and p.wage_week > dna.wage_budget_week:
            wage["level"] = "over"
            wage["text"] += f"; выше лимита клуба {money(dna.wage_budget_week, p.currency)}"
    ml = months_left(p, gd)
    contract = "нет данных" if ml is None else (f"{ml} мес. до конца" + (" — рычаг в торге" if ml <= 12 else ""))
    feasibility = []
    if p.is_free_agent():
        feasibility.append("Свободный агент — сделка зависит только от зарплаты")
    if ml is not None and ml <= 12:
        feasibility.append("Короткий контракт — продавец сговорчивее")
    if dna.transfer_budget and p.value_low and p.value_low > dna.transfer_budget:
        feasibility.append(f"Нижняя оценка стоимости выше бюджета ({money(dna.transfer_budget, dna.currency)})")
    feasibility.append("Интерес других клубов в выгрузке не виден — проверьте в профиле игрока в FM27")
    rep = scouting_report(p, dna, own, market)
    alts = alternatives(p, dna, market, slot, fit.score) if slot and fit and fit.score is not None else []
    verdict = rep["verdict"]
    reasons = list(rep["sections"][9]["items"])
    if wage["level"] == "over" and verdict == "BUY":
        verdict = "WATCH"
        reasons.append("Зарплата выше лимита клуба")
    if alts and verdict == "BUY" and alts[0]["fit"] >= (fit.score if fit and fit.score else 0) - 2:
        reasons.append(f"Есть почти равная и заметно более дешёвая альтернатива: {alts[0]['name']}")
    return {
        "player_id": p.id, "name": p.name, "verdict": verdict, "grade": rep["grade"], "reasons": reasons,
        "fit": fit.score if fit else None, "profile": fit.profile_name if fit else None,
        "position": POSITION_RU.get(slot, slot) if slot else None, "vs_squad": bench_line, "improvement": improvement,
        "price": price, "wage": wage, "contract": contract, "feasibility": feasibility,
        "alternatives": alts, "negotiation": negotiation(p, dna, ws, gd), "note": NOTE, "disclaimer": DISCLAIMER,
    }


# --- режим трансферного окна (22) ---
NEED_WEIGHT = {"critical": 1.5, "high": 1.2, "medium": 1.0}


def parse_window_request(text: str) -> dict:
    q = text.lower().replace("ё", "е")
    budget = None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(млрд|млн|миллион\w*|тыс\w*|m\b|k\b)", q)
    if m:
        v = float(m.group(1).replace(",", "."))
        u = m.group(2)
        budget = v * (1e9 if u.startswith("млрд") else 1e6 if u.startswith(("млн", "миллион", "m")) else 1e3)
    return {"budget": budget, "needs": find_all_positions(text)}


def _candidates(code: str, codes: list[str], benchmark: int, market: list[ScoutPlayer], dna: ClubDNA) -> list[dict]:
    out = []
    for m in market:
        if not (set(m.positions) & set(codes)):
            continue
        fr = best_fit(m, dna, code if code in m.positions else next(iter(set(m.positions) & set(codes))))
        if not fr or fr.score is None or fr.score < benchmark + 3:
            continue
        price = 0.0 if m.is_free_agent() else m.value_mid
        if price is None:
            continue
        risks = []
        if fr.confidence < 0.6:
            risks.append("атрибуты известны диапазонами")
        if dna.max_signing_age and m.age and m.age > dna.max_signing_age:
            risks.append("старше возрастной политики")
        if m.age and m.age >= 30:
            risks.append("низкая перепродажа")
        out.append({"id": m.id, "name": m.name, "age": m.age, "fit": fr.score, "confidence": fr.confidence,
                    "improvement": fr.score - benchmark, "price": price, "wage": m.wage_week or 0.0,
                    "price_text": money(price, m.currency) if price else "свободный агент",
                    "wage_text": money(m.wage_week, m.currency) if m.wage_week else "—",
                    "risks": risks, "currency": m.currency})
    return sorted(out, key=lambda c: (-c["fit"], c["price"]))[:6]


def transfer_window(dna: ClubDNA, own: list[ScoutPlayer], market: list[ScoutPlayer],
                    budget: float | None = None, needs: list[list[str]] | None = None) -> dict:
    budget = budget if budget is not None else dna.transfer_budget
    if not budget:
        return {"error": "Не задан бюджет: укажите его в запросе или в ДНК клуба"}
    plan = squad_plan(own, dna) if own else {"slots": [], "player_verdicts": []}
    slot_by_code = {s["code"]: s for s in plan["slots"]}
    if not needs:
        auto = [s for s in plan["slots"] if s["need"] in ("critical", "high")]
        auto.sort(key=lambda s: (0 if s["need"] == "critical" else 1))
        needs = [[s["code"]] for s in auto[:3]]
        source = "по карте состава"
    else:
        source = "по запросу"
    need_rows = []
    for codes in needs:
        code = next((c for c in codes if c in slot_by_code), codes[0])
        s = slot_by_code.get(code)
        level = s["need"] if s else "high"
        if s and s["starters"]:
            weakest = min(x["fit"] for x in s["starters"])
            why = " ".join(s["reasons"])
            if "слабее остальной" in why or "не соответствует уровню" in why:
                benchmark = weakest  # нужен игрок сильнее основного
            elif s["second"]:
                benchmark = s["second"]["fit"]  # нужна замена сильнее нынешней
            else:
                benchmark = weakest - 10  # замены нет вовсе — подойдёт крепкий второй номер
        else:
            benchmark = 0
        need_rows.append({"code": code, "codes": codes, "name": POSITION_RU.get(code, code), "level": level,
                          "benchmark": benchmark, "weight": NEED_WEIGHT.get(level, 1.0),
                          "candidates": _candidates(code, codes, benchmark, market, dna)})
    sales = [v for v in plan.get("player_verdicts", []) if v["verdict"] == "SELL"]
    own_by_id = {p.id: p for p in own}
    sale_value = sum((own_by_id[v["id"]].value_low or 0) * 0.8 for v in sales if v["id"] in own_by_id)

    def best_combo(cap: float, pool_size: int, filt=lambda c: True, prefer_cheap: bool = False) -> list:
        options = [[None] + [c for c in n["candidates"] if filt(c)][:pool_size] for n in need_rows]
        best, best_key = [None] * len(need_rows), None
        for combo in itertools.product(*options):
            cost = sum(c["price"] for c in combo if c)
            if cost > cap:
                continue
            gain = sum(c["improvement"] * n["weight"] for c, n in zip(combo, need_rows) if c)
            covered = sum(1 for c in combo if c)
            key = (covered, -cost, gain) if prefer_cheap else (gain, covered, -cost)
            if best_key is None or key > best_key:
                best, best_key = list(combo), key
        return best

    safe = best_combo(budget * 0.7, 6, lambda c: c["confidence"] >= 0.6 and not c["risks"])
    balanced = best_combo(budget, 5, lambda c: "старше возрастной политики" not in c["risks"])
    stretch = budget * 1.3 + sale_value  # амбициозный: до +30% к бюджету за счёт торга/продаж
    ambitious = best_combo(stretch, 6)

    def pack(name: str, title: str, combo: list, cap: float, desc: str) -> dict:
        picks, total, wages = [], 0.0, 0.0
        for c, n in zip(combo, need_rows):
            if c:
                total += c["price"]
                wages += c["wage"]
                picks.append({**c, "need": n["name"]})
        uncovered = [n["name"] for c, n in zip(combo, need_rows) if not c]
        over = max(0.0, total - budget)
        return {
            "id": name, "title": title, "description": desc, "picks": picks, "total": total,
            "total_text": money(total, dna.currency), "left_text": money(budget - total, dna.currency) if total <= budget else "—",
            "wages_added_text": money(wages, dna.currency) + " в неделю" if wages else "—",
            "uncovered": uncovered, "needs_sales": over > 0,
            "sales_text": f"Нужно выручить {money(over, dna.currency)} продажами" if over > 0 else None,
        }

    scenarios = [
        pack("safe", "Безопасный", safe, budget * 0.7,
             "Только надёжные данные и без рисков по возрасту; тратим не больше 70% бюджета, остальное — резерв"),
        pack("balanced", "Сбалансированный", balanced, budget,
             "Максимум усиления в рамках бюджета и возрастной политики клуба, приоритет — самые проблемные позиции"),
        pack("ambitious", "Амбициозный", ambitious, stretch,
             "Сильнейшие варианты, бюджет до +30% — за счёт продаж или увеличения бюджета у правления"),
    ]
    if [p["id"] for p in scenarios[2]["picks"]] == [p["id"] for p in scenarios[1]["picks"]]:
        scenarios[2]["description"] += ". Совпадает со сбалансированным: более сильных вариантов в базе нет"
    return {
        "budget_text": money(budget, dna.currency), "needs_source": source,
        "needs": [{k: v for k, v in n.items() if k != "candidates"} | {"candidates": n["candidates"][:4]} for n in need_rows],
        "scenarios": scenarios,
        "sales": [{**v, "value": money(own_by_id[v["id"]].value_low, own_by_id[v["id"]].currency) if v["id"] in own_by_id else "—"} for v in sales],
        "sale_value_text": money(sale_value, dna.currency) if sale_value else None,
        "note": NOTE, "disclaimer": DISCLAIMER,
    }
