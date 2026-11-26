"""Состояние моста: очередь команд для плагина и последние данные из игры (в памяти ядра)."""

from __future__ import annotations

import json
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .gamedate import find_game_date

COMMANDS = {"grab_table", "screen", "tables", "explore", "sniff", "probe"}
ONLINE_SECONDS = 4.0  # плагин опрашивает раз в секунду; 4 с тишины — связи нет


def plural(n: int, one: str, few: str, many: str) -> str:
    n10, n100 = n % 10, n % 100
    word = one if n10 == 1 and n100 != 11 else few if 2 <= n10 <= 4 and not 12 <= n100 <= 14 else many
    return f"{n} {word}"


def suggest_scope(screen: str) -> str | None:
    """Подсказка, чья это таблица, по имени экрана FM (имена элементов английские при любом языке игры).

    Только подсказка: экран «Состав» бывает и у чужого клуба, поэтому решает пользователь.
    """
    s = screen.lower()
    if any(k in s for k in ("search", "scout", "shortlist", "transfer", "loan", "recruit")):
        return "market"
    if "squad" in s or "players" in s or "first team" in s:
        return "own"
    return None


@dataclass
class Command:
    id: str
    type: str
    table_index: int | None = None
    created: float = field(default_factory=time.time)
    status: str = "queued"  # queued → sent → done | failed
    message: str = ""

    def public(self) -> dict:
        return {"id": self.id, "type": self.type, "status": self.status, "message": self.message,
                "created": self.created}


class BridgeState:
    def __init__(self, dump_dir: Path | None = None, keep_dumps: int = 300) -> None:
        self.hello: dict | None = None
        self.last_seen: float | None = None
        self.queue: deque[Command] = deque()
        self.commands: dict[str, Command] = {}
        self.auto_screen = False
        self.auto_interval = 3.0
        self.last_table: dict | None = None
        self.last_screen: dict | None = None
        self.last_tables: list[dict] = []
        self.game_date: date | None = None
        self.game_date_text: str | None = None
        self.dump_dir = dump_dir
        self.keep_dumps = keep_dumps

    # --- плагин ---
    def on_hello(self, info: dict) -> None:
        self.hello = info
        self.last_seen = time.time()

    def poll(self) -> dict:
        self.last_seen = time.time()
        out = []
        while self.queue:
            c = self.queue.popleft()
            c.status = "sent"
            out.append({"id": c.id, "type": c.type, **({"table_index": c.table_index} if c.table_index is not None else {})})
        return {"commands": out, "auto_screen": self.auto_screen, "auto_interval_sec": self.auto_interval}

    def finish(self, command_id: str | None, ok: bool, message: str = "") -> None:
        c = self.commands.get(command_id or "")
        if c:
            c.status = "done" if ok else "failed"
            c.message = message

    def _note_date(self, texts: list[str]) -> None:
        found = find_game_date(texts)
        if found:
            self.game_date, self.game_date_text = found

    def on_table(self, payload: dict) -> dict:
        self.last_seen = time.time()
        self._note_date(payload.get("context_texts") or [])
        headers = payload.get("headers") or []
        rows = payload.get("rows") or []
        table = {
            "id": uuid.uuid4().hex[:10],
            "received_at": time.time(),
            "screen": payload.get("screen") or "",
            "path": payload.get("path") or "",
            "headers": headers,
            "rows": rows,
            "row_count": len(rows),
            "expected_rows": payload.get("expected_rows"),
            "paginated": bool(payload.get("paginated")),
            "hidden_columns": payload.get("hidden_columns") or 0,
            "missing_rows": payload.get("missing_rows") or 0,
            "notes": payload.get("notes") or [],
            "game_date": self.game_date.isoformat() if self.game_date else None,
            "suggested_scope": suggest_scope(payload.get("screen") or ""),
            "imported": None,
        }
        self.last_table = table
        self.finish(payload.get("command_id"), True, plural(len(rows), "строка", "строки", "строк"))
        self._dump("table", payload)
        return table

    def on_screen(self, payload: dict) -> dict:
        self.last_seen = time.time()
        texts = [t.get("t", "") for t in payload.get("texts") or []]
        self._note_date(texts[:60])
        screen = {
            "received_at": time.time(),
            "auto": bool(payload.get("auto")),
            "screen": payload.get("screen") or "",
            "hash": payload.get("hash") or "",
            "truncated": bool(payload.get("truncated")),
            "width": payload.get("width"),
            "height": payload.get("height"),
            "texts": payload.get("texts") or [],
        }
        self.last_screen = screen
        if payload.get("command_id"):
            self.finish(payload.get("command_id"), True, plural(len(texts), "текст", "текста", "текстов"))
        self._dump("screen", payload)
        return screen

    def on_tables(self, payload: dict) -> None:
        self.last_seen = time.time()
        self.last_tables = payload.get("tables") or []
        self.finish(payload.get("command_id"), True, f"таблиц: {len(self.last_tables)}")

    # --- приложение ---
    def request(self, type_: str, table_index: int | None = None) -> Command:
        if type_ not in COMMANDS:
            raise ValueError(f"Неизвестная команда: {type_}")
        # одна и та же ещё не отправленная команда — не дублируем (двойной клик по кнопке)
        for q in self.queue:
            if q.type == type_ and q.table_index == table_index:
                return q
        c = Command(id=uuid.uuid4().hex[:10], type=type_, table_index=table_index)
        self.commands[c.id] = c
        self.queue.append(c)
        if len(self.commands) > 200:
            for k in list(self.commands)[:100]:
                self.commands.pop(k, None)
        return c

    @property
    def online(self) -> bool:
        return self.last_seen is not None and time.time() - self.last_seen < ONLINE_SECONDS

    def status(self) -> dict:
        return {
            "online": self.online,
            "last_seen": self.last_seen,
            "plugin": self.hello,
            "auto_screen": self.auto_screen,
            "auto_interval": self.auto_interval,
            "game_date": self.game_date.isoformat() if self.game_date else None,
            "game_date_text": self.game_date_text,
            "queued": len(self.queue),
            "last_table": self.table_summary(),
            "last_screen": self.screen_summary(),
            "tables_on_screen": self.last_tables,
        }

    def table_summary(self) -> dict | None:
        t = self.last_table
        if not t:
            return None
        return {k: v for k, v in t.items() if k not in ("rows",)} | {"preview": t["rows"][:5]}

    def screen_summary(self) -> dict | None:
        s = self.last_screen
        if not s:
            return None
        return {k: v for k, v in s.items() if k != "texts"} | {"text_count": len(s["texts"])}

    # --- снимки на диск: для настройки распознавания экранов матча ---
    def _dump(self, kind: str, payload: dict) -> None:
        if not self.dump_dir:
            return
        try:
            self.dump_dir.mkdir(parents=True, exist_ok=True)
            name = f"{time.strftime('%Y%m%d-%H%M%S')}-{kind}-{uuid.uuid4().hex[:6]}.json"
            (self.dump_dir / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            files = sorted(self.dump_dir.glob("*.json"))
            for f in files[: max(0, len(files) - self.keep_dumps)]:
                f.unlink(missing_ok=True)
        except OSError:
            pass


def as_rows(table: dict[str, Any]) -> list[list[str]]:
    return [list(table["headers"])] + [list(r) for r in table["rows"]]
