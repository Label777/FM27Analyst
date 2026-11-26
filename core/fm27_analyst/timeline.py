"""История снимков матча, превращение снимков в проверенные факты и поиск изменений.

Сравниваем состояния, а не картинки: два снимка → список изменений
(«соперник сменил схему», «за 15 минут xG соперника +0.6»).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Fact, Fatigue, PlayerState, Snapshot, Source

# Окно для трендов (игровые минуты)
WINDOW = 15
# Факты с уверенностью ниже порога в анализ не попадают
MIN_CONFIDENCE = 0.7

_FATIGUE_RU = {
    Fatigue.FRESH: "свежий",
    Fatigue.OK: "в норме",
    Fatigue.TIRED: "устал",
    Fatigue.EXHAUSTED: "сильно устал",
    Fatigue.UNKNOWN: "неизвестно",
}


def fatigue_ru(f: Fatigue) -> str:
    return _FATIGUE_RU[f]


@dataclass
class Change:
    """Изменение между двумя снимками."""

    kind: str
    text: str
    minute: int
    fact_id: str


@dataclass
class Timeline:
    snapshots: list[Snapshot] = field(default_factory=list)

    def add(self, snap: Snapshot) -> list[Change]:
        """Добавить снимок. Возвращает изменения относительно предыдущего."""
        if self.snapshots and snap.minute < self.snapshots[-1].minute:
            raise ValueError(
                f"минута {snap.minute} меньше предыдущей {self.snapshots[-1].minute}"
            )
        if self.snapshots:
            prev = self.snapshots[-1]
            if snap.home_goals < prev.home_goals or snap.away_goals < prev.away_goals:
                raise ValueError("счёт не может уменьшиться")
        prev = self.snapshots[-1] if self.snapshots else None
        self.snapshots.append(snap)
        return diff(prev, snap) if prev else []

    @property
    def latest(self) -> Snapshot | None:
        return self.snapshots[-1] if self.snapshots else None

    def at_or_before(self, minute: int) -> Snapshot | None:
        """Последний снимок не позже указанной минуты."""
        best = None
        for s in self.snapshots:
            if s.minute <= minute:
                best = s
        return best

    def xg_window(self, side: str, window: int = WINDOW) -> float | None:
        """Сколько xG набрала сторона ('us'/'them') за последние `window` минут.

        None — если нет двух снимков с xG, между которыми ≥ 5 минут.
        """
        cur = self.latest
        if cur is None:
            return None
        base = self.at_or_before(cur.minute - window)
        if base is None:
            # Начало матча: считаем от нуля, если матч идёт меньше окна
            if cur.minute <= window:
                now = _team(cur, side).stats.xg
                return round(now, 2) if now is not None else None
            base = self.snapshots[0]
        if cur.minute - base.minute < 5:
            return None
        a = _team(base, side).stats.xg
        b = _team(cur, side).stats.xg
        if a is None or b is None:
            return None
        return round(b - a, 2)

    def rating_trend(self, name: str, points: int = 3) -> list[float]:
        """Оценки игрока по последним снимкам (только где оценка видна)."""
        out: list[float] = []
        for s in self.snapshots:
            p = _find(s.us.players, name)
            if p and p.rating is not None:
                out.append(p.rating)
        return out[-points:]


def _team(s: Snapshot, side: str):
    return s.us if side == "us" else s.them


def _find(players: list[PlayerState], name: str) -> PlayerState | None:
    for p in players:
        if p.name == name:
            return p
    return None


def diff(prev: Snapshot, cur: Snapshot) -> list[Change]:
    m = cur.minute
    out: list[Change] = []
    if (cur.home_goals, cur.away_goals) != (prev.home_goals, prev.away_goals):
        out.append(Change("score", f"Счёт изменился: {cur.home_goals}:{cur.away_goals}", m, f"score@{m}"))
    for who, side in (("Наша команда", "us"), ("Соперник", "them")):
        a, b = _team(prev, side), _team(cur, side)
        for attr, what in (
            ("formation_in_possession", "схема в владении"),
            ("formation_out_of_possession", "схема без мяча"),
        ):
            old, new = getattr(a, attr), getattr(b, attr)
            if old and new and old != new:
                out.append(
                    Change(f"formation_{side}", f"{who}: {what} {old} → {new}", m, f"{attr}_{side}@{m}")
                )
    for p in cur.us.players:
        old = _find(prev.us.players, p.name)
        if old and old.on_pitch and not p.on_pitch:
            out.append(Change("sub", f"{p.name} покинул поле", m, f"sub:{p.name}@{m}"))
        if old and old.fatigue != p.fatigue and p.fatigue in (Fatigue.TIRED, Fatigue.EXHAUSTED):
            out.append(
                Change("fatigue", f"{p.name}: усталость — {fatigue_ru(p.fatigue)}", m, f"fatigue:{p.name}@{m}")
            )
        if old and not old.injured and p.injured:
            out.append(Change("injury", f"{p.name}: травма", m, f"injury:{p.name}@{m}"))
    new_msgs = [x for x in cur.dugout_messages if x not in prev.dugout_messages]
    for i, msg in enumerate(new_msgs):
        out.append(Change("dugout", f"Штаб: {msg}", m, f"dugout:{i}@{m}"))
    return out


def build_facts(tl: Timeline, changes: list[Change] | None = None) -> list[Fact]:
    """Факты из последнего снимка и трендов. Только то, что реально видно."""
    s = tl.latest
    if s is None:
        return []
    src: Source = s.source
    m = s.minute
    conf = s.confidence
    facts: list[Fact] = []

    def add(fid: str, text: str) -> None:
        facts.append(Fact(id=fid, text=text, minute=m, source=src, confidence=conf))

    add(f"score@{m}", f"{m}' — счёт {s.home.name} {s.home_goals}:{s.away_goals} {s.away.name}")
    us, them = s.us.stats, s.them.stats
    if us.possession is not None:
        add(f"possession@{m}", f"Владение: мы {us.possession:.0f}%, соперник {100 - us.possession:.0f}%")
    if us.xg is not None and them.xg is not None:
        add(f"xg@{m}", f"xG за матч: мы {us.xg:.2f}, соперник {them.xg:.2f}")
    if us.shots is not None and them.shots is not None:
        sot = ""
        if us.shots_on_target is not None and them.shots_on_target is not None:
            sot = f" (в створ {us.shots_on_target} и {them.shots_on_target})"
        add(f"shots@{m}", f"Удары: мы {us.shots}, соперник {them.shots}{sot}")
    if us.pass_accuracy is not None:
        add(f"passacc@{m}", f"Точность передач у нас {us.pass_accuracy:.0f}%")
    for side, label in (("us", "мы"), ("them", "соперник")):
        w = tl.xg_window(side)
        if w is not None:
            add(f"xg_window_{side}@{m}", f"xG за последние {WINDOW} мин: {label} {w:.2f}")
    t = s.them
    if t.formation_in_possession or t.formation_out_of_possession:
        add(
            f"formation_them@{m}",
            f"Схема соперника: {t.formation_in_possession or '?'} в владении / "
            f"{t.formation_out_of_possession or '?'} без мяча",
        )
    o = s.us
    if o.formation_in_possession or o.formation_out_of_possession:
        add(
            f"formation_us@{m}",
            f"Наша схема: {o.formation_in_possession or '?'} в владении / "
            f"{o.formation_out_of_possession or '?'} без мяча",
        )
    for p in s.us.players:
        if not p.on_pitch:
            continue
        parts = []
        if p.position:
            parts.append(p.position)
        if p.role:
            parts.append(p.role)
        head = f"{p.name} ({', '.join(parts)})" if parts else p.name
        bits = []
        if p.rating is not None:
            trend = tl.rating_trend(p.name)
            if len(trend) >= 2:
                bits.append("оценка " + " → ".join(f"{r:.1f}" for r in trend))
            else:
                bits.append(f"оценка {p.rating:.1f}")
        if p.fatigue != Fatigue.UNKNOWN:
            bits.append(f"усталость: {fatigue_ru(p.fatigue)}")
        if p.yellow_card:
            bits.append("жёлтая карточка")
        if p.injured:
            bits.append("травма")
        if bits:
            add(f"player:{p.name}@{m}", f"{head}: {', '.join(bits)}")
    for p in s.us.bench:
        if p.attributes:
            attrs = ", ".join(f"{k} {v}" for k, v in sorted(p.attributes.items()))
            add(f"bench:{p.name}@{m}", f"Запасной {p.name} ({p.position or '?'}): {attrs}")
        else:
            add(f"bench:{p.name}@{m}", f"Запасной {p.name} ({p.position or '?'}), атрибуты не сняты")
    for ch in changes or []:
        facts.append(Fact(id=ch.fact_id, text=ch.text, minute=ch.minute, source=src, confidence=conf))
    return [f for f in facts if f.confidence >= MIN_CONFIDENCE]
