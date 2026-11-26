from __future__ import annotations

import os

import pytest

# Тесты не должны искать игру и ставить плагин на машине разработчика.
os.environ.setdefault("FM27_NO_PLUGIN_INSTALL", "1")

from fm27_analyst.models import Fatigue, PlayerState, Snapshot, TeamState, TeamStats


def make_snap(
    minute: int,
    *,
    goals: tuple[int, int] = (0, 0),
    poss: float = 50,
    xg: tuple[float, float] = (0.0, 0.0),
    them_formation: str = "4-3-3",
    players: list[PlayerState] | None = None,
    bench: list[PlayerState] | None = None,
    dugout: list[str] | None = None,
) -> Snapshot:
    return Snapshot(
        minute=minute,
        home_goals=goals[0],
        away_goals=goals[1],
        our_side="home",
        home=TeamState(
            name="Мы",
            formation_in_possession="4-3-3",
            formation_out_of_possession="4-4-2",
            stats=TeamStats(possession=poss, xg=xg[0], shots=5, shots_on_target=2),
            players=players or [PlayerState(name="Иванов", position="ПВ", rating=7.0, fatigue=Fatigue.OK)],
            bench=bench or [],
        ),
        away=TeamState(
            name="Они",
            formation_in_possession=them_formation,
            stats=TeamStats(possession=100 - poss, xg=xg[1], shots=3, shots_on_target=1),
        ),
        dugout_messages=dugout or [],
    )


@pytest.fixture
def snap_factory():
    return make_snap
