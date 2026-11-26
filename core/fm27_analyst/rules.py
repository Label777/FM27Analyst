"""Детекторы ситуаций без LLM.

Каждое правило смотрит только на проверенные данные таймлайна и возвращает
сигнал со ссылками на факты. Пороговые значения вынесены в константы,
чтобы их можно было калибровать на записанных матчах (этап 4).
"""

from __future__ import annotations

from .models import Fatigue, Severity, Signal
from .timeline import WINDOW, Timeline, fatigue_ru

STERILE_POSSESSION_MIN = 60.0  # % владения
STERILE_XG_WINDOW_MAX = 0.20  # xG за окно
XG_SURGE_MIN = 0.50  # xG соперника за окно
RATING_DROP = 0.4
RATING_LOW = 6.4
YELLOW_RISK_UNTIL = 70
LATE_GAME = 60
FATIGUE_FROM = 55


def evaluate(tl: Timeline) -> list[Signal]:
    s = tl.latest
    if s is None:
        return []
    m = s.minute
    out: list[Signal] = []
    us, them = s.us.stats, s.them.stats
    xg_us = tl.xg_window("us")
    xg_them = tl.xg_window("them")

    # 1. Стерильное владение: мяч у нас, моментов нет
    if (
        m >= 20
        and us.possession is not None
        and us.possession >= STERILE_POSSESSION_MIN
        and xg_us is not None
        and xg_us < STERILE_XG_WINDOW_MAX
    ):
        out.append(
            Signal(
                rule_id="sterile_possession",
                severity=Severity.WARNING,
                title=f"Владение {us.possession:.0f}%, но за {WINDOW} мин xG всего {xg_us:.2f}",
                minute=m,
                fact_ids=[f"possession@{m}", f"xg_window_us@{m}"],
            )
        )

    # 2. Соперник резко прибавил в опасности
    if xg_them is not None and xg_them >= XG_SURGE_MIN and (xg_us is None or xg_them >= 2 * max(xg_us, 0.05)):
        out.append(
            Signal(
                rule_id="xg_against_surge",
                severity=Severity.WARNING,
                title=f"Соперник создал {xg_them:.2f} xG за {WINDOW} мин",
                minute=m,
                fact_ids=[f"xg_window_them@{m}"] + ([f"xg_window_us@{m}"] if xg_us is not None else []),
            )
        )

    # 3. Проигрываем во второй половине матча
    if m >= LATE_GAME and s.our_goals < s.their_goals:
        out.append(
            Signal(
                rule_id="losing_late",
                severity=Severity.INFO,
                title=f"Проигрываем {s.our_goals}:{s.their_goals} на {m}-й минуте",
                minute=m,
                fact_ids=[f"score@{m}"],
            )
        )

    # 4. Тактика работает — не трогать без веских причин
    if (
        s.our_goals >= s.their_goals
        and xg_us is not None
        and xg_them is not None
        and xg_us > xg_them
    ):
        out.append(
            Signal(
                rule_id="tactic_working",
                severity=Severity.INFO,
                title=f"Тактика работает: за {WINDOW} мин xG {xg_us:.2f} против {xg_them:.2f}",
                minute=m,
                fact_ids=[f"score@{m}", f"xg_window_us@{m}", f"xg_window_them@{m}"],
            )
        )

    # 5. Изменение схемы соперника (по снимкам или по сообщению штаба)
    if len(tl.snapshots) >= 2:
        prev = tl.snapshots[-2]
        for attr in ("formation_in_possession", "formation_out_of_possession"):
            old, new = getattr(prev.them, attr), getattr(s.them, attr)
            if old and new and old != new:
                out.append(
                    Signal(
                        rule_id="opponent_formation_change",
                        severity=Severity.WARNING,
                        title=f"Соперник перестроился: {old} → {new}",
                        minute=m,
                        fact_ids=[f"{attr}_them@{m}"],
                    )
                )
                break

    # 6–9. Игроки
    for p in s.us.players:
        if not p.on_pitch:
            continue
        fid = f"player:{p.name}@{m}"
        if p.injured:
            out.append(
                Signal(rule_id="injury", severity=Severity.CRITICAL, title=f"{p.name}: травма", minute=m,
                       fact_ids=[fid], player=p.name)
            )
            continue
        if m >= FATIGUE_FROM and p.fatigue in (Fatigue.TIRED, Fatigue.EXHAUSTED):
            sev = Severity.WARNING if p.fatigue == Fatigue.EXHAUSTED else Severity.INFO
            out.append(
                Signal(rule_id="fatigue", severity=sev, title=f"{p.name}: {fatigue_ru(p.fatigue)}", minute=m,
                       fact_ids=[fid], player=p.name)
            )
        trend = tl.rating_trend(p.name)
        if len(trend) >= 3 and trend[0] - trend[-1] >= RATING_DROP - 1e-6 and trend[-1] <= RATING_LOW + 1e-6:
            out.append(
                Signal(
                    rule_id="rating_drop",
                    severity=Severity.WARNING,
                    title=f"{p.name}: оценка падает {trend[0]:.1f} → {trend[-1]:.1f}",
                    minute=m,
                    fact_ids=[fid],
                    player=p.name,
                )
            )
        if p.yellow_card and m < YELLOW_RISK_UNTIL:
            out.append(
                Signal(rule_id="yellow_risk", severity=Severity.INFO,
                       title=f"{p.name} с жёлтой — риск удаления, впереди {90 - m} мин", minute=m,
                       fact_ids=[fid], player=p.name)
            )
    return out


def substitution_candidates(signals: list[Signal]) -> list[str]:
    """Игроки, которых правила считают кандидатами на замену (усталость + падение оценки)."""
    by_player: dict[str, set[str]] = {}
    for sig in signals:
        if sig.player:
            by_player.setdefault(sig.player, set()).add(sig.rule_id)
    out = []
    for name, rules in by_player.items():
        if "injury" in rules or ({"fatigue", "rating_drop"} <= rules):
            out.append(name)
    return out
