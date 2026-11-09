"""Rooms HTTP API (D-E) — including the cross-user matrix rows."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from team_helpers import wait_idle

O = {"Origin": "http://127.0.0.1:18800"}
AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _bots(c: TestClient, *names: str) -> list[str]:
    return [c.post("/api/bots", json={"name": n, "job": "helps", "instructions": "", "avatar": AVATAR}, headers=O).json()["id"]
            for n in names]


def test_create_room_shape_and_default_coordinator_is_the_main_bot():
    c = _client()
    chief, scout = _bots(c, "Boss", "Scout")
    c.post(f"/api/bots/{chief}/star", headers=O)
    r = c.post("/api/rooms", json={"name": "Saturday", "member_ids": [scout, chief]}, headers=O)
    assert r.status_code == 201
    room = r.json()
    assert set(room) == {"id", "name", "coordinator_id", "member_ids", "thread_id", "created_at", "updated_at"}
    assert (room["name"], room["coordinator_id"], room["member_ids"]) == ("Saturday", chief, [scout, chief])
    assert c.get("/api/rooms").json() == [room]
    assert c.get(f"/api/rooms/{room['id']}").json() == room


def test_without_a_main_bot_the_first_member_coordinates():
    c = _client()
    scout, quill = _bots(c, "Scout", "Quill")
    assert c.post("/api/rooms", json={"name": "Pair", "member_ids": [quill, scout]}, headers=O).json()["coordinator_id"] == quill


def test_refused_rooms_are_422_with_a_plain_reason():
    c = _client()
    a, b, d, e, f, g, h = _bots(c, "A1", "B1", "D1", "E1", "F1", "G1", "H1")
    c.put(f"/api/bots/{b}/duty", json={"off_duty": True}, headers=O)
    cases = [
        ({"name": "x", "member_ids": [a]}, None),
        ({"name": "x", "member_ids": [a, d, e, f, g, h, b]}, None),
        ({"name": "x", "member_ids": [a, a]}, "Each bot can join a room once."),
        ({"name": "x", "member_ids": [a, b]}, "B1 is off duty."),
        ({"name": "x", "member_ids": [a, "someone-elses-bot"]}, "One of these bots isn't on your team."),
        ({"name": "x", "member_ids": [a, d], "coordinator_id": e}, "The coordinator must be one of the members."),
        ({"name": "", "member_ids": [a, d]}, None),
    ]
    for body, detail in cases:
        r = c.post("/api/rooms", json=body, headers=O)
        assert r.status_code == 422, body
        if detail is not None:
            assert r.json()["detail"] == detail


def test_posting_routes_by_mention_and_room_threads_refuse_the_chat_route():
    c = _client()
    chief, scout = _bots(c, "Boss", "Scout")
    room = c.post("/api/rooms", json={"name": "Saturday", "member_ids": [chief, scout]}, headers=O).json()

    plain = c.post(f"/api/rooms/{room['id']}/messages", json={"text": "plan it"}, headers=O)
    mentioned = c.post(f"/api/rooms/{room['id']}/messages", json={"text": "@Scout prices?"}, headers=O)
    everyone = c.post(f"/api/rooms/{room['id']}/messages", json={"text": "@everyone ideas"}, headers=O)

    assert plain.status_code == 202 and plain.json()["routed_to"] == [chief]
    assert mentioned.json()["routed_to"] == [scout]
    assert everyone.json()["routed_to"] == [chief, scout]
    assert c.post(f"/api/threads/{room['thread_id']}/messages", json={"text": "x"}, headers=O).status_code == 409
    assert room["thread_id"] not in [t["id"] for t in c.get(f"/api/bots/{chief}/threads").json()]
    assert [m["body"] for m in c.get(f"/api/rooms/{room['id']}/messages").json() if m["role"] == "user"][:1] == ["plan it"]


def test_rooms_need_an_allowed_origin():
    c = _client()
    a, b = _bots(c, "A1", "B1")
    assert c.post("/api/rooms", json={"name": "x", "member_ids": [a, b]}).status_code == 403


async def test_another_users_room_is_404_everywhere():
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    for name in ("alice", "bob"):
        await register_user(cfg, name, "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        await alice.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
        await bob.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"}, headers=O)
        ids = [(await alice.post("/api/bots", json={"name": n, "job": "j", "instructions": "", "avatar": AVATAR},
                                 headers=O)).json()["id"] for n in ("Chief", "Scout")]
        room = (await alice.post("/api/rooms", json={"name": "Saturday", "member_ids": ids}, headers=O)).json()

        assert (await bob.get(f"/api/rooms/{room['id']}")).status_code == 404
        assert (await bob.get(f"/api/rooms/{room['id']}/messages")).status_code == 404
        assert (await bob.post(f"/api/rooms/{room['id']}/messages", json={"text": "hi"}, headers=O)).status_code == 404
        assert (await bob.get(f"/api/threads/{room['thread_id']}/messages")).status_code == 404
        assert (await bob.get("/api/rooms")).json() == []
        r = await bob.post("/api/rooms", json={"name": "Steal", "member_ids": ids}, headers=O)
        assert (r.status_code, r.json()["detail"]) == (422, "One of these bots isn't on your team.")
    await wait_idle(app.state.turns)
