"""AI Football Department (разделы 25–26): отделы над общей базой клуба.

Не девять чат-ботов, а одна система: каждый отдел — набор инструментов над
общими данными сейва (матчи, игроки, ДНК клуба) со своими критериями решения.
Оркестратор собирает их выводы в одно заключение и направляет вопросы
пользователя нужному отделу. Ни один отдел ничего не делает в FM27 сам.
"""

from __future__ import annotations

import re
from datetime import datetime

from .club.db import ClubDB
from .club.director import assess_deal, parse_window_request, transfer_window
from .club.finance import finance_report, transfer_impact
from .club.fit import DISCLAIMER
from .club.opposition import opposition_report
from .club.report import GRADE_RU, VERDICT_RU, money, scouting_report
from .club.search import parse_query, run_search
from .club.squad import squad_plan
from .club.youth import youth_report
from .season import season_answer, season_report

DEPARTMENTS = {
    "head_coach": {"name": "Главный тренер", "section": "tactics",
                   "role": "Тактика клуба, основа, соответствие игроков схеме"},
    "live_analyst": {"name": "Аналитик матча", "section": "live", "role": "Матч в реальном времени, советы по ходу игры"},
    "chief_scout": {"name": "Главный скаут", "section": "scout", "role": "Поиск игроков, Tactical Fit, скаутские отчёты"},
    "opposition": {"name": "Аналитик соперников", "section": "recon", "role": "Разведка будущих соперников"},
    "sporting_director": {"name": "Спортивный директор", "section": "director", "role": "Сделки, бюджет окна, переговоры"},
    "squad_planner": {"name": "Планировщик состава", "section": "squad", "role": "Глубина состава, приоритеты окна"},
    "youth": {"name": "Развитие молодёжи", "section": "youth", "role": "Молодые игроки, планы развития, аренды"},
    "finance": {"name": "Финансовый директор", "section": "finance", "role": "Зарплаты, контракты, экономия"},
    "season": {"name": "Аналитик сезона", "section": "season", "role": "Результаты, форма, что работает"},
}


def _ok(level: str, text: str) -> dict:
    return {"level": level, "text": text}


def dashboard(engine, club: ClubDB | None) -> list[dict]:
    """Короткий статус каждого отдела для главного меню."""
    out = []

    def add(dep: str, lines: list[dict]) -> None:
        out.append({"id": dep, **DEPARTMENTS[dep], "lines": lines})

    # аналитик матча
    if engine.last:
        s = engine.last.snapshot
        top = [x for x in engine.last.signals if x.rule_id != "tactic_working"]
        add("live_analyst", [_ok("info", f"Идёт матч: {s.minute}' {s.home_goals}:{s.away_goals}")]
            + ([_ok(top[0].severity.value, top[0].title)] if top else [_ok("good", "Проблем по данным нет")]))
    else:
        add("live_analyst", [_ok("muted", "Матч не идёт. На экране матча нажмите «Анализ экрана»")])
    if club is None:
        for dep in ("head_coach", "chief_scout", "opposition", "sporting_director", "squad_planner", "youth", "finance", "season"):
            add(dep, [_ok("muted", "Откройте сохранение")])
        return out
    dna = club.dna()
    own, market = club.players("own"), club.players("market")
    plan = squad_plan(own, dna) if own else None
    # главный тренер
    if plan:
        starters = [x["fit"] for s in plan["slots"] for x in s["starters"]]
        avg = round(sum(starters) / len(starters)) if starters else None
        from .club.report import style_names

        add("head_coach", [_ok("info", f"Схема {dna.formation}" + (", " + ", ".join(style_names(dna)) if dna.style else "")),
                           _ok("info", f"Среднее соответствие основы схеме: {avg}" if avg is not None else "Основа не определена")])
    else:
        add("head_coach", [_ok("muted", "Импортируйте состав, чтобы оценить основу под схему")])
    # скаут
    add("chief_scout", [_ok("info" if market else "muted",
                            f"В базе рынка {len(market)} игроков, в шорт-листе {len(club.shortlist())}" if market
                            else "База рынка пуста — импортируйте поиск игроков")])
    # соперники
    opps = [s for s in club.scopes() if s.startswith("opp:")]
    add("opposition", [_ok("info", f"Разведданные по соперникам: {len(opps)}") if opps
                       else _ok("muted", "Импортируйте состав ближайшего соперника")])
    # планировщик состава
    if plan:
        lines = [_ok("critical" if i == 0 and plan["slots"] else "warning", t) for i, t in enumerate(plan["priorities"][:2])]
        add("squad_planner", lines or [_ok("good", "Явных дыр в составе нет")])
    else:
        add("squad_planner", [_ok("muted", "Импортируйте состав")])
    # спортивный директор
    lines = []
    if dna.transfer_budget:
        lines.append(_ok("info", f"Трансферный бюджет: {money(dna.transfer_budget, dna.currency)}"))
    if plan and plan["player_verdicts"]:
        sells = [v["name"] for v in plan["player_verdicts"] if v["verdict"] == "SELL"]
        if sells:
            lines.append(_ok("warning", "Кандидаты на продажу: " + ", ".join(sells[:3])))
    add("sporting_director", lines or [_ok("muted", "Задайте бюджет в «ДНК клуба»")])
    # молодёжь
    if own:
        y = youth_report(own, dna, club.attribute_history_full)
        ready = [p["name"] for p in y["players"] if p["status"] == "Готов к первой команде"]
        stuck = [p["name"] for p in y["players"] if p["flags"] and p["flags"][0].startswith("Застой")]
        lines = []
        if ready:
            lines.append(_ok("good", "Готовы к первой команде: " + ", ".join(ready[:3])))
        if stuck:
            lines.append(_ok("warning", "Застой в развитии: " + ", ".join(stuck[:3])))
        add("youth", lines or [_ok("info", f"Молодых игроков до 21: {y['count']}")])
    else:
        add("youth", [_ok("muted", "Импортируйте состав")])
    # финансы
    if own:
        f = finance_report(own, dna)
        if "error" in f:
            add("finance", [_ok("muted", f["error"])])
        else:
            lines = [_ok(a["level"], a["text"]) for a in f["alerts"]]
            if f["renew"]:
                lines.append(_ok("warning", "Продлить: " + ", ".join(r["name"] for r in f["renew"][:3])))
            lines.append(_ok("info", f"Ведомость: {f['payroll_week']} в неделю"))
            add("finance", lines)
    else:
        add("finance", [_ok("muted", "Импортируйте состав с зарплатами")])
    # сезон
    if engine.store:
        r = season_report(engine.store)
        if "error" in r:
            add("season", [_ok("muted", "Завершённых матчей пока нет")])
        else:
            t = r["total"]
            lines = [_ok("info", f"{t['played']} матчей, {t['pts']} очков, форма {r['form']}")]
            if r["points_lost"]:
                lines.append(_ok("warning", r["points_lost"][0]["text"]))
            add("season", lines)
    return out


def player_conclusion(club: ClubDB, pid: int) -> dict:
    """Единое заключение по игроку: скаут → тренер → директор → финансы → данные."""
    p = club.player(pid)
    if p is None:
        raise KeyError(pid)
    dna, own, market = club.dna(), club.players("own"), club.players("market")
    rep = scouting_report(p, dna, own, market)
    deal = assess_deal(p, dna, own, market)
    fin = transfer_impact(p, own, dna)
    opinions = []
    s10 = rep["sections"][9]
    opinions.append({"dept": "Главный скаут", "stance": "за" if rep["grade"] in ("Elite Signing", "Excellent Signing", "Good Signing") else "против",
                     "text": f"{GRADE_RU[rep['grade']]}. " + "; ".join(s10["items"][:2])})
    if deal["fit"] is not None:
        if deal["improvement"] is None:
            coach = f"Соответствие задаче «{deal['profile']}»: {deal['fit']}/100. Сравнить с нашими не с кем — импортируйте состав"
            stance = "нейтрально"
        else:
            coach = f"{deal['position'] or 'Позиция'}: {deal['fit']}/100. {deal['vs_squad']}"
            stance = "за" if deal["improvement"] > 3 else "нейтрально" if deal["improvement"] >= -3 else "против"
    else:
        coach, stance = "Недостаточно атрибутов, чтобы оценить соответствие тактике", "нейтрально"
    opinions.append({"dept": "Главный тренер", "stance": stance, "text": coach})
    dir_stance = {"BUY": "за", "WATCH": "нейтрально", "AVOID": "против"}.get(deal["verdict"], "нейтрально")
    neg = deal["negotiation"]
    dir_text = f"{deal['price']['text'].rstrip('.')}. {deal['wage']['text']}."
    if deal["wage"].get("rank") == 1 and deal["wage"].get("ratio", 0) >= 2:
        dir_text += " Станет самым высокооплачиваемым — риск для зарплатной структуры (другие захотят столько же)."
        if dir_stance == "за":
            dir_stance = "нейтрально"
    if neg.get("opening_text"):
        dir_text += f" Стартовое предложение ~{neg['opening_text']}, предел {neg['walk_away_text']}."
    if deal["alternatives"]:
        a = deal["alternatives"][0]
        dir_text += f" Альтернатива дешевле: {a['name']} ({a['fit']}, {a['value']})."
    opinions.append({"dept": "Спортивный директор", "stance": dir_stance, "text": dir_text})
    if fin:
        f_stance = "против" if fin.get("over_budget") else "нейтрально"
        f_text = f"Ведомость станет {fin['new_payroll_week']} в неделю ({fin['increase']})" + (
            f", {fin['budget_share']}" if fin.get("budget_share") else "")
        opinions.append({"dept": "Финансовый директор", "stance": f_stance, "text": f_text})
    conf = rep["sections"][5]["fit"]["confidence"] if rep["sections"][5].get("fit") else 0
    data_text = f"Источник: {p.source.file}, импорт {datetime.fromtimestamp(p.source.imported_at):%d.%m.%Y}. "
    data_text += f"Достоверность атрибутов {conf:.0%}." if conf else "Атрибутов для оценки мало."
    if conf and conf < 0.6:
        data_text += " Нужен полный отчёт скаута в игре."
    opinions.append({"dept": "Аналитик данных", "stance": "против" if conf < 0.5 else "нейтрально", "text": data_text})
    against = [o for o in opinions if o["stance"] == "против"]
    pro = [o for o in opinions if o["stance"] == "за"]
    if deal["verdict"] == "AVOID" or len(against) >= 2:
        final = "AVOID"
    elif deal["verdict"] == "BUY" and not against:
        final = "BUY"
    else:
        final = "WATCH"
    summary = (f"{VERDICT_RU[final]}: " + (f"за — {', '.join(o['dept'] for o in pro)}" if pro else "сторонников нет")
               + (f"; против — {', '.join(o['dept'] for o in against)}" if against else ""))
    return {"player_id": pid, "name": p.name, "verdict": final, "verdict_ru": VERDICT_RU[final], "summary": summary,
            "opinions": opinions, "grade": rep["grade"], "deal": deal, "disclaimer": DISCLAIMER,
            "note": "Помощник только советует — в FM27 ничего не делается без вас."}


ROUTES = [
    ("live_analyst", r"сейчас|в матче|этот матч|по ходу|центр поля|момент|замен\w* сейчас"),
    ("season", r"сезон|теря\w* очк|форм\w* команд|в следующем месяце|какая тактика работает|какие изменения"),
    ("finance", r"зарплат|ведомост|финанс|продл\w*|контракт|экономи"),
    ("youth", r"молод\w*|академ|развити|юниор|воспитанник"),
    ("opposition", r"соперник|нейтрализ|разведк|следующ\w* матч"),
    ("sporting_director", r"бюджет|трансфер\w* окн|окно|распредел|продать|продаж|\d+\s*(?:млн|миллион|m\b)"),
    ("chief_scout", r"найди|ищ\w|подбери|скаут|кого купить|кандидат"),
    ("squad_planner", r"состав|глубин|усилит|дыр|слаб\w* позици|приоритет"),
]


def route(question: str, live: bool) -> str:
    q = question.lower().replace("ё", "е")
    for dep, pat in ROUTES:
        if re.search(pat, q):
            if dep == "live_analyst" and not live:
                continue
            return dep
    return "live_analyst" if live else "squad_planner"


def ask(engine, club: ClubDB | None, question: str) -> dict:
    live = engine.last is not None
    dep = route(question, live)
    base = {"department": dep, "department_name": DEPARTMENTS[dep]["name"], "section": DEPARTMENTS[dep]["section"],
            "question": question}
    if dep == "live_analyst":
        a = engine.ask(question)
        return {**base, "short": a.short, "detail": a.detail}
    if dep == "season":
        if not engine.store:
            return {**base, "short": "Откройте сохранение.", "detail": ""}
        a = season_answer(question, season_report(engine.store))
        return {**base, **a}
    if club is None:
        return {**base, "short": "Откройте сохранение — база клуба хранится в сейве.", "detail": ""}
    dna, own, market = club.dna(), club.players("own"), club.players("market")
    if dep == "finance":
        if not own:
            return {**base, "short": "Импортируйте состав с зарплатами.", "detail": ""}
        f = finance_report(own, dna)
        if "error" in f:
            return {**base, "short": f["error"], "detail": ""}
        parts = [a["text"] for a in f["alerts"]] + [r["why"] for r in f["renew"][:2]] + f["savings"][:2]
        return {**base, "short": parts[0] + "." if parts else f"Ведомость {f['payroll_week']} в неделю, рисков нет.",
                "detail": "; ".join(parts)}
    if dep == "youth":
        if not own:
            return {**base, "short": "Импортируйте состав.", "detail": ""}
        y = youth_report(own, dna, club.attribute_history_full)
        if not y["players"]:
            return {**base, "short": "Игроков до 21 года в составе нет.", "detail": ""}
        lines = [f"{p['name']} ({p['age']}): {p['status'].lower()}" for p in y["players"][:4]]
        return {**base, "short": lines[0] + ".", "detail": "; ".join(lines)}
    if dep == "opposition":
        opps = [s for s in club.scopes() if s.startswith("opp:")]
        if not opps:
            return {**base, "short": "Нет данных о сопернике: импортируйте его состав в разделе «Разведка».", "detail": ""}
        name = opps[-1][4:]
        r = opposition_report(name, club.players(opps[-1]), own, dna)
        h = r["hypotheses"]
        return {**base, "short": (h[0]["text"] + ".") if h else "Явных слабостей по выгрузке не видно.",
                "detail": "; ".join(x["text"] for x in h[1:4]) + ". " + r["note"]}
    if dep == "sporting_director":
        req = parse_window_request(question)
        if not market:
            return {**base, "short": "База рынка пуста — импортируйте поиск игроков.", "detail": ""}
        w = transfer_window(dna, own, market, req["budget"], req["needs"] or None)
        if "error" in w:
            return {**base, "short": w["error"], "detail": ""}
        b = w["scenarios"][1]
        picks = ", ".join(f"{p['need']}: {p['name']} ({p['price_text']})" for p in b["picks"]) or "подходящих кандидатов нет"
        return {**base, "short": f"Сбалансированный план на {w['budget_text']}: {picks}.",
                "detail": f"Итого {b['total_text']}, остаток {b['left_text']}. Безопасный и амбициозный варианты — в разделе «Спортивный директор»."}
    if dep == "chief_scout":
        if not market:
            return {**base, "short": "База рынка пуста — импортируйте поиск игроков.", "detail": ""}
        f, understood = parse_query(question)
        hits = run_search(market, f, dna)[:3]
        if not hits:
            return {**base, "short": "Никто не подошёл под все условия.", "detail": "; ".join(understood)}
        return {**base, "short": "Лучшие варианты: " + ", ".join(
            f"{h.player.name} ({h.player.age}, соответствие {h.fit.score if h.fit else 'н/д'})" for h in hits) + ".",
                "detail": "Как понял запрос: " + "; ".join(understood)}
    # планировщик состава
    if not own:
        return {**base, "short": "Импортируйте состав.", "detail": ""}
    plan = squad_plan(own, dna)
    return {**base, "short": plan["priorities"][0] if plan["priorities"] else "Явных дыр в составе нет.",
            "detail": " ".join(plan["priorities"][1:])}
