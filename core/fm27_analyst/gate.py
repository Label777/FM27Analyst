"""Advice Gate — решает, показывать ли совет без запроса пользователя.

Правила из ТЗ: не перегружать во время матча, не менять работающую тактику
без веских причин, не повторять отклонённое, критичное — сразу.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Severity, Signal

MIN_GAP_MINUTES = 5  # не чаще одного непрошеного совета за столько игровых минут
REPEAT_AFTER = 20  # тот же сигнал можно поднять снова через столько минут


@dataclass
class AdviceGate:
    min_gap: int = MIN_GAP_MINUTES
    repeat_after: int = REPEAT_AFTER
    last_minute: int | None = None
    rejected_rules: set[str] = field(default_factory=set)
    shown: dict[str, int] = field(default_factory=dict)  # ключ сигнала -> минута показа

    def reset(self) -> None:
        self.last_minute = None
        self.rejected_rules.clear()
        self.shown.clear()

    def select(self, signals: list[Signal], minute: int) -> list[Signal]:
        """Сигналы, по которым стоит выдать совет сейчас (возможно пусто)."""
        critical = [s for s in signals if s.severity == Severity.CRITICAL and self._new(s, minute)]
        if critical:
            return critical
        if self.last_minute is not None and minute - self.last_minute < self.min_gap:
            return []
        working = any(s.rule_id == "tactic_working" for s in signals)
        actionable = []
        for s in signals:
            if s.rule_id == "tactic_working":
                continue
            # Информационные сигналы — только контекст, кроме усталости
            if s.severity == Severity.INFO and s.rule_id != "fatigue":
                continue
            if s.rule_id in self.rejected_rules or not self._new(s, minute):
                continue
            # Работающую тактику не трогаем: командные советы пропускаем,
            # индивидуальные (усталость, падение оценки) оставляем.
            if working and s.player is None:
                continue
            actionable.append(s)
        if actionable:
            # Контекст для совета: «проигрываем» усиливает тактические советы
            actionable += [s for s in signals if s.rule_id == "losing_late"]
        return actionable

    def mark_shown(self, signals: list[Signal], minute: int) -> None:
        self.last_minute = minute
        for s in signals:
            self.shown[self._key(s)] = minute

    def mark_rejected(self, rule_ids: list[str]) -> None:
        self.rejected_rules.update(rule_ids)

    @staticmethod
    def _key(s: Signal) -> str:
        return f"{s.rule_id}:{s.player or ''}"

    def _new(self, s: Signal, minute: int) -> bool:
        seen = self.shown.get(self._key(s))
        return seen is None or minute - seen >= self.repeat_after
