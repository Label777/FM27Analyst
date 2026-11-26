"""Локальный API ядра: HTTP + WebSocket на 127.0.0.1.

Интерфейс (Tauri/React) подписывается на /ws и получает события:
state, changes, signals, recommendations, answer, capture.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import __version__, demo
from .capture import CaptureError, get_default_source
from .engine import Engine, TickResult
from .models import Snapshot
from .reasoner import Reasoner, default_provider
from .storage import list_saves
from .vision import Pipeline

log = logging.getLogger("fm27")


def default_data_dir() -> Path:
    base = os.environ.get("FM27_DATA_DIR")
    if base:
        return Path(base)
    appdata = os.environ.get("APPDATA")
    return Path(appdata) / "FM27Analyst" if appdata else Path.home() / ".fm27-analyst"


class Hub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def send(self, event: str, payload: Any) -> None:
        dead = []
        for ws in self.clients:
            try:
                await ws.send_json({"type": event, "data": payload})
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


def tick_payload(r: TickResult) -> dict:
    return {
        "snapshot": r.snapshot.model_dump(mode="json"),
        "changes": [c.__dict__ for c in r.changes],
        "facts": [f.model_dump(mode="json") for f in r.facts],
        "signals": [s.model_dump(mode="json") for s in r.signals],
        "recommendations": [x.model_dump(mode="json") for x in r.recommendations],
    }


class SaveIn(BaseModel):
    club: str
    save_name: str


class MatchIn(BaseModel):
    opponent: str
    our_side: Literal["home", "away"] = "home"


class AskIn(BaseModel):
    question: str


class FeedbackIn(BaseModel):
    status: Literal["accepted", "rejected"]


class DemoIn(BaseModel):
    seconds_per_step: float = 2.0


def create_app(data_dir: Path | None = None, reasoner: Reasoner | None = None) -> FastAPI:
    app = FastAPI(title="FM27 Analyst Core", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:1420", "http://127.0.0.1:1420", "http://localhost:8727", "http://127.0.0.1:8727", "tauri://localhost",
                       "http://tauri.localhost", "https://tauri.localhost"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    engine = Engine(data_dir or default_data_dir(), reasoner or Reasoner(default_provider()))
    hub = Hub()
    pipeline = Pipeline()
    app.state.engine = engine
    app.state.demo_task = None

    def need_match() -> None:
        if engine.store is None:
            raise HTTPException(409, "Сначала выберите сохранение")
        if engine.match_id is None:
            raise HTTPException(409, "Сначала начните матч")

    async def ingest(snap: Snapshot) -> dict:
        try:
            r = engine.ingest(snap)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        payload = tick_payload(r)
        await hub.send("tick", payload)
        return payload

    @app.get("/api/health")
    def health() -> dict:
        return {
            "ok": True,
            "version": __version__,
            "llm": engine.reasoner.has_llm,
            "save": engine.store.save_id if engine.store else None,
            "match_id": engine.match_id,
        }

    @app.get("/api/saves")
    def saves() -> list[dict]:
        return list_saves(engine.data_dir / "saves")

    @app.post("/api/saves")
    async def open_save(body: SaveIn) -> dict:
        st = engine.open_save(body.club, body.save_name)
        await hub.send("save", {"save_id": st.save_id, "club": st.club, "save_name": st.save_name})
        return {"save_id": st.save_id}

    @app.post("/api/matches")
    async def start_match(body: MatchIn) -> dict:
        if engine.store is None:
            raise HTTPException(409, "Сначала выберите сохранение")
        mid = engine.start_match(body.opponent, body.our_side)
        await hub.send("match", {"match_id": mid, "opponent": body.opponent, "our_side": body.our_side})
        return {"match_id": mid}

    @app.get("/api/matches")
    def matches() -> list[dict]:
        if engine.store is None:
            raise HTTPException(409, "Сначала выберите сохранение")
        return engine.store.matches()

    @app.post("/api/snapshots")
    async def add_snapshot(snap: Snapshot) -> dict:
        need_match()
        return await ingest(snap)

    @app.get("/api/state")
    def state() -> dict:
        if not engine.last:
            return {"tick": None}
        return {"tick": tick_payload(engine.last)}

    @app.post("/api/ask")
    async def ask(body: AskIn) -> dict:
        a = engine.ask(body.question)
        payload = {"question": body.question, **a.__dict__}
        await hub.send("answer", payload)
        return payload

    @app.post("/api/review")
    async def review() -> dict:
        need_match()
        recs = engine.head_coach_review()
        payload = [r.model_dump(mode="json") for r in recs]
        await hub.send("review", payload)
        return {"recommendations": payload}

    @app.get("/api/recommendations")
    def recommendations() -> list[dict]:
        if engine.store is None:
            raise HTTPException(409, "Сначала выберите сохранение")
        return [
            {**{k: v for k, v in it.items() if k != "recommendation"},
             "recommendation": it["recommendation"].model_dump(mode="json")}
            for it in engine.store.recommendations()
        ]

    @app.post("/api/recommendations/{rec_id}/feedback")
    async def feedback(rec_id: int, body: FeedbackIn) -> dict:
        try:
            engine.feedback(rec_id, body.status)
        except KeyError as e:
            raise HTTPException(404, "Совет не найден") from e
        await hub.send("feedback", {"id": rec_id, "status": body.status})
        return {"ok": True}

    @app.post("/api/capture/analyze")
    async def analyze() -> dict:
        """Кнопка «Анализ экрана»: снимок текущего экрана → конвейер распознавания."""
        try:
            src = get_default_source()
            img = await asyncio.to_thread(src.grab)
        except CaptureError as e:
            payload = {"ok": False, "message": str(e)}
            await hub.send("capture", payload)
            return payload
        res = pipeline.process(img)
        payload: dict[str, Any] = {
            "ok": res.snapshot is not None,
            "screen": res.screen.value,
            "changed_regions": res.changed_regions,
            "message": res.message,
            "size": list(img.size),
            "source": src.name,
        }
        if engine.store:
            shots = engine.data_dir / "captures" / engine.store.save_id
            shots.mkdir(parents=True, exist_ok=True)
            path = shots / f"m{engine.match_id or 0}_{len(list(shots.iterdir())):05d}.png"
            img.save(path)
            payload["saved_to"] = str(path)
        await hub.send("capture", payload)
        if res.snapshot is not None and engine.match_id is not None:
            payload["tick"] = await ingest(res.snapshot)
        return payload

    @app.post("/api/demo/start")
    async def demo_start(body: DemoIn) -> dict:
        if app.state.demo_task and not app.state.demo_task.done():
            app.state.demo_task.cancel()
        engine.open_save("Демо-клуб", "Демо-сейв")
        engine.start_match("Соперник", "home")
        await hub.send("save", {"save_id": engine.store.save_id, "club": "Демо-клуб", "save_name": "Демо-сейв"})
        await hub.send("match", {"match_id": engine.match_id, "opponent": "Соперник", "our_side": "home"})

        async def run() -> None:
            for snap in demo.scenario():
                await ingest(snap)
                await asyncio.sleep(body.seconds_per_step)
            engine.finish_match()
            await hub.send("demo_done", {})

        app.state.demo_task = asyncio.create_task(run())
        return {"ok": True, "steps": len(demo.MINUTES)}

    @app.post("/api/demo/stop")
    def demo_stop() -> dict:
        if app.state.demo_task:
            app.state.demo_task.cancel()
        return {"ok": True}

    from .club.api import register as register_club

    register_club(app, engine)
    from .club.api import register_departments

    register_departments(app, engine)
    from .bridge import register_bridge

    register_bridge(app, engine, hub, engine.data_dir)

    @app.websocket("/ws")
    async def ws(sock: WebSocket) -> None:
        await sock.accept()
        hub.clients.add(sock)
        try:
            await sock.send_json({"type": "hello", "data": health()})
            if engine.last:
                await sock.send_json({"type": "tick", "data": tick_payload(engine.last)})
            while True:
                await sock.receive_text()  # клиент может слать ping
        except WebSocketDisconnect:
            pass
        finally:
            hub.clients.discard(sock)

    # Интерфейс в браузере (без сборки Tauri): папка web рядом с ядром или FM27_WEB_DIR.
    web = Path(os.environ["FM27_WEB_DIR"]) if os.environ.get("FM27_WEB_DIR") else None
    if web and (web / "index.html").exists():
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=web, html=True), name="web")

    return app


def main() -> None:
    ap = argparse.ArgumentParser(description="FM27 Analyst — локальное ядро")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8727)
    ap.add_argument("--data-dir", type=Path, default=None)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    import uvicorn

    uvicorn.run(create_app(args.data_dir), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
