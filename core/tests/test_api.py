from __future__ import annotations

from fastapi.testclient import TestClient
from PIL import Image

from fm27_analyst import demo
from fm27_analyst.reasoner import Reasoner
from fm27_analyst.server import create_app
from fm27_analyst.vision import ChangeFilter, Pipeline


def client(tmp_path):
    return TestClient(create_app(tmp_path, Reasoner(None)))


def test_flow_save_match_snapshot_ask_feedback(tmp_path):
    c = client(tmp_path)
    assert c.get("/api/health").json()["llm"] is False
    assert c.post("/api/snapshots", json=demo.scenario()[0].model_dump(mode="json")).status_code == 409
    c.post("/api/saves", json={"club": "Динамо", "save_name": "Карьера"})
    c.post("/api/matches", json={"opponent": "Шахтёр", "our_side": "home"})
    recs = []
    with c.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        for s in demo.scenario()[:13]:
            r = c.post("/api/snapshots", json=s.model_dump(mode="json"))
            assert r.status_code == 200
            recs += r.json()["recommendations"]
            ev = ws.receive_json()
            assert ev["type"] == "tick"
    assert recs
    a = c.post("/api/ask", json={"question": "Что сейчас с нашей тактикой?"}).json()
    assert a["short"] and len(a["short"].split()) <= 25
    rid = int(recs[0]["id"])
    assert c.post(f"/api/recommendations/{rid}/feedback", json={"status": "rejected"}).json()["ok"]
    hist = c.get("/api/recommendations").json()
    assert any(h["recommendation"]["status"] == "rejected" for h in hist)


def test_impossible_snapshot_rejected(tmp_path):
    c = client(tmp_path)
    c.post("/api/saves", json={"club": "Д", "save_name": "К"})
    c.post("/api/matches", json={"opponent": "Ш"})
    s = demo.scenario()[5].model_dump(mode="json")
    c.post("/api/snapshots", json=s)
    earlier = demo.scenario()[2].model_dump(mode="json")
    r = c.post("/api/snapshots", json=earlier)
    assert r.status_code == 422 and "минута" in r.json()["detail"]


def test_change_filter_and_untrained_pipeline():
    cf = ChangeFilter()
    a = Image.new("RGB", (320, 180), (20, 120, 40))
    assert cf.changed(a) == ["full"]
    assert cf.changed(a) == []
    b = a.copy()
    b.paste((250, 250, 250), (0, 0, 160, 90))
    assert cf.changed(b) == ["full"]
    res = Pipeline().process(Image.new("RGB", (320, 180), (0, 0, 0)))
    assert res.snapshot is None and "этап 3" in res.message
