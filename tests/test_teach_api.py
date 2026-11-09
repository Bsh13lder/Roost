"""Teach over HTTP and the control socket: Teach, click and type on the computer, I'm done teaching → a card."""

from __future__ import annotations

import json
import struct
from dataclasses import replace

from fastapi.testclient import TestClient

from roost.config import load_config
from roost.desk.fake_cu import FAKE_GEOMETRY, FakeScreenState, fake_target
from roost.gateway.app import create_app
from roost.teach import texts
from test_live_control_mode import AVATAR, O, REQUEST, _handshake

TOP = FAKE_GEOMETRY.page_top
ORDERS = fake_target("link", "Orders", 100, 100)
SEARCH = fake_target("field", "Search orders", 100, 200, width=300)
SCRIPT = {"shop": FakeScreenState(url="https://shop.example/?session=abc", title="Shop", targets=(ORDERS, SEARCH))}
SECRET = "hunter2"


def _client() -> TestClient:
    return TestClient(create_app(replace(load_config(), in_container=True)))


def _bot(c: TestClient, *, linux: bool = True) -> str:
    if c.get("/api/auth/me").status_code != 200:
        assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"},
                      headers=O).status_code == 201
    bot_id = c.post("/api/bots", json={"name": "Scout", "job": "read", "instructions": "", "avatar": AVATAR},
                    headers=O).json()["id"]
    c.patch(f"/api/bots/{bot_id}", json={"computer": "linux" if linux else "mac_brave"}, headers=O)
    if linux:
        c.post(f"/api/bots/{bot_id}/desk/browser/start", headers=O)
    return bot_id


def _press(x: int, y: int) -> bytes:
    return struct.pack(">BBHH", 5, 1, x, y) + struct.pack(">BBHH", 5, 0, x, y)


def _keys(text: str) -> bytes:
    return b"".join(struct.pack(">BBxxI", 4, 1, ord(ch)) + struct.pack(">BBxxI", 4, 0, ord(ch)) for ch in text)


def test_teach_a_task_end_to_end():
    with _client() as c:
        bot_id = _bot(c)
        page = c.app.state.desks.for_bot(bot_id, "linux").serve_screen(SCRIPT)
        assert c.get(f"/api/bots/{bot_id}/teach").json() == {
            "teaching": False, "steps": 0, "capped": False, "started_at": None}
        started = c.post(f"/api/bots/{bot_id}/teach/start", headers=O)
        assert started.status_code == 200 and started.json()["teaching"] is True
        assert c.get(f"/api/bots/{bot_id}/control").json()["held"] is True
        with c.websocket_connect(f"/api/bots/{bot_id}/live?mode=control", headers=O) as ws:
            _handshake(ws)
            ws.send_bytes(_press(120, 110 + TOP))
            page._focused = SEARCH
            ws.send_bytes(_keys(SECRET))
            ws.send_bytes(REQUEST)
            ws.receive_bytes()
        assert c.get(f"/api/bots/{bot_id}/teach").json()["steps"] == 2
        stopped = c.post(f"/api/bots/{bot_id}/teach/stop", json={"description": "Find an order"}, headers=O)
        assert stopped.status_code == 200
        body = stopped.json()
        assert body["proposal_id"] and body["steps"] == 2 and body["discarded"] is False
        assert c.get(f"/api/bots/{bot_id}/control").json()["held"] is False
        [proposal] = c.get("/api/skill-proposals").json()
        assert proposal["tainted"] is True and proposal["bot_id"] == bot_id
        assert SECRET not in json.dumps(proposal) and "session=abc" not in json.dumps(proposal)
        assert "Search orders" in proposal["payload"]["body"]


def test_start_refusals_and_another_users_bot():
    with _client() as c:
        mac = _bot(c, linux=False)
        refused = c.post(f"/api/bots/{mac}/teach/start", headers=O)
        assert refused.status_code == 409 and refused.json()["detail"] == texts.LINUX_ONLY
        assert c.post("/api/bots/nope/teach/start", headers=O).status_code == 404
        assert c.get("/api/bots/nope/teach").status_code == 404
        assert c.post("/api/bots/nope/teach/stop", json={}, headers=O).status_code == 404
        assert c.post(f"/api/bots/{mac}/teach/start").status_code == 403          # no Origin


def test_stop_refusals_and_discard():
    with _client() as c:
        bot_id = _bot(c)
        none = c.post(f"/api/bots/{bot_id}/teach/stop", json={}, headers=O)
        assert none.status_code == 409 and none.json()["detail"] == texts.NOT_TEACHING
        c.post(f"/api/bots/{bot_id}/teach/start", headers=O)
        empty = c.post(f"/api/bots/{bot_id}/teach/stop", json={}, headers=O)
        assert empty.status_code == 422 and empty.json()["detail"] == texts.NOTHING_RECORDED
        bad = c.post(f"/api/bots/{bot_id}/teach/stop", json={"description": "a\nb"}, headers=O)
        assert bad.status_code == 422
        gone = c.post(f"/api/bots/{bot_id}/teach/stop", json={"discard": True}, headers=O)
        assert gone.status_code == 200 and gone.json()["discarded"] is True
        assert c.get(f"/api/bots/{bot_id}/teach").json()["teaching"] is False
        assert c.get(f"/api/bots/{bot_id}/control").json()["held"] is False
        assert c.get("/api/skill-proposals").json() == []


def test_a_plain_give_back_ends_teaching():
    """Review FAIL 1 over HTTP: I'm done (DELETE /control) ends the teach session, so a later Take control
    is never recorded."""
    with _client() as c:
        bot_id = _bot(c)
        assert c.post(f"/api/bots/{bot_id}/teach/start", headers=O).status_code == 200
        assert c.request("DELETE", f"/api/bots/{bot_id}/control", headers=O).status_code == 200
        assert c.post(f"/api/bots/{bot_id}/teach/stop", json={}, headers=O).status_code == 409   # log gone
        assert c.get(f"/api/bots/{bot_id}/teach").json()["teaching"] is False
        c.post(f"/api/bots/{bot_id}/control", headers=O)
        assert c.app.state.teach.recording(bot_id) is False
