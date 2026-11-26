"""Оркестратор: снимок → изменения → факты → правила → гейт → совет → память."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .gate import AdviceGate
from .models import Fact, Recommendation, Signal, Snapshot
from .reasoner import Answer, Reasoner
from .rules import evaluate
from .storage import SaveStore
from .timeline import Change, Timeline, build_facts

OUTCOME_WINDOW = 15  # через сколько минут оцениваем эффект принятого совета


@dataclass
class TickResult:
    snapshot: Snapshot
    changes: list[Change]
    facts: list[Fact]
    signals: list[Signal]
    recommendations: list[Recommendation] = field(default_factory=list)


class Engine:
    def __init__(self, data_dir: Path, reasoner: Reasoner | None = None) -> None:
        self.data_dir = data_dir
        self.reasoner = reasoner or Reasoner()
        self.store: SaveStore | None = None
        self.match_id: int | None = None
        self.timeline = Timeline()
        self.gate = AdviceGate()
        self.last: TickResult | None = None
        self._accepted: dict[int, int] = {}  # rec_id -> минута принятия
        self._issued: set[frozenset[str]] = set()

    # --- сейвы и матчи ---
    def open_save(self, club: str, save_name: str) -> SaveStore:
        if self.store:
            self.store.close()
        self.store = SaveStore(self.data_dir / "saves", club, save_name)
        self.match_id = None
        self._reset_match_state()
        return self.store

    def start_match(self, opponent: str, our_side: str = "home") -> int:
        if not self.store:
            raise RuntimeError("Сначала выберите сохранение (клуб и название сейва)")
        if self.match_id is not None and self.timeline.latest:
            self.finish_match()
        self.match_id = self.store.start_match(opponent, our_side)
        self._reset_match_state()
        return self.match_id

    def finish_match(self) -> None:
        if self.store and self.match_id is not None and self.timeline.latest:
            s = self.timeline.latest
            self.store.finish_match(self.match_id, f"{s.home_goals}:{s.away_goals}")

    def _reset_match_state(self) -> None:
        self.timeline = Timeline()
        self.gate.reset()
        self.last = None
        self._accepted.clear()
        self._issued = set()

    # --- основной цикл ---
    def ingest(self, snap: Snapshot) -> TickResult:
        if self.store is None or self.match_id is None:
            raise RuntimeError("Нет активного матча")
        changes = self.timeline.add(snap)
        self.store.add_snapshot(self.match_id, snap)
        facts = build_facts(self.timeline, changes)
        signals = evaluate(self.timeline)
        result = TickResult(snap, changes, facts, signals)
        chosen = self.gate.select(signals, snap.minute)
        if chosen:
            recs = self.reasoner.recommend(
                self.timeline, facts, chosen, "live", self.store.memory_lines()
            )
            # Тот же набор действий в этом матче уже советовали — не повторяем
            fresh = []
            for r in recs:
                key = frozenset(a.text for a in r.actions)
                if key in self._issued:
                    continue
                self._issued.add(key)
                fresh.append(r)
            for r in fresh:
                used = [s.rule_id for s in chosen if set(s.fact_ids) & set(r.evidence_fact_ids)]
                rid = self.store.add_recommendation(self.match_id, r, used)
                r.id = str(rid)
            if fresh:
                evidence = {f for r in fresh for f in r.evidence_fact_ids}
                self.gate.mark_shown([s for s in chosen if set(s.fact_ids) & evidence], snap.minute)
            result.recommendations = fresh
        self._evaluate_outcomes(snap)
        self.last = result
        return result

    def ask(self, question: str) -> Answer:
        tl = self.timeline
        facts = self.last.facts if self.last else []
        signals = self.last.signals if self.last else []
        memory = self.store.memory_lines() if self.store else []
        return self.reasoner.answer(question, tl, facts, signals, memory)

    def head_coach_review(self) -> list[Recommendation]:
        """Глубокий разбор по запросу (перерыв, после матча): без гейта."""
        if not self.last:
            return []
        memory = self.store.memory_lines() if self.store else []
        return self.reasoner.recommend(self.timeline, self.last.facts, self.last.signals, "head_coach", memory)

    def feedback(self, rec_id: int, status: str) -> None:
        if not self.store:
            raise RuntimeError("Нет активного сейва")
        rule_ids = self.store.set_status(rec_id, status)
        if status == "rejected":
            self.gate.mark_rejected(rule_ids)
        elif status == "accepted" and self.timeline.latest:
            self._accepted[rec_id] = self.timeline.latest.minute

    def _evaluate_outcomes(self, snap: Snapshot) -> None:
        """Через 15 минут после принятия совета фиксируем, что изменилось."""
        if not self.store:
            return
        for rec_id, minute in list(self._accepted.items()):
            if snap.minute - minute < OUTCOME_WINDOW:
                continue
            base = self.timeline.at_or_before(minute)
            if base is None:
                continue
            xu0, xu1 = base.us.stats.xg, snap.us.stats.xg
            xt0, xt1 = base.them.stats.xg, snap.them.stats.xg
            outcome: dict[str, Any] = {
                "window": snap.minute - minute,
                "xg_us": round((xu1 or 0) - (xu0 or 0), 2) if xu0 is not None and xu1 is not None else 0.0,
                "xg_them": round((xt1 or 0) - (xt0 or 0), 2) if xt0 is not None and xt1 is not None else 0.0,
                "goals": f"{snap.our_goals - base.our_goals}:{snap.their_goals - base.their_goals}",
                "note": "корреляция одного матча, не доказательство",
            }
            self.store.set_outcome(rec_id, outcome)
            del self._accepted[rec_id]
