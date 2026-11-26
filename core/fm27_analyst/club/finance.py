"""Финансовый директор (раздел 21): ведомость, контракты, переплаты, экономия, риски.

Опирается только на зарплаты, стоимость и контракты из выгрузки состава.
Бонусы, условия контрактов и амортизацию выгрузка не содержит — об этом
отчёт говорит прямо, а не додумывает.
"""

from __future__ import annotations

from datetime import date

from .db import ClubDNA
from .director import months_left, wage_structure
from .importer import ScoutPlayer
from .report import money
from .squad import squad_plan

ROLE_RU = {0: "основной", 1: "второй номер", 2: "запасной"}


def finance_report(own: list[ScoutPlayer], dna: ClubDNA) -> dict:
    gd = dna.game_date or date.today()
    ws = wage_structure(own)
    if not ws:
        return {"error": "В выгрузке состава нет зарплат — добавьте колонку зарплаты в вид и выгрузите снова"}
    cur = next((p.currency for p in own if p.currency), dna.currency)
    plan = squad_plan(own, dna)
    ranks: dict[str, int] = plan["ranks"]

    def role(p: ScoutPlayer) -> str:
        r = ranks.get(p.name)
        return ROLE_RU.get(r, "вне ротации")

    total_w = ws["total"]
    alerts: list[dict] = []
    budget_line = None
    if dna.wage_budget_total_week:
        share = total_w / dna.wage_budget_total_week
        budget_line = f"{share:.0%} зарплатного бюджета ({money(total_w, cur)} из {money(dna.wage_budget_total_week, cur)} в неделю)"
        if share > 1:
            alerts.append({"level": "critical", "text": f"Ведомость превышает зарплатный бюджет на {money(total_w - dna.wage_budget_total_week, cur)} в неделю"})
        elif share > 0.9:
            alerts.append({"level": "warning", "text": f"Ведомость занимает {share:.0%} бюджета — запаса на новичков почти нет"})

    overpaid, renew, sell_expiring = [], [], []
    for p in own:
        r = ranks.get(p.name)
        ml = months_left(p, gd)
        if p.wage_week and p.wage_week > ws["p75"] and r != 0:
            overpaid.append({"id": p.id, "name": p.name, "age": p.age, "wage": money(p.wage_week, cur), "role": role(p),
                             "why": f"зарплата в верхней четверти состава, но {role(p)}"})
        if r in (0, 1) and ml is not None and ml <= 18 and (p.age or 0) <= 31:
            renew.append({"id": p.id, "name": p.name, "age": p.age, "months_left": ml, "role": role(p),
                          "why": f"{role(p)}, до конца контракта {ml} мес." + (" — срочно" if ml <= 6 else "")})
        if (r is None or r >= 2) and ml is not None and ml <= 12 and p.value_low:
            sell_expiring.append({"id": p.id, "name": p.name, "age": p.age, "months_left": ml, "role": role(p),
                                  "value": money(p.value_low, cur),
                                  "why": f"{role(p)}, контракт истекает через {ml} мес. — продать, пока стоит {money(p.value_low, cur)}"})

    verdicts = {v["name"]: v["verdict"] for v in plan["player_verdicts"]}
    by_name = {p.name: p for p in own}
    sell_saving = sum(by_name[n].wage_week or 0 for n, v in verdicts.items() if v == "SELL")
    loan_saving = sum(by_name[n].wage_week or 0 for n, v in verdicts.items() if v == "LOAN")
    savings = []
    if sell_saving:
        savings.append(f"Продажа игроков из списка «Продавать» освободит {money(sell_saving, cur)} в неделю")
    if loan_saving:
        savings.append(f"Аренды молодых — до {money(loan_saving, cur)} в неделю (зависит от доли зарплаты, которую возьмёт арендатор)")
    for o in overpaid[:3]:
        savings.append(f"{o['name']}: {o['why']} — кандидат на продажу или пересмотр роли")

    top = sorted((p for p in own if p.wage_week), key=lambda p: -p.wage_week)[:6]
    expiring_soon = sorted(((p, months_left(p, gd)) for p in own if months_left(p, gd) is not None and months_left(p, gd) <= 12),
                           key=lambda x: x[1])
    if len(expiring_soon) >= 4:
        alerts.append({"level": "warning", "text": f"У {len(expiring_soon)} игроков контракт истекает в ближайший год"})
    return {
        "currency": cur,
        "payroll_week": money(total_w, cur), "payroll_year": money(total_w * 52, cur),
        "median_wage": money(ws["median"], cur), "max_wage": money(ws["max"], cur), "players_with_wage": ws["count"],
        "budget_line": budget_line, "alerts": alerts,
        "top_earners": [{"id": p.id, "name": p.name, "age": p.age, "wage": money(p.wage_week, cur), "role": role(p),
                         "share": f"{p.wage_week / total_w:.0%}"} for p in top],
        "overpaid": overpaid, "renew": sorted(renew, key=lambda x: x["months_left"]),
        "sell_before_expiry": sorted(sell_expiring, key=lambda x: x["months_left"]),
        "savings": savings,
        "squad_value": money(sum(p.value_mid or 0 for p in own), cur),
        "not_available": ["Бонусы и условия контрактов", "Амортизация трансферов",
                          "Доходы клуба и финансовые ограничения лиги"],
        "note": "Бонусы, амортизацию и доходы выгрузка состава не содержит — их нужно смотреть в разделе финансов FM27.",
    }


def transfer_impact(p: ScoutPlayer, own: list[ScoutPlayer], dna: ClubDNA) -> dict | None:
    """Как покупка изменит ведомость."""
    ws = wage_structure(own)
    if not ws or not p.wage_week:
        return None
    new_total = ws["total"] + p.wage_week
    out = {"new_payroll_week": money(new_total, p.currency), "increase": f"+{p.wage_week / ws['total']:.0%}"}
    if dna.wage_budget_total_week:
        out["budget_share"] = f"{new_total / dna.wage_budget_total_week:.0%} зарплатного бюджета"
        out["over_budget"] = new_total > dna.wage_budget_total_week
    return out
