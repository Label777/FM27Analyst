"""Аналитик сезона (раздел 23): результаты, форма, тактики, где теряем очки.

Источник — матчи сейва: отслеженные вживую (снимки) или введённые вручную
итоги. Всё считается из сохранённых данных; если чего-то нет (xG, дата),
отчёт так и пишет.
"""

from __future__ import annotations

import random
import re
from collections import Counter, defaultdict
from statistics import mean

from .models import Fatigue, PlayerState, Snapshot, Source, TeamState, TeamStats
from .storage import SaveStore

LATE = 75


def _mode(values: list[str | None]) -> str | None:
    vals = [v for v in values if v]
    return Counter(vals).most_common(1)[0][0] if vals else None


def match_summary(m: dict, snaps: list[Snapshot]) -> dict | None:
    if not snaps:
        return None
    last = snaps[-1]
    gf, ga = last.our_goals, last.their_goals
    before_late = max((s for s in snaps if s.minute <= LATE), key=lambda s: s.minute, default=None)
    late_ga = ga - before_late.their_goals if before_late else 0
    late_gf = gf - before_late.our_goals if before_late else 0
    led = any(s.our_goals > s.their_goals for s in snaps)
    trailed = any(s.our_goals < s.their_goals for s in snaps)
    pts = 3 if gf > ga else 1 if gf == ga else 0
    us, them = last.us.stats, last.them.stats
    ratings = {p.name: p.rating for p in last.us.players if p.rating is not None}
    positions = {p.name: p.position for p in last.us.players}
    return {
        "id": m["id"], "opponent": m["opponent"], "home": m["our_side"] == "home", "game_date": m.get("game_date"),
        "gf": gf, "ga": ga, "pts": pts, "result": "W" if pts == 3 else "D" if pts == 1 else "L",
        "xg_for": us.xg, "xg_against": them.xg, "possession": us.possession,
        "our_formation": _mode([s.us.formation_in_possession for s in snaps]),
        "opp_formation": _mode([s.them.formation_in_possession for s in snaps]),
        "led": led, "trailed": trailed, "late_ga": late_ga, "late_gf": late_gf,
        "ratings": ratings, "positions": positions, "tracked": len(snaps) > 1,
    }


def load(store: SaveStore) -> list[dict]:
    out = []
    for m in sorted(store.matches(), key=lambda m: (m.get("game_date") or "", m["id"])):
        if not m["finished"]:
            continue
        s = match_summary(m, store.snapshots(m["id"]))
        if s:
            out.append(s)
    return out


def _table(ms: list[dict]) -> dict:
    n = len(ms)
    if not n:
        return {"played": 0}
    xf = [m["xg_for"] for m in ms if m["xg_for"] is not None]
    xa = [m["xg_against"] for m in ms if m["xg_against"] is not None]
    return {
        "played": n, "w": sum(m["result"] == "W" for m in ms), "d": sum(m["result"] == "D" for m in ms),
        "l": sum(m["result"] == "L" for m in ms), "gf": sum(m["gf"] for m in ms), "ga": sum(m["ga"] for m in ms),
        "pts": sum(m["pts"] for m in ms), "ppg": round(sum(m["pts"] for m in ms) / n, 2),
        "xg_for": round(sum(xf), 2) if xf else None, "xg_against": round(sum(xa), 2) if xa else None,
        "xg_diff_pm": round((sum(xf) - sum(xa)) / len(xf), 2) if xf and len(xf) == len(xa) else None,
    }


def _periods(ms: list[dict]) -> list[tuple[str, list[dict]]]:
    if all(m["game_date"] for m in ms):
        groups: dict[str, list[dict]] = defaultdict(list)
        for m in ms:
            groups[m["game_date"][:7]].append(m)
        months = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
        return [(f"{months[int(k[5:7]) - 1].capitalize()} {k[:4]}", v) for k, v in sorted(groups.items())]
    return [(f"Матчи {i + 1}–{min(i + 5, len(ms))}", ms[i:i + 5]) for i in range(0, len(ms), 5)]


def points_lost(ms: list[dict]) -> list[dict]:
    issues = []
    blown = [m for m in ms if m["led"] and m["pts"] < 3]
    if blown:
        issues.append({"id": "blown_leads", "points": sum(3 - m["pts"] for m in blown),
                       "text": f"Упущенные победы: вели в счёте в {len(blown)} матчах и не выиграли",
                       "matches": [m["opponent"] for m in blown]})
    late = [m for m in ms if m["late_ga"] > 0 and m["tracked"]]
    if late:
        cost = 0
        for m in late:
            ga_wo = m["ga"] - m["late_ga"]
            pts_wo = 3 if m["gf"] > ga_wo else 1 if m["gf"] == ga_wo else 0
            cost += pts_wo - m["pts"]
        if cost:
            issues.append({"id": "late_goals", "points": cost,
                           "text": f"Голы после {LATE}-й минуты: пропускали в {len(late)} матчах — это стоило {cost} очк.",
                           "matches": [m["opponent"] for m in late]})
    wasteful = [m for m in ms if m["xg_for"] is not None and m["xg_for"] - m["gf"] >= 1.0 and m["pts"] < 3]
    if wasteful:
        issues.append({"id": "finishing", "points": sum(3 - m["pts"] for m in wasteful) // 2 or 1,
                       "text": f"Реализация: в {len(wasteful)} матчах забили на 1+ гол меньше xG и не выиграли",
                       "matches": [m["opponent"] for m in wasteful]})
    sterile = [m for m in ms if (m["possession"] or 0) >= 60 and (m["xg_for"] or 9) < 1.0 and m["pts"] < 3]
    if sterile:
        issues.append({"id": "sterile", "points": sum(3 - m["pts"] for m in sterile),
                       "text": f"Стерильное владение: в {len(sterile)} матчей с владением 60%+ и xG меньше 1.0 без победы",
                       "matches": [m["opponent"] for m in sterile]})
    home = [m for m in ms if m["home"]]
    away = [m for m in ms if not m["home"]]
    if len(home) >= 3 and len(away) >= 3:
        ph, pa = _table(home)["ppg"], _table(away)["ppg"]
        if ph - pa >= 0.7:
            issues.append({"id": "away", "points": round((ph - pa) * len(away)),
                           "text": f"Выезд: {pa} очка за матч против {ph} дома", "matches": []})
    ids = {i["id"]: i for i in issues}
    if "blown_leads" in ids and "late_goals" in ids:
        both = set(ids["blown_leads"]["matches"]) & set(ids["late_goals"]["matches"])
        if both:
            ids["blown_leads"]["text"] += f" — в {len(both)} из них решили голы после {LATE}-й минуты (очки частично те же)"
    for i in issues:
        i["text"] = re.sub(r"\b(\d+) матчей", lambda m: f"{m.group(1)} {_plural(int(m.group(1)))}", i["text"])
    return sorted(issues, key=lambda i: -i["points"])


def _plural(n: int) -> str:
    return "матче" if n % 10 == 1 and n % 100 != 11 else "матчах"


def season_report(store: SaveStore) -> dict:
    ms = load(store)
    if not ms:
        return {"error": "Завершённых матчей в сейве нет: отслеживайте матчи помощником или введите итоги вручную"}
    total = _table(ms)
    form = "".join({"W": "В", "D": "Н", "L": "П"}[m["result"]] for m in ms[-5:])
    by_formation = []
    for f, group in defaultdict(list, {k: [m for m in ms if m["our_formation"] == k] for k in {m["our_formation"] for m in ms}}).items():
        if f:
            by_formation.append({"formation": f, **_table(group)})
    by_formation.sort(key=lambda r: -r["ppg"])
    by_opp = []
    for f in {m["opp_formation"] for m in ms if m["opp_formation"]}:
        by_opp.append({"opp_formation": f, **_table([m for m in ms if m["opp_formation"] == f])})
    by_opp.sort(key=lambda r: r["ppg"])
    low_block = [m for m in ms if (m["possession"] or 0) >= 60]
    others = [m for m in ms if (m["possession"] or 0) < 60]
    opp_types = [{"type": "Соперник отдаёт мяч (наше владение 60%+)", **_table(low_block)},
                 {"type": "Остальные матчи", **_table(others)}]
    # игроки
    rating_sum: dict[str, list[float]] = defaultdict(list)
    pos_of: dict[str, str] = {}
    for m in ms:
        for n, r in m["ratings"].items():
            rating_sum[n].append(r)
            pos_of[n] = m["positions"].get(n) or pos_of.get(n, "")
    players = sorted(({"name": n, "position": pos_of.get(n), "matches": len(v), "avg": round(mean(v), 2)}
                      for n, v in rating_sum.items() if len(v) >= 3), key=lambda x: -x["avg"])
    by_pos: dict[str, list[float]] = defaultdict(list)
    for p in players:
        by_pos[p["position"] or "?"].append(p["avg"])
    positions = sorted(({"position": k, "avg": round(mean(v), 2)} for k, v in by_pos.items()), key=lambda x: -x["avg"])
    issues = points_lost(ms)
    # что помогло: принятые советы и их итог через 15 минут
    helped: dict[str, list[float]] = defaultdict(list)
    for item in store.recommendations():
        rec, out = item["recommendation"], item["outcome"]
        if rec.status == "accepted" and out:
            helped[rec.actions[0].text.split(":")[0].split(". Почему")[0]].append(out["xg_us"] - out["xg_them"])
    changes = sorted(({"change": k, "times": len(v), "xg_diff": round(mean(v), 2)} for k, v in helped.items()),
                     key=lambda x: -x["xg_diff"])
    focus = [i["text"] for i in issues[:2]]
    if by_formation and len(by_formation) > 1 and by_formation[0]["played"] >= 3:
        b, w = by_formation[0], by_formation[-1]
        if b["ppg"] - w["ppg"] >= 0.5:
            focus.append(f"Схема {b['formation']} даёт {b['ppg']} очка за матч против {w['ppg']} у {w['formation']} — "
                         f"основной выбор на следующий месяц")
    return {
        "total": total, "form": form, "home": _table([m for m in ms if m["home"]]),
        "away": _table([m for m in ms if not m["home"]]),
        "periods": [{"title": t, **_table(g), "results": "".join({"W": "В", "D": "Н", "L": "П"}[m["result"]] for m in g)}
                    for t, g in _periods(ms)],
        "by_formation": by_formation, "by_opp_formation": by_opp, "opp_types": opp_types,
        "players": players[:8], "positions": positions, "points_lost": issues, "changes": changes,
        "next_focus": focus,
        "matches": [{k: m[k] for k in ("opponent", "home", "gf", "ga", "result", "xg_for", "xg_against", "possession",
                                       "our_formation", "opp_formation", "game_date")} for m in reversed(ms)],
        "note": "Важность игроков — по средней оценке в отслеженных матчах (не меньше 3). Влияние каждого на очки "
                "без данных о заменах точно не посчитать.",
    }


def season_answer(question: str, rep: dict) -> dict:
    q = question.lower()
    if "error" in rep:
        return {"short": rep["error"], "detail": ""}
    if "очк" in q or "теря" in q or "почему" in q and ("проигр" in q or "не выигр" in q):
        iss = rep["points_lost"]
        if not iss:
            return {"short": "Явных системных потерь очков не видно.", "detail": ""}
        return {"short": iss[0]["text"] + ".", "detail": "; ".join(i["text"] for i in iss)}
    if "игрок" in q or "важн" in q or "лидер" in q:
        p = rep["players"][:3]
        return {"short": "Лучшие по средней оценке: " + ", ".join(f"{x['name']} ({x['avg']})" for x in p) + ".",
                "detail": rep["note"]}
    if "позици" in q:
        p = rep["positions"][:3]
        return {"short": "Больше всего дают позиции: " + ", ".join(f"{x['position']} ({x['avg']})" for x in p) + ".", "detail": ""}
    if "тактик" in q or "схем" in q:
        f = rep["by_formation"]
        if not f:
            return {"short": "Схемы в матчах не записаны.", "detail": ""}
        return {"short": f"Лучше всего работает {f[0]['formation']}: {f[0]['ppg']} очка за матч.",
                "detail": "; ".join(f"{x['formation']}: {x['ppg']} очк./матч, {x['played']} матчей" for x in f)}
    if "измен" in q or "помог" in q or "улучш" in q:
        c = rep["changes"]
        if not c:
            return {"short": "Принятых советов с оценкой эффекта пока нет.", "detail": ""}
        return {"short": f"Лучше всего сработало: {c[0]['change']} (xG-баланс {c[0]['xg_diff']:+} за 15 мин).",
                "detail": "; ".join(f"{x['change']}: {x['xg_diff']:+}, раз: {x['times']}" for x in c)}
    if "исправ" in q or "месяц" in q or "дальше" in q:
        return {"short": rep["next_focus"][0] if rep["next_focus"] else "Критичных проблем нет.", "detail": "; ".join(rep["next_focus"])}
    t = rep["total"]
    return {"short": f"{t['played']} матчей: {t['w']}В {t['d']}Н {t['l']}П, {t['pts']} очков, форма {rep['form']}.",
            "detail": ""}


# --- ввод итогов и демо-сезон ---
def _team(name: str, formation: str | None, poss: float | None, goals_xg: float | None, shots: int | None,
          players: list[PlayerState] | None = None) -> TeamState:
    return TeamState(name=name, formation_in_possession=formation,
                     stats=TeamStats(possession=poss, xg=goals_xg, shots=shots,
                                     shots_on_target=(shots // 3 if shots is not None else None)),
                     players=players or [])


def add_result(store: SaveStore, opponent: str, our_side: str, gf: int, ga: int, *, game_date: str | None = None,
               xg_for: float | None = None, xg_against: float | None = None, possession: float | None = None,
               our_formation: str | None = None, opp_formation: str | None = None) -> int:
    """Итог матча вручную (без отслеживания по минутам)."""
    mid = store.start_match(opponent, our_side, game_date)
    us = _team("Мы", our_formation, possession, xg_for, None)
    them = _team(opponent, opp_formation, (100 - possession) if possession is not None else None, xg_against, None)
    home, away = (us, them) if our_side == "home" else (them, us)
    hg, ag = (gf, ga) if our_side == "home" else (ga, gf)
    store.add_snapshot(mid, Snapshot(minute=90, home_goals=hg, away_goals=ag, our_side=our_side, home=home, away=away,
                                     source=Source.MANUAL))
    store.finish_match(mid, f"{hg}:{ag}")
    return mid


DEMO_XI = [("Ковальчук", "ВРТ"), ("Мельник", "ЛЗ"), ("Бондар", "ЦЗ"), ("Ткач", "ЦЗ"), ("Шевчук", "ПЗ"),
           ("Лысенко", "ОП"), ("Гончар", "ЦП"), ("Савчук", "ЦП"), ("Кравец", "ЛВ"), ("Олейник", "ПВ"), ("Руденко", "Ф")]


def demo_season(store: SaveStore, n: int = 18, seed: int = 5) -> int:
    """Вымышленный сезон с закономерностями: поздние пропущенные голы, слабый выезд,
    4-3-3 результативнее 4-2-3-1, стерильное владение против низкого блока."""
    rng = random.Random(seed)
    opps = ["Днепровские Волки", "Атлетик Порту-Нова", "Рапид Карпаты", "Олимпик Лаго", "Спортинг Бриз",
            "Динамо Степь", "Юнайтед Харбор", "ФК Северный", "Металлург Восток"]
    for i in range(n):
        home = i % 2 == 0
        formation = "4-3-3" if i % 3 != 0 else "4-2-3-1"
        opp_form = rng.choice(["4-4-2", "4-2-3-1", "5-3-2", "4-3-3"])
        strength = (0.35 if home else -0.15) + (0.3 if formation == "4-3-3" else -0.2)
        low_block = opp_form == "5-3-2"
        poss = rng.uniform(60, 68) if low_block else rng.uniform(44, 58)
        xg_f = max(0.2, rng.gauss(1.4 + strength - (0.6 if low_block else 0), 0.35))
        xg_a = max(0.2, rng.gauss(1.1 - strength / 2, 0.3))
        gf = max(0, round(rng.gauss(xg_f - (0.3 if low_block else 0), 0.7)))
        ga_early = max(0, round(rng.gauss(xg_a * 0.7, 0.5)))
        late = 1 if rng.random() < 0.35 else 0  # склонность пропускать в концовке
        mid = store.start_match(opps[i % len(opps)], "home" if home else "away", f"2026-{8 + i // 4:02d}-{1 + (i % 4) * 7:02d}")
        for minute, frac in ((30, 0.35), (60, 0.7), (75, 0.85), (90, 1.0)):
            g_f = min(gf, round(gf * frac + 0.01))
            g_a = min(ga_early, round(ga_early * min(1.0, frac / 0.85))) + (late if minute == 90 else 0)
            players = [PlayerState(name=nm, position=pos, rating=round(min(9.5, max(5.5, rng.gauss(6.8 + (0.4 if nm in ("Савчук", "Лысенко") else 0) + (gf - g_a) * 0.15, 0.3))), 1),
                                   fatigue=Fatigue.OK) for nm, pos in DEMO_XI]
            us = _team("Наш клуб", formation, round(poss, 1), round(xg_f * frac, 2), int(6 + 10 * frac), players)
            them = _team(opps[i % len(opps)], opp_form, round(100 - poss, 1), round(xg_a * frac, 2), int(4 + 8 * frac))
            h, a = (us, them) if home else (them, us)
            hg, ag = (g_f, g_a) if home else (g_a, g_f)
            store.add_snapshot(mid, Snapshot(minute=minute, home_goals=hg, away_goals=ag, our_side="home" if home else "away",
                                             home=h, away=a, source=Source.DEMO))
        store.finish_match(mid, f"{hg}:{ag}")
    return n
