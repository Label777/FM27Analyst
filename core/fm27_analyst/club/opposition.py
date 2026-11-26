"""Разведка соперника (раздел 18) по выгрузке его состава и истории матчей.

Факты (атрибуты из выгрузки, результаты прошлых матчей) отделены от
тактических гипотез (вероятная схема, где атаковать, как нейтрализовать).
Стиль владения, прессинг и высоту линии выгрузка состава не показывает —
для них нужен экран превью/анализа соперника (этап 3) или прошлые матчи.
"""

from __future__ import annotations

from .. import reference as ref
from .db import ClubDNA
from .fit import best_fit, formation_slots, profiles_data
from .importer import ScoutPlayer
from .squad import squad_plan
from .values import POSITION_RU

SIDE_OPP = {"L": "R", "R": "L"}


def guess_lineup(players: list[ScoutPlayer], dna: ClubDNA) -> tuple[list[str], list[dict]]:
    """Схемы, под которые состав соперника закрывается лучше всего (гипотеза). Первая — основная."""
    results = []
    for name in profiles_data()["formations"]:
        slots = formation_slots(name)
        pairs = []
        for i, (code, label) in enumerate(slots):
            for p in players:
                if code in p.positions:
                    fr = best_fit(p, dna, code)
                    if fr and fr.score is not None:
                        pairs.append((fr.score, i, p, code, label))
        pairs.sort(key=lambda x: -x[0])
        used_p, used_s, xi = set(), set(), []
        for score, i, p, code, label in pairs:
            if i in used_s or p.key in used_p:
                continue
            used_s.add(i)
            used_p.add(p.key)
            xi.append({"slot": i, "code": code, "label": label, "player": p, "fit": score})
        total = sum(x["fit"] for x in xi) - 40 * (len(slots) - len(xi))
        results.append((total, name, sorted(xi, key=lambda x: x["slot"])))
    results.sort(key=lambda r: -r[0])
    if not results:
        return ["?"], []
    top = results[0][0]
    close = [r[1] for r in results if r[0] >= top - abs(top) * 0.03]
    return close[:2], results[0][2]


def speed(p: ScoutPlayer) -> float | None:
    vals = [v for v in (p.attr("pace"), p.attr("acceleration")) if v is not None]
    return sum(vals) / len(vals) if vals else None


def _a(p: ScoutPlayer, key: str) -> float | None:
    return p.attr(key)


def _fmt(p: ScoutPlayer, keys: list[str]) -> str:
    return ", ".join(f"{ref.attr_ru(k)} {p.attr(k):g}" for k in keys if p.attr(k) is not None)


def opposition_report(name: str, opp: list[ScoutPlayer], own: list[ScoutPlayer], dna: ClubDNA,
                      past: list[dict] | None = None) -> dict:
    formations, xi = guess_lineup(opp, dna)
    facts: list[str] = []
    hyps: list[dict] = []
    # --- ключевые игроки ---
    key_players = sorted(xi, key=lambda x: -x["fit"])[:3]
    key_out = []
    for x in key_players:
        p = x["player"]
        fr = best_fit(p, dna, x["code"])
        key_out.append({"name": p.name, "position": POSITION_RU.get(x["code"], x["code"]), "fit": x["fit"],
                        "strengths": fr.strengths if fr else []})
        facts.append(f"{p.name} ({POSITION_RU.get(x['code'], x['code'])}): " + (", ".join(fr.strengths) if fr and fr.strengths else "сильных сторон ≥14 нет"))
    # --- наши основные ---
    plan = squad_plan(own, dna) if own else None
    ours: dict[str, ScoutPlayer] = {}
    if plan:
        by_name = {p.name: p for p in own}
        for s in plan["slots"]:
            for r in s["starters"]:
                ours.setdefault(s["code"], by_name[r["name"]])
    # --- их оборона против наших атакующих ---
    defenders = [x for x in xi if x["code"] in ("D_C", "D_L", "D_R", "WB_L", "WB_R")]
    for x in defenders:
        p = x["player"]
        pace = speed(p)
        air = min(filter(None, [_a(p, "heading"), _a(p, "jumping_reach")]), default=None)
        where = POSITION_RU.get(x["code"], x["code"])
        if pace is not None and pace <= 11:
            facts.append(f"{p.name} ({where}): {_fmt(p, ['pace', 'acceleration'])}")
            # кто из наших может это использовать
            side = x["code"][-1] if "_" in x["code"] else None
            attackers = []
            if side in ("L", "R"):
                attackers = [ours.get(f"AM_{SIDE_OPP[side]}"), ours.get(f"M_{SIDE_OPP[side]}")]
            attackers += [ours.get("ST")]
            fast = [a for a in attackers if a and (speed(a) or 0) >= 14]
            if not fast:
                hyps.append({"type": "attack", "text": f"{where} соперника {p.name} медленный, но быстрых атакующих "
                             "в нашей основе нет — использовать забегания за спину полузащитников", "based_on": [p.name]})
            if fast:
                a = fast[0]
                direction = {"L": "правый", "R": "левый"}.get(side or "", "центр")
                hyps.append({"type": "attack", "text":
                             f"{where} соперника {p.name} медленный — атаковать "
                             + (f"через {direction} фланг " if side in ("L", "R") else "за спину защитников ")
                             + f"скоростью {a.name} ({_fmt(a, ['pace', 'acceleration'])})",
                             "based_on": [p.name, a.name]})
        if x["code"] == "D_C" and air is not None and air <= 11:
            st = ours.get("ST")
            if st and (st.attr("heading") or 0) >= 14:
                hyps.append({"type": "attack", "text": f"{p.name} слаб в воздухе ({_fmt(p, ['heading', 'jumping_reach'])}) — "
                             f"навесы на {st.name} ({_fmt(st, ['heading'])})", "based_on": [p.name, st.name]})
    # --- их угрозы против нашей обороны ---
    threats = [x for x in xi if x["code"] in ("AM_L", "AM_R", "M_L", "M_R", "ST", "AM_C")]
    for x in threats:
        p = x["player"]
        sp = speed(p) or 0
        drib = _a(p, "dribbling") or 0
        fin = _a(p, "finishing") or 0
        if sp >= 15 or drib >= 15 or (x["code"] == "ST" and fin >= 15):
            facts.append(f"Угроза — {p.name} ({POSITION_RU.get(x['code'], x['code'])}): {_fmt(p, ['pace', 'acceleration', 'dribbling', 'finishing'])}")
            side = x["code"][-1] if x["code"][-1] in "LR" and "_" in x["code"] else None
            opp_def = ours.get(f"D_{SIDE_OPP[side]}") if side else ours.get("D_C")
            if opp_def:
                d_speed = speed(opp_def) or 0
                gap = sp - d_speed
                txt = (f"{p.name} против нашего {opp_def.name} ({_fmt(opp_def, ['pace', 'acceleration'])})"
                       + (f": разница в скорости {gap:+g} — " if gap > 0 else ": ")
                       + (("не оставлять один в один, подстраховка опорником с этой стороны, не играть высоко на этом фланге"
                           if side else "не держать слишком высокую линию, опорник прикрывает зону перед защитниками")
                          if gap >= 2 else "держать дистанцию и закрывать удобную ногу"))
                hyps.append({"type": "defend", "text": txt, "based_on": [p.name, opp_def.name]})
    # --- стандарты ---
    aerial = [p for p in opp if (p.attr("heading") or 0) >= 15 and (p.attr("jumping_reach") or 0) >= 14]
    takers = [p for p in opp if (p.attr("corners") or 0) >= 15 or (p.attr("free_kicks") or 0) >= 15]
    set_pieces = []
    if aerial:
        set_pieces.append("Сильны в воздухе: " + "; ".join(f"{p.name} ({_fmt(p, ['heading', 'jumping_reach'])})" for p in aerial[:3]))
    if takers:
        set_pieces.append("Исполнители стандартов: " + "; ".join(f"{p.name} ({_fmt(p, ['corners', 'free_kicks'])})" for p in takers[:2]))
    if aerial:
        our_air = sorted((p for code, p in ours.items() if code != "GK" and p.attr("heading") is not None),
                         key=lambda p: p.attr("heading"))
        if our_air and our_air[0].attr("heading") <= 11:
            hyps.append({"type": "set_piece", "text": f"На угловых не оставлять {our_air[0].name} ({_fmt(our_air[0], ['heading'])}) "
                         f"против {aerial[0].name} — опекать его сильнейшим в воздухе", "based_on": [our_air[0].name, aerial[0].name]})
    # --- прошлые матчи ---
    past_out = []
    for m in past or []:
        past_out.append(m)
    if past_out:
        facts.append(f"Прошлые матчи с этим соперником в сейве: {len(past_out)}")
    style_unknown = ["Стиль владения и прессинга", "Высота линии обороны", "Направления атак и типичные комбинации"]
    return {
        "opponent": name,
        "formation_guess": formations[0],
        "formation_alternatives": formations[1:],
        "formation_text": formations[0] + (f" или {formations[1]} — по составу неоднозначно, подтвердите по превью матча"
                                            if len(formations) > 1 else " — гипотеза по составу, подтвердите по превью"),
        "lineup_guess": [{"label": x["label"], "position": POSITION_RU.get(x["code"], x["code"]), "name": x["player"].name,
                          "fit": x["fit"]} for x in xi],
        "key_players": key_out,
        "facts": facts,
        "hypotheses": hyps,
        "set_pieces": set_pieces or ["Явной угрозы на стандартах по атрибутам нет"],
        "past_matches": past_out,
        "unknown": style_unknown,
        "note": "Факты — из выгрузки состава соперника. Схема, состав и выводы — гипотезы помощника: проверьте по превью "
                "матча в FM27. Стиль игры соперника по выгрузке не определить — нужен экран превью/анализа (этап 3).",
    }
