"""Модели данных матча.

Главный принцип: каждое значение, которое попадает в анализ, знает,
откуда оно взялось (какой экран / ручной ввод), насколько мы в нём уверены
и на какой минуте матча было снято. Значения без источника в анализ не идут.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Source(str, Enum):
    """Откуда пришли данные."""

    SCREEN_MATCH = "screen_match"  # экран матча (плашка счёта, статистика)
    SCREEN_TACTICS = "screen_tactics"  # экран тактики
    SCREEN_SQUAD = "screen_squad"  # панель состава / squad bar
    SCREEN_DUGOUT = "screen_dugout"  # лента dugout (сообщения штаба)
    SCREEN_ANALYSIS = "screen_analysis"  # тепловые карты, Action Zones, Pass Maps
    MANUAL = "manual"  # ручная загрузка / ввод
    CONNECTOR = "connector"  # опциональный BepInEx-коннектор
    DEMO = "demo"  # демо-сценарий


class Fatigue(str, Enum):
    """Уровень усталости. В FM это иконка/цвет, не число — храним уровень."""

    FRESH = "fresh"
    OK = "ok"
    TIRED = "tired"
    EXHAUSTED = "exhausted"
    UNKNOWN = "unknown"


Side = Literal["home", "away"]


class TeamStats(BaseModel):
    """Статистика одной команды на момент снимка. None = не видно на экране."""

    possession: float | None = Field(default=None, ge=0, le=100)
    shots: int | None = Field(default=None, ge=0)
    shots_on_target: int | None = Field(default=None, ge=0)
    xg: float | None = Field(default=None, ge=0)
    passes: int | None = Field(default=None, ge=0)
    pass_accuracy: float | None = Field(default=None, ge=0, le=100)
    tackles_won: int | None = Field(default=None, ge=0)
    tackles: int | None = Field(default=None, ge=0)
    yellow_cards: int | None = Field(default=None, ge=0)
    red_cards: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _consistent(self) -> "TeamStats":
        if self.shots is not None and self.shots_on_target is not None:
            if self.shots_on_target > self.shots:
                raise ValueError("ударов в створ больше, чем ударов")
        if self.tackles is not None and self.tackles_won is not None:
            if self.tackles_won > self.tackles:
                raise ValueError("выигранных единоборств больше, чем всего")
        return self


class PlayerState(BaseModel):
    """Игрок на поле или в запасе."""

    name: str
    position: str | None = None  # как подписано в игре, напр. «ПВ», «ЦЗ»
    role: str | None = None  # роль как подписана в игре (не выдумывается!)
    rating: float | None = Field(default=None, ge=0, le=10)
    fatigue: Fatigue = Fatigue.UNKNOWN
    yellow_card: bool = False
    injured: bool = False
    on_pitch: bool = True
    # Ключевые атрибуты, если были сняты с профиля (1–20). Пусто = неизвестно.
    attributes: dict[str, int] = Field(default_factory=dict)

    @field_validator("attributes")
    @classmethod
    def _attr_range(cls, v: dict[str, int]) -> dict[str, int]:
        for k, val in v.items():
            if not 1 <= val <= 20:
                raise ValueError(f"атрибут {k}={val} вне диапазона 1–20")
        return v


class TeamState(BaseModel):
    name: str
    formation_in_possession: str | None = None
    formation_out_of_possession: str | None = None
    stats: TeamStats = Field(default_factory=TeamStats)
    players: list[PlayerState] = Field(default_factory=list)
    bench: list[PlayerState] = Field(default_factory=list)


class Snapshot(BaseModel):
    """Один снимок состояния матча (результат разбора одного или нескольких экранов)."""

    minute: int = Field(ge=0, le=130)
    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)
    our_side: Side = "home"
    home: TeamState
    away: TeamState
    dugout_messages: list[str] = Field(default_factory=list)
    source: Source = Source.MANUAL
    confidence: float = Field(default=1.0, ge=0, le=1)

    @property
    def us(self) -> TeamState:
        return self.home if self.our_side == "home" else self.away

    @property
    def them(self) -> TeamState:
        return self.away if self.our_side == "home" else self.home

    @property
    def our_goals(self) -> int:
        return self.home_goals if self.our_side == "home" else self.away_goals

    @property
    def their_goals(self) -> int:
        return self.away_goals if self.our_side == "home" else self.home_goals

    @model_validator(mode="after")
    def _possession_sums(self) -> "Snapshot":
        a, b = self.home.stats.possession, self.away.stats.possession
        if a is not None and b is not None and abs(a + b - 100) > 1.5:
            raise ValueError(f"владение в сумме {a + b}%, ожидается 100%")
        return self


class Fact(BaseModel):
    """Проверенный факт, на который может ссылаться совет."""

    id: str
    text: str  # человекочитаемо, по-русски
    minute: int
    source: Source
    confidence: float = 1.0


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Signal(BaseModel):
    """Сработавшее правило (детектор). Без LLM, детерминированно."""

    rule_id: str
    severity: Severity
    title: str
    minute: int
    fact_ids: list[str]
    player: str | None = None


class RecommendationAction(BaseModel):
    text: str
    # Что именно менять в FM27: тип и значение настройки.
    kind: Literal["tactical_tweak", "role", "instruction", "substitution", "shout", "other"]
    setting: str | None = None


class Recommendation(BaseModel):
    """Совет по шаблону ТЗ: проблема → действия → эффект → риски."""

    id: str = ""
    minute: int
    mode: Literal["quick", "live", "head_coach"]
    problem: str
    evidence_fact_ids: list[str]
    actions: list[RecommendationAction] = Field(min_length=1, max_length=3)
    expected_effect: str
    risks: str
    confidence: Literal["low", "medium", "high"]
    missing_data: list[str] = Field(default_factory=list)
    status: Literal["new", "accepted", "rejected"] = "new"
    generated_by: Literal["llm", "rules"] = "rules"
