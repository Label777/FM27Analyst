"""Память контекста: одна SQLite-база на каждое сохранение FM27.

Данные разных сейвов физически лежат в разных файлах и не смешиваются.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
import unicodedata
from pathlib import Path

from .models import Recommendation, Snapshot

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opponent TEXT NOT NULL,
    our_side TEXT NOT NULL,
    started_at REAL NOT NULL,
    finished INTEGER NOT NULL DEFAULT 0,
    final_score TEXT
);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL REFERENCES matches(id),
    minute INTEGER NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL REFERENCES matches(id),
    minute INTEGER NOT NULL,
    rule_ids TEXT NOT NULL,
    data TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    outcome TEXT
);
CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def slugify(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).strip().lower()
    t = re.sub(r"[^\w\-]+", "-", t, flags=re.U).strip("-")
    return t or "save"


class SaveStore:
    def __init__(self, root: Path, club: str, save_name: str) -> None:
        self.club = club
        self.save_name = save_name
        self.save_id = f"{slugify(club)}__{slugify(save_name)}"
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / f"{self.save_id}.sqlite"
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(matches)")}
        if "game_date" not in cols:  # миграция: дата матча в сейве (для месячных отчётов)
            self.db.execute("ALTER TABLE matches ADD COLUMN game_date TEXT")
        self.db.execute("INSERT OR REPLACE INTO meta VALUES ('club', ?)", (club,))
        self.db.execute("INSERT OR REPLACE INTO meta VALUES ('save_name', ?)", (save_name,))
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # --- матчи ---
    def start_match(self, opponent: str, our_side: str, game_date: str | None = None) -> int:
        cur = self.db.execute(
            "INSERT INTO matches (opponent, our_side, started_at, game_date) VALUES (?, ?, ?, ?)",
            (opponent, our_side, time.time(), game_date),
        )
        self.db.commit()
        return int(cur.lastrowid)

    def finish_match(self, match_id: int, score: str) -> None:
        self.db.execute("UPDATE matches SET finished=1, final_score=? WHERE id=?", (score, match_id))
        self.db.commit()

    def matches(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT id, opponent, our_side, started_at, finished, final_score, game_date FROM matches ORDER BY id DESC"
        ).fetchall()
        return [
            dict(zip(("id", "opponent", "our_side", "started_at", "finished", "final_score", "game_date"), r))
            for r in rows
        ]

    def add_snapshot(self, match_id: int, snap: Snapshot) -> None:
        self.db.execute(
            "INSERT INTO snapshots (match_id, minute, data) VALUES (?, ?, ?)",
            (match_id, snap.minute, snap.model_dump_json()),
        )
        self.db.commit()

    def snapshots(self, match_id: int) -> list[Snapshot]:
        rows = self.db.execute(
            "SELECT data FROM snapshots WHERE match_id=? ORDER BY minute, id", (match_id,)
        ).fetchall()
        return [Snapshot.model_validate_json(r[0]) for r in rows]

    # --- рекомендации ---
    def add_recommendation(self, match_id: int, rec: Recommendation, rule_ids: list[str]) -> int:
        cur = self.db.execute(
            "INSERT INTO recommendations (match_id, minute, rule_ids, data) VALUES (?, ?, ?, ?)",
            (match_id, rec.minute, json.dumps(rule_ids), rec.model_dump_json()),
        )
        self.db.commit()
        return int(cur.lastrowid)

    def set_status(self, rec_id: int, status: str) -> list[str]:
        row = self.db.execute("SELECT rule_ids FROM recommendations WHERE id=?", (rec_id,)).fetchone()
        if row is None:
            raise KeyError(rec_id)
        self.db.execute("UPDATE recommendations SET status=? WHERE id=?", (status, rec_id))
        self.db.commit()
        return json.loads(row[0])

    def set_outcome(self, rec_id: int, outcome: dict) -> None:
        self.db.execute(
            "UPDATE recommendations SET outcome=? WHERE id=?", (json.dumps(outcome, ensure_ascii=False), rec_id)
        )
        self.db.commit()

    def recommendations(self, match_id: int | None = None) -> list[dict]:
        q = "SELECT id, match_id, minute, rule_ids, data, status, outcome FROM recommendations"
        args: tuple = ()
        if match_id is not None:
            q += " WHERE match_id=?"
            args = (match_id,)
        out = []
        for r in self.db.execute(q + " ORDER BY id", args).fetchall():
            rec = Recommendation.model_validate_json(r[4])
            rec.id = str(r[0])
            rec.status = r[5]
            out.append(
                {
                    "match_id": r[1],
                    "rule_ids": json.loads(r[3]),
                    "recommendation": rec,
                    "outcome": json.loads(r[6]) if r[6] else None,
                }
            )
        return out

    def memory_lines(self, limit: int = 8) -> list[str]:
        """Короткая сводка «что советовали и что вышло» для контекста LLM."""
        lines = []
        for item in self.recommendations()[-50:]:
            rec: Recommendation = item["recommendation"]
            if rec.status == "new":
                continue
            o = item["outcome"]
            res = ""
            if o:
                res = f"; через {o['window']} мин: xG мы {o['xg_us']:+.2f}, соперник {o['xg_them']:+.2f}, голы {o['goals']}"
            lines.append(f"{rec.minute}' {rec.actions[0].text} — {'принят' if rec.status == 'accepted' else 'отклонён'}{res}")
        return lines[-limit:]

    # --- предпочтения ---
    def set_pref(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO preferences VALUES (?, ?)", (key, value))
        self.db.commit()

    def prefs(self) -> dict[str, str]:
        return dict(self.db.execute("SELECT key, value FROM preferences").fetchall())


def list_saves(root: Path) -> list[dict]:
    out = []
    if not root.exists():
        return out
    for p in sorted(root.glob("*.sqlite")):
        db = sqlite3.connect(p)
        try:
            meta = dict(db.execute("SELECT key, value FROM meta").fetchall())
        except sqlite3.DatabaseError:
            continue
        finally:
            db.close()
        out.append({"save_id": p.stem, "club": meta.get("club", "?"), "save_name": meta.get("save_name", "?")})
    return out
