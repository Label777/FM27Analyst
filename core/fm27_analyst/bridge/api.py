"""HTTP-эндпоинты моста.

Плагин в игре: /api/bridge/hello, /poll, /table, /screen, /tables, /result.
Приложение:    /api/bridge/status, /request, /auto, /import, /screen/last, /command/{id}.
Мост только читает интерфейс игры; ни одна команда не меняет состояние FM27.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..club.api import opp_scope
from ..club.db import ClubDB
from ..club.importer import import_rows
from .state import BridgeState, as_rows


class RequestIn(BaseModel):
    type: Literal["grab_table", "screen", "tables", "explore", "sniff"]
    table_index: int | None = None


class AutoIn(BaseModel):
    enabled: bool
    interval_sec: float = 3.0


class BridgeImportIn(BaseModel):
    scope: Literal["own", "market", "opp"]
    opponent: str | None = None
    replace: bool | None = None  # по умолчанию: свой состав и соперник — заменить, рынок — дополнить


def register_bridge(app: FastAPI, engine, hub, data_dir: Path) -> BridgeState:
    state = BridgeState(dump_dir=data_dir / "bridge_dumps")
    app.state.bridge = state

    async def notify() -> None:
        await hub.send("bridge", state.status())

    # ---------- плагин ----------
    @app.post("/api/bridge/hello")
    async def hello(body: dict) -> dict:
        state.on_hello(body)
        await notify()
        return {"ok": True}

    @app.get("/api/bridge/poll")
    async def poll() -> dict:
        was = state.online
        reply = state.poll()
        if not was:
            await notify()
        return reply

    @app.post("/api/bridge/table")
    async def table(body: dict) -> dict:
        t = state.on_table(body)
        await notify()
        return {"ok": True, "id": t["id"]}

    @app.post("/api/bridge/screen")
    async def screen(body: dict) -> dict:
        s = state.on_screen(body)
        await hub.send("bridge_screen", state.screen_summary())
        if not s["auto"]:
            await notify()
        return {"ok": True}

    @app.post("/api/bridge/tables")
    async def tables(body: dict) -> dict:
        state.on_tables(body)
        await notify()
        return {"ok": True}

    @app.post("/api/bridge/result")
    async def result(body: dict) -> dict:
        state.finish(body.get("command_id"), bool(body.get("ok")), body.get("message") or "")
        await hub.send("bridge_result", {"command_id": body.get("command_id"), "ok": bool(body.get("ok")),
                                         "message": body.get("message") or ""})
        return {"ok": True}

    # ---------- приложение ----------
    @app.get("/api/bridge/status")
    def status() -> dict:
        return state.status()

    @app.post("/api/bridge/request")
    def request(body: RequestIn) -> dict:
        if not state.online:
            raise HTTPException(409, "Игра не на связи: запустите FM27 с установленным плагином FM27 Analyst Bridge")
        c = state.request(body.type, body.table_index)
        return c.public()

    @app.get("/api/bridge/command/{cid}")
    def command(cid: str) -> dict:
        c = state.commands.get(cid)
        if not c:
            raise HTTPException(404, "Команда не найдена")
        return c.public()

    @app.post("/api/bridge/auto")
    async def auto(body: AutoIn) -> dict:
        state.auto_screen = body.enabled
        state.auto_interval = max(1.0, min(30.0, body.interval_sec))
        await notify()
        return state.status()

    @app.get("/api/bridge/screen/last")
    def last_screen() -> dict:
        if not state.last_screen:
            raise HTTPException(404, "Снимков экрана ещё нет")
        return state.last_screen

    @app.get("/api/bridge/table/last")
    def last_table() -> dict:
        if not state.last_table:
            raise HTTPException(404, "Таблиц из игры ещё нет")
        return state.last_table

    @app.post("/api/bridge/import")
    async def do_import(body: BridgeImportIn) -> dict:
        t = state.last_table
        if not t:
            raise HTTPException(404, "Сначала заберите таблицу из игры")
        if engine.store is None:
            raise HTTPException(409, "Сначала выберите сохранение — база клуба хранится в файле сейва")
        if body.scope == "opp":
            if not (body.opponent or "").strip():
                raise HTTPException(422, "Укажите название соперника")
            scope = opp_scope(body.opponent.strip())
        else:
            scope = body.scope
        replace = body.replace if body.replace is not None else body.scope in ("own", "opp")
        file = f"game:{t['screen'] or 'table'}"
        res = import_rows(as_rows(t), file, scope=scope, kind="game")
        if not res.players:
            raise HTTPException(422, "; ".join(res.warnings) or "Игроки в таблице не найдены")
        club = ClubDB(engine.store.db)
        gd = date.fromisoformat(t["game_date"]) if t.get("game_date") else None
        stats = club.save_import(res, scope, file, replace_scope=replace, game_date=gd)
        if body.scope == "opp":
            club.db.execute("INSERT OR REPLACE INTO meta_opp (scope, name) VALUES (?, ?)", (scope, body.opponent.strip()))
            club.db.commit()
        if gd:
            dna = club.dna()
            if dna.game_date is None or gd > dna.game_date:
                dna.game_date = gd
                club.set_dna(dna)
        notes = list(t.get("notes") or [])
        if not gd:
            notes.append("Игровая дата на экране не найдена — динамика атрибутов будет привязана ко времени импорта.")
        if t.get("missing_rows"):
            notes.append(f"{t['missing_rows']} строк не удалось прочитать.")
        t["imported"] = {"scope": scope, **stats}
        out = {**stats, "scope": scope, "rows": len(res.players), "mapped": res.mapped,
               "game_date": t.get("game_date"), "notes": notes}
        await notify()
        return out

    return state
