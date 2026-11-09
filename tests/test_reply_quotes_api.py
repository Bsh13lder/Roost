"""Reply quotes over HTTP: ``POST /api/threads/{id}/messages`` takes ``reply_to``; the server makes the quote."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from team_helpers import make_bot

ORIGIN = {"Origin": "http://127.0.0.1:18800"}


def _client(app) -> tuple[TestClient, str, str]:
    c = TestClient(app)
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=ORIGIN).status_code == 201
    user_id = c.get("/api/auth/me").json()["id"]
    bot_id = c.get("/api/bots").json()[0]["id"]
    thread_id = c.post(f"/api/bots/{bot_id}/chat", headers=ORIGIN).json()["id"]
    return c, user_id, thread_id


async def test_a_reply_stores_the_server_made_quote():
    app = create_app()
    c, user_id, thread_id = _client(app)
    quoted = await app.state.talk.add_message(user_id, thread_id, "bot", "Long " * 60, tainted=True)
    sent = c.post(f"/api/threads/{thread_id}/messages", json={"text": "Why?", "reply_to": quoted.id}, headers=ORIGIN)
    assert sent.status_code == 202
    [row] = [m for m in c.get(f"/api/threads/{thread_id}/messages").json() if m["id"] == sent.json()["message_id"]]
    assert row["reply_to"] == quoted.id and row["reply_tainted"] is True
    assert row["reply_quote"].startswith("Long Long") and row["reply_quote"].endswith("…")
    assert row["body"] == "Why?" and row["tainted"] is False


async def test_a_message_without_reply_to_is_unchanged():
    app = create_app()
    c, _, thread_id = _client(app)
    sent = c.post(f"/api/threads/{thread_id}/messages", json={"text": "hi"}, headers=ORIGIN)
    assert sent.status_code == 202
    [row] = c.get(f"/api/threads/{thread_id}/messages").json()[-1:]
    assert row["reply_to"] is None and row["reply_quote"] is None


async def test_reply_to_a_message_elsewhere_or_unknown_is_404_and_nothing_is_stored():
    app = create_app()
    c, user_id, thread_id = _client(app)
    bot_id = c.get("/api/bots").json()[0]["id"]
    other = await app.state.talk.create_thread(user_id, bot_id)
    elsewhere = await app.state.talk.add_message(user_id, other.id, "bot", "elsewhere")
    card = await app.state.talk.add_message(user_id, thread_id, "bot", "{}", kind="skill_proposal")
    before = len(c.get(f"/api/threads/{thread_id}/messages").json())
    for reply_to in (elsewhere.id, card.id, "nope"):
        r = c.post(f"/api/threads/{thread_id}/messages", json={"text": "x", "reply_to": reply_to}, headers=ORIGIN)
        assert r.status_code == 404 and r.json()["detail"] == "That message can't be replied to here."
    assert len(c.get(f"/api/threads/{thread_id}/messages").json()) == before


async def test_reply_to_must_be_a_short_id():
    app = create_app()
    c, _, thread_id = _client(app)
    for bad in ("", "x" * 65):
        r = c.post(f"/api/threads/{thread_id}/messages", json={"text": "x", "reply_to": bad}, headers=ORIGIN)
        assert r.status_code == 422


async def test_another_users_message_cannot_be_quoted():
    app = create_app()
    c, user_id, thread_id = _client(app)
    mine = await app.state.talk.add_message(user_id, thread_id, "bot", "secret words")
    cfg = load_config()
    await init_db(cfg)
    bob = await register_user(cfg, "bob", "pw-123456")
    bob_thread, _ = await app.state.talk.ensure_main_thread(bob.id, (await make_bot(cfg, bob.id, "Pal")).id)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as other:
        assert (await other.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"},
                                 headers=ORIGIN)).status_code == 200
        r = await other.post(f"/api/threads/{bob_thread.id}/messages", json={"text": "x", "reply_to": mine.id},
                             headers=ORIGIN)
        assert r.status_code == 404
