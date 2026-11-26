"""Общая база клуба (в файле сейва): игроки, импорты, ДНК клуба, шорт-лист."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import date

from pydantic import BaseModel, Field

from .importer import ImportResult, ScoutPlayer

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    scope TEXT NOT NULL,
    name TEXT NOT NULL,
    data TEXT NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(key, scope)
);
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file TEXT NOT NULL,
    scope TEXT NOT NULL,
    rows INTEGER NOT NULL,
    warnings TEXT NOT NULL,
    imported_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS attribute_history (
    player_key TEXT NOT NULL,
    taken_at REAL NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS club_dna (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS shortlist (player_id INTEGER PRIMARY KEY, note TEXT, added_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS meta_opp (scope TEXT PRIMARY KEY, name TEXT NOT NULL);
"""


class ClubDNA(BaseModel):
    """Философия клуба (раздел 24). Всё задаёт пользователь — помощник не угадывает."""

    formation: str = "4-2-3-1"
    style: list[str] = Field(default_factory=list)  # high_press, possession, counter, high_line, high_fullbacks, low_block
    max_signing_age: int | None = None  # возрастная политика
    prefer_young: bool = False
    transfer_budget: float | None = None
    wage_budget_week: float | None = None  # лимит зарплаты одного игрока в неделю
    wage_budget_total_week: float | None = None  # зарплатный бюджет клуба в неделю
    currency: str = "EUR"
    preferred_traits: list[str] = Field(default_factory=list)  # атрибуты, которые клуб ценит
    youth_policy: str | None = None
    game_date: date | None = None  # текущая дата в сейве — для контрактов
    notes: str | None = None


class ClubDB:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db
        self.db.executescript(SCHEMA)
        # миграция старых баз: игровая дата импорта (для динамики развития)
        for table in ("imports", "attribute_history"):
            cols = {r[1] for r in self.db.execute(f"PRAGMA table_info({table})")}
            if "game_date" not in cols:
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN game_date TEXT")
        self.db.commit()

    # --- импорт ---
    def save_import(self, res: ImportResult, scope: str, file: str, replace_scope: bool = False,
                    game_date: date | None = None) -> dict:
        now = time.time()
        gd = (game_date or self.dna().game_date)
        gd_s = gd.isoformat() if gd else None
        if replace_scope:
            self.db.execute("DELETE FROM players WHERE scope=?", (scope,))
        added = updated = 0
        for p in res.players:
            p.scope = scope
            row = self.db.execute("SELECT id FROM players WHERE key=? AND scope=?", (p.key, scope)).fetchone()
            data = p.model_dump_json(exclude={"id"})
            if row:
                self.db.execute("UPDATE players SET data=?, name=?, updated_at=? WHERE id=?", (data, p.name, now, row[0]))
                updated += 1
            else:
                self.db.execute(
                    "INSERT INTO players (key, scope, name, data, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (p.key, scope, p.name, data, now),
                )
                added += 1
            if p.attributes:
                self.db.execute(
                    "INSERT INTO attribute_history (player_key, taken_at, data, game_date) VALUES (?, ?, ?, ?)",
                    (p.key, now, json.dumps({k: list(v) for k, v in p.attributes.items()}), gd_s),
                )
        self.db.execute(
            "INSERT INTO imports (file, scope, rows, warnings, imported_at, game_date) VALUES (?, ?, ?, ?, ?, ?)",
            (file, scope, len(res.players), json.dumps(res.warnings, ensure_ascii=False), now, gd_s),
        )
        self.db.commit()
        return {"added": added, "updated": updated, "warnings": res.warnings, "unmapped": res.unmapped}

    def imports(self) -> list[dict]:
        rows = self.db.execute("SELECT id, file, scope, rows, warnings, imported_at FROM imports ORDER BY id DESC").fetchall()
        return [
            {"id": r[0], "file": r[1], "scope": r[2], "rows": r[3], "warnings": json.loads(r[4]), "imported_at": r[5]}
            for r in rows
        ]

    # --- игроки ---
    def players(self, scope: str | None = None) -> list[ScoutPlayer]:
        q, args = "SELECT id, data FROM players", ()
        if scope:
            q, args = q + " WHERE scope=?", (scope,)
        out = []
        for pid, data in self.db.execute(q + " ORDER BY id", args).fetchall():
            p = ScoutPlayer.model_validate_json(data)
            p.id = pid
            out.append(p)
        return out

    def player(self, pid: int) -> ScoutPlayer | None:
        row = self.db.execute("SELECT id, data FROM players WHERE id=?", (pid,)).fetchone()
        if not row:
            return None
        p = ScoutPlayer.model_validate_json(row[1])
        p.id = row[0]
        return p

    def attribute_history_full(self, key: str) -> list[dict]:
        """Снимки атрибутов игрока: время импорта, дата в сейве (если была задана), значения."""
        rows = self.db.execute(
            "SELECT taken_at, game_date, data FROM attribute_history WHERE player_key=? ORDER BY taken_at", (key,)
        ).fetchall()
        return [{"taken_at": t, "game_date": date.fromisoformat(g) if g else None,
                 "attrs": {k: tuple(v) for k, v in json.loads(d).items()}} for t, g, d in rows]

    def scopes(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT DISTINCT scope FROM players ORDER BY scope").fetchall()]

    def attribute_history(self, key: str) -> list[tuple[float, dict]]:
        rows = self.db.execute(
            "SELECT taken_at, data FROM attribute_history WHERE player_key=? ORDER BY taken_at", (key,)
        ).fetchall()
        return [(t, json.loads(d)) for t, d in rows]

    # --- ДНК клуба ---
    def dna(self) -> ClubDNA:
        row = self.db.execute("SELECT data FROM club_dna WHERE id=1").fetchone()
        return ClubDNA.model_validate_json(row[0]) if row else ClubDNA()

    def set_dna(self, dna: ClubDNA) -> None:
        self.db.execute("INSERT OR REPLACE INTO club_dna (id, data) VALUES (1, ?)", (dna.model_dump_json(),))
        self.db.commit()

    # --- шорт-лист ---
    def shortlist_add(self, pid: int, note: str | None = None) -> None:
        self.db.execute("INSERT OR REPLACE INTO shortlist VALUES (?, ?, ?)", (pid, note, time.time()))
        self.db.commit()

    def shortlist_remove(self, pid: int) -> None:
        self.db.execute("DELETE FROM shortlist WHERE player_id=?", (pid,))
        self.db.commit()

    def shortlist(self) -> list[int]:
        return [r[0] for r in self.db.execute("SELECT player_id FROM shortlist ORDER BY added_at").fetchall()]
