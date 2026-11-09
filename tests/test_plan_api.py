"""The Plan over HTTP: GET / PUT / PATCH an item, CAS 409, 404 for another user, origin on writes."""

from __future__ import annotations

import sqlite3

import httpx
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user

from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}


def _client(name="alice") -> tuple[TestClient, str]:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": name, "password": "pw-123456"}, headers=O).status_code == 201
    bot_id = c.get("/api/bots").json()[0]["id"]   # the main bot exists from the start
    return c, bot_id


def _frames() -> list[str]:
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        return [row[0] for row in con.execute("SELECT kind FROM events ORDER BY seq")]
    finally:
        con.close()


def test_get_put_patch_round_trip_and_frame():
    c, bot = _client()
    first = c.get(f"/api/bots/{bot}/plan").json()
    assert (first["content"], first["revision"], first["items"], first["unreadable"]) == ("", 1, [], 0)
    put = c.put(f"/api/bots/{bot}/plan", json={"content": "- [ ] call ⏰ 10:07 #a 📅 2026-10-23\nnote ✋\n- [ ] bad 📅 2026-13-01\n",
                                              "base_revision": 1}, headers=O)
    assert put.status_code == 200
    body = put.json()
    [item] = body["items"]
    assert (item["text"], item["time"], item["date"], item["tags"], item["status"], item["tainted"]) == (
        "call", "10:07", "2026-10-23", ["#a"], "planned", False)
    assert len(item["id"]) == 6 and body["unreadable"] == 1 and body["revision"] == 2
    patched = c.patch(f"/api/bots/{bot}/plan/items/{item['id']}", json={"base_revision": 2, "status": "done"}, headers=O)
    assert patched.status_code == 200 and patched.json()["items"][0]["status"] == "done"
    assert patched.json()["items"][0]["done_on"]
    assert "plan_changed" in _frames()


def test_a_stale_revision_is_409_with_the_current_copy():
    c, bot = _client()
    c.put(f"/api/bots/{bot}/plan", json={"content": "- [ ] one\n", "base_revision": 1}, headers=O)
    stale = c.put(f"/api/bots/{bot}/plan", json={"content": "- [ ] two\n", "base_revision": 1}, headers=O)
    assert stale.status_code == 409 and stale.json()["current"]["revision"] == 2
    assert stale.json()["current"]["items"][0]["text"] == "one"
    item = stale.json()["current"]["items"][0]["id"]
    assert c.patch(f"/api/bots/{bot}/plan/items/{item}", json={"base_revision": 1, "text": "z"}, headers=O).status_code == 409


def test_refusals_are_422_and_missing_is_404():
    c, bot = _client()
    too_many = "".join(f"- [ ] t{i}\n" for i in range(2001))
    r = c.put(f"/api/bots/{bot}/plan", json={"content": too_many, "base_revision": 1}, headers=O)
    assert r.status_code == 422 and "too long" in str(r.json())
    assert c.patch(f"/api/bots/{bot}/plan/items/abcdef", json={"base_revision": 1, "status": "done"}, headers=O).status_code == 404
    assert c.patch(f"/api/bots/{bot}/plan/items/abcdef", json={"base_revision": 1}, headers=O).status_code == 422
    assert c.patch(f"/api/bots/{bot}/plan/items/abcdef", json={"base_revision": 1, "status": "nope"}, headers=O).status_code == 422


async def test_another_users_plan_and_items_are_404():
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    await register_user(cfg, "bob", "pw-123456")
    made = await make_bot(cfg, alice_id, "Scout")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as a, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as b:
        for client, name in ((a, "alice"), (b, "bob")):
            assert (await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)).status_code == 200
        bot = made.id
        await a.put(f"/api/bots/{bot}/plan", json={"content": "- [ ] private\n", "base_revision": 1}, headers=O)
        item = (await a.get(f"/api/bots/{bot}/plan")).json()["items"][0]["id"]
        assert (await b.get(f"/api/bots/{bot}/plan")).status_code == 404
        assert (await b.put(f"/api/bots/{bot}/plan", json={"content": "x", "base_revision": 1}, headers=O)).status_code == 404
        assert (await b.patch(f"/api/bots/{bot}/plan/items/{item}", json={"base_revision": 1, "status": "done"}, headers=O)).status_code == 404
        assert "private" in (await a.get(f"/api/bots/{bot}/plan")).json()["content"]


def test_every_write_needs_the_origin():
    c, bot = _client()
    assert c.put(f"/api/bots/{bot}/plan", json={"content": "x", "base_revision": 1}).status_code == 403
    assert c.patch(f"/api/bots/{bot}/plan/items/abcdef", json={"base_revision": 1, "status": "done"}).status_code == 403
    assert c.put(f"/api/bots/{bot}/plan", json={"content": "x", "base_revision": 1},
                 headers={"Origin": "http://evil.example"}).status_code == 403
