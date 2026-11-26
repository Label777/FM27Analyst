"""Советы по правилам (без LLM).

Работает всегда, даже без ключа API: превращает сработавшие сигналы в
рекомендацию по шаблону ТЗ. LLM-советник (reasoner.py) использует эти же
сигналы, но формулирует глубже; при сбое LLM возвращаемся сюда.
"""

from __future__ import annotations

from . import reference as ref
from .models import Fatigue, PlayerState, Recommendation, RecommendationAction, Signal, Snapshot
from .timeline import Timeline


def _tweak_action(tid: str, why: str) -> RecommendationAction:
    t = ref.tweak(tid)
    return RecommendationAction(
        text=f"Тактическая правка «{t['name_ru']}»: {why}",
        kind="tactical_tweak",
        setting=tid,
    )


def pick_substitute(starter: PlayerState, bench: list[PlayerState]) -> tuple[PlayerState | None, str]:
    """Лучший запасной на ту же линию по профилю атрибутов. Возвращает (игрок, объяснение)."""
    group = ref.position_group(starter.position)
    same_line = [p for p in bench if not p.injured and ref.position_group(p.position) == group] if group else []
    if not same_line:
        return None, "на скамейке нет игрока той же линии — нужен скриншот запасных"
    profile = ref.sub_profile(group or "")
    known = [p for p in same_line if p.attributes]
    if not known or not profile:
        p = same_line[0]
        return p, f"{p.name} — единственный вариант той же линии; атрибуты не сняты, выбор без сравнения"

    def score(p: PlayerState) -> float:
        vals = [p.attributes[a] for a in profile if a in p.attributes]
        return sum(vals) / len(vals) if vals else 0.0

    best = max(known, key=score)
    shown = [a for a in profile if a in best.attributes][:3]
    attrs = ", ".join(f"{ref.attr_ru(a)} {best.attributes[a]}" for a in shown)
    why = f"{best.name}: {attrs}"
    if len(known) > 1:
        why += f" — лучший средний профиль среди {len(known)} запасных этой линии"
    return best, why


def _sub_rec(snap: Snapshot, sig: Signal, related: list[Signal], mode: str) -> Recommendation | None:
    starter = next((p for p in snap.us.players if p.name == sig.player), None)
    if starter is None:
        return None
    sub, why = pick_substitute(starter, snap.us.bench)
    ids = sorted({f for s in related for f in s.fact_ids})
    if sub:
        ids.append(f"bench:{sub.name}@{snap.minute}")
    reasons = "; ".join(s.title for s in related)
    if sub is None:
        return Recommendation(
            minute=snap.minute, mode=mode, problem=reasons, evidence_fact_ids=ids,
            actions=[RecommendationAction(text=f"Готовить замену для {starter.name}", kind="substitution")],
            expected_effect="Сохранить интенсивность на позиции",
            risks="Без данных о запасных выбор вслепую",
            confidence="low", missing_data=["Скриншот скамейки запасных с позициями"],
        )
    return Recommendation(
        minute=snap.minute,
        mode=mode,
        problem=reasons,
        evidence_fact_ids=ids,
        actions=[
            RecommendationAction(
                text=f"Заменить {starter.name} на {sub.name}. Почему он: {why}",
                kind="substitution",
                setting=f"{starter.name}->{sub.name}",
            )
        ],
        expected_effect="Свежие ноги на позиции, где игрок перестал выполнять роль",
        risks="Минус одна замена; если матч уйдёт в овертайм, вариантов меньше",
        confidence="medium" if sub.attributes else "low",
        missing_data=[] if sub.attributes else [f"Профиль {sub.name} (атрибуты)"],
    )


def build(tl: Timeline, signals: list[Signal], mode: str = "live") -> list[Recommendation]:
    snap = tl.latest
    if snap is None or not signals:
        return []
    recs: list[Recommendation] = []
    by_id = {s.rule_id: s for s in signals}
    m = snap.minute

    if "sterile_possession" in by_id:
        s = by_id["sterile_possession"]
        ids = list(s.fact_ids)
        losing = "losing_late" in by_id
        if losing:
            ids += by_id["losing_late"].fact_ids
        actions = [_tweak_action("exploit_width", "растянуть блок соперника и открыть зоны между линиями")]
        if losing:
            actions.append(_tweak_action("increase_urgency", "быстрее вертикальные передачи, пока есть время"))
        recs.append(
            Recommendation(
                minute=m, mode=mode,
                problem="Команда контролирует мяч, но почти не создаёт моментов"
                + (" и проигрывает" if losing else ""),
                evidence_fact_ids=ids,
                actions=actions,
                expected_effect="Больше атак через фланги и вариантов для продвижения вперёд",
                risks="Выше уязвимость к контратакам: меньше игроков в центре при потере",
                confidence="medium",
                missing_data=["Экран тактики: роли наших полузащитников — для совета по ролям"],
            )
        )

    if "xg_against_surge" in by_id and "sterile_possession" not in by_id:
        s = by_id["xg_against_surge"]
        actions = []
        if snap.our_goals > snap.their_goals:
            actions.append(_tweak_action("reduce_press", "удержать компактность и сберечь силы"))
        else:
            actions.append(RecommendationAction(
                text="Открыть экран Action Zones/тепловую карту: найти фланг, через который идут атаки",
                kind="other"))
        recs.append(
            Recommendation(
                minute=m, mode=mode, problem=s.title, evidence_fact_ids=s.fact_ids, actions=actions,
                expected_effect="Снизить качество моментов соперника",
                risks="Меньше давления на чужую оборону",
                confidence="low",
                missing_data=["Тепловая карта / Action Zones соперника"],
            )
        )

    if "opponent_formation_change" in by_id:
        s = by_id["opponent_formation_change"]
        recs.append(
            Recommendation(
                minute=m, mode=mode, problem=s.title, evidence_fact_ids=s.fact_ids,
                actions=[RecommendationAction(
                    text="Сделать снимок через 5 минут: сравню, где у соперника появился лишний игрок",
                    kind="other")],
                expected_effect="Понять, какую зону соперник усилил, прежде чем менять тактику",
                risks="Реакция на перестроение откладывается на несколько минут",
                confidence="medium",
                missing_data=["Средние позиции соперника после перестроения"],
            )
        )

    # Замены: травма — всегда; усталость — если есть сигнал
    done: set[str] = set()
    for sig in signals:
        if not sig.player or sig.player in done:
            continue
        related = [x for x in signals if x.player == sig.player]
        rules = {x.rule_id for x in related}
        exhausted = any(p.name == sig.player and p.fatigue == Fatigue.EXHAUSTED for p in snap.us.players)
        needs_sub = (
            "injury" in rules
            or "rating_drop" in rules
            or ("fatigue" in rules and (exhausted or m >= 70))
        )
        if needs_sub:
            r = _sub_rec(snap, sig, related, mode)
            if r:
                recs.append(r)
                done.add(sig.player)
        elif "yellow_risk" in rules:
            recs.append(
                Recommendation(
                    minute=m, mode=mode, problem=sig.title, evidence_fact_ids=sig.fact_ids,
                    actions=[RecommendationAction(
                        text=f"Индивидуальная инструкция для {sig.player}: осторожнее в отборе", kind="instruction")],
                    expected_effect="Снизить риск второй жёлтой",
                    risks="Меньше агрессии в единоборствах на этом участке",
                    confidence="medium",
                )
            )
            done.add(sig.player)
    return recs
