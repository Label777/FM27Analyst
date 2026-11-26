"""Демо-сценарий матча для проверки всей цепочки без игры.

Сценарий из ТЗ: проигрываем 0:1, соперник в низком блоке, у нас владение
~65%, но моментов почти нет; на 61-й соперник перестраивается; правый
вингер к 67-й устаёт и проседает по оценке. Имена игроков вымышленные.
"""

from __future__ import annotations

from .models import Fatigue, PlayerState, Snapshot, Source, TeamState, TeamStats

MINUTES = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 57, 61, 64, 67, 72, 77, 82, 87, 90]


def _lineup(minute: int) -> list[PlayerState]:
    rw_rating = {55: 6.9, 57: 6.8, 61: 6.6, 64: 6.4, 67: 6.2}.get(minute, 6.9 if minute < 55 else 6.1)
    rw_fatigue = Fatigue.OK
    if minute >= 61:
        rw_fatigue = Fatigue.TIRED
    if minute >= 67:
        rw_fatigue = Fatigue.EXHAUSTED
    cm_fatigue = Fatigue.TIRED if minute >= 72 else Fatigue.OK
    return [
        PlayerState(name="Ковальчук", position="ВРТ", rating=6.8, fatigue=Fatigue.FRESH),
        PlayerState(name="Мельник", position="ЛЗ", rating=6.9, fatigue=Fatigue.OK),
        PlayerState(name="Бондар", position="ЦЗ", rating=7.0, fatigue=Fatigue.OK),
        PlayerState(name="Ткач", position="ЦЗ", rating=6.7, fatigue=Fatigue.OK, yellow_card=minute >= 41),
        PlayerState(name="Шевчук", position="ПЗ", rating=6.8, fatigue=Fatigue.OK),
        PlayerState(name="Лысенко", position="ОП", rating=7.1, fatigue=Fatigue.OK),
        PlayerState(name="Гончар", position="ЦП", rating=6.9, fatigue=cm_fatigue),
        PlayerState(name="Савчук", position="ЦП", rating=7.2, fatigue=Fatigue.OK),
        PlayerState(name="Кравец", position="ЛВ", rating=6.9, fatigue=Fatigue.OK),
        PlayerState(name="Олейник", position="ПВ", rating=rw_rating, fatigue=rw_fatigue),
        PlayerState(name="Руденко", position="Ф", rating=6.6, fatigue=Fatigue.OK),
    ]


BENCH = [
    PlayerState(name="Поляков", position="ПВ", on_pitch=False, fatigue=Fatigue.FRESH,
                attributes={"acceleration": 16, "dribbling": 15, "work_rate": 14, "pace": 15, "crossing": 12}),
    PlayerState(name="Зинченко", position="ЛВ", on_pitch=False, fatigue=Fatigue.FRESH,
                attributes={"acceleration": 13, "dribbling": 14, "work_rate": 12, "pace": 13, "crossing": 14}),
    PlayerState(name="Литвин", position="ЦП", on_pitch=False, fatigue=Fatigue.FRESH,
                attributes={"passing": 14, "stamina": 15, "work_rate": 16, "decisions": 13, "vision": 12}),
    PlayerState(name="Гаврилюк", position="Ф", on_pitch=False, fatigue=Fatigue.FRESH),
]


def scenario(our_side: str = "home") -> list[Snapshot]:
    snaps = []
    for m in MINUTES:
        poss = 52 if m <= 10 else (58 if m <= 30 else 65)
        # Наш xG растёт очень медленно после гола соперника
        xg_us = round(min(m, 30) * 0.012 + max(0, m - 30) * 0.003, 2)
        xg_them = round(0.05 + (0.6 if m >= 34 else 0) + (0.55 if m >= 75 else 0) + m * 0.002, 2)
        shots_us = 2 + m // 12
        shots_them = 1 + m // 20 + (2 if m >= 75 else 0)
        them_ip = "4-3-3" if m < 61 else "4-2-3-1"
        them_oop = "4-5-1" if m < 61 else "4-4-1-1"
        dugout = []
        if m >= 61:
            dugout.append("Соперник перешёл на 4-2-3-1 и опустил линию полузащиты")
        us = TeamState(
            name="Наша команда",
            formation_in_possession="4-3-3",
            formation_out_of_possession="4-4-2",
            stats=TeamStats(possession=poss, shots=shots_us, shots_on_target=max(1, shots_us // 3), xg=xg_us,
                            passes=m * 6, pass_accuracy=86, tackles=m // 3, tackles_won=m // 5,
                            yellow_cards=1 if m >= 41 else 0, red_cards=0),
            players=_lineup(m),
            bench=[b.model_copy() for b in BENCH],
        )
        them = TeamState(
            name="Соперник",
            formation_in_possession=them_ip,
            formation_out_of_possession=them_oop,
            stats=TeamStats(possession=100 - poss, shots=shots_them, shots_on_target=max(1, shots_them // 2),
                            xg=xg_them, passes=m * 3, pass_accuracy=74, tackles=m // 2, tackles_won=m // 4,
                            yellow_cards=0, red_cards=0),
        )
        home, away = (us, them) if our_side == "home" else (them, us)
        their_goals = 1 if m >= 34 else 0
        hg, ag = (0, their_goals) if our_side == "home" else (their_goals, 0)
        snaps.append(
            Snapshot(minute=m, home_goals=hg, away_goals=ag, our_side=our_side, home=home, away=away,
                     dugout_messages=dugout, source=Source.DEMO, confidence=1.0)
        )
    return snaps
