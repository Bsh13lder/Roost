"""Chat text search (mobile SERVER_NEEDS M4): ``GET /api/chats/search?q=`` finds words in every chat's messages.

The same matching as the ``search_chat`` tool (every word must appear, accents and case folded, best match first),
across the user's bot chats and rooms. Bodies are sealed and decrypted only for their owner: another user never
sees a hit. Routine run logs and cards are not searched."""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}
PASSWORD = "pw-123456"
RESULT_FIELDS = {"chat_kind", "chat_id", "name", "thread_id", "message_id", "from_you", "snippet", "created_at",
                 "tainted"}


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def app(cfg):
    return create_app(cfg)


@asynccontextmanager
async def signed_in(app, username):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        assert (await client.post("/api/auth/login", json={"username": username, "password": PASSWORD},
                                  headers=O)).status_code == 200
        yield client


async def _say(app, user_id, thread_id, role, body, **extra):
    return await app.state.talk.add_message(user_id, thread_id, role, body, **extra)


async def test_finds_words_across_chats_with_the_chat_it_belongs_to(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    scout, pip = await make_bot(cfg, alice.id, "Scout"), await make_bot(cfg, alice.id, "Pip")
    scout_thread, _ = await app.state.talk.ensure_main_thread(alice.id, scout.id)
    pip_thread, _ = await app.state.talk.ensure_main_thread(alice.id, pip.id)
    mine = await _say(app, alice.id, scout_thread.id, "user", "Find me a blue Kettle please")
    reply = await _say(app, alice.id, pip_thread.id, "bot", "The blue kettle costs 25 EUR.", tainted=True,
                       author_bot_id=pip.id)
    await _say(app, alice.id, pip_thread.id, "bot", "A red kettle only.", author_bot_id=pip.id)

    async with signed_in(app, "alice") as client:
        answer = await client.get("/api/chats/search", params={"q": "kettle BLUE"})

    assert answer.status_code == 200
    results = answer.json()["results"]
    assert {r["message_id"] for r in results} == {mine.id, reply.id}
    assert all(set(r) == RESULT_FIELDS for r in results)
    by_id = {r["message_id"]: r for r in results}
    assert (by_id[mine.id]["chat_kind"], by_id[mine.id]["chat_id"], by_id[mine.id]["name"]) == ("bot", scout.id, "Scout")
    assert by_id[mine.id]["from_you"] is True and by_id[mine.id]["thread_id"] == scout_thread.id
    assert by_id[reply.id]["from_you"] is False and by_id[reply.id]["tainted"] is True
    assert by_id[reply.id]["snippet"] == "The blue kettle costs 25 EUR."


async def test_a_room_message_names_the_room(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    scout, pip = await make_bot(cfg, alice.id, "Scout"), await make_bot(cfg, alice.id, "Pip")
    async with signed_in(app, "alice") as client:
        room = (await client.post("/api/rooms", json={"name": "Saturday", "member_ids": [scout.id, pip.id]},
                                  headers=O)).json()
        said = await _say(app, alice.id, room["thread_id"], "user", "Plan the picnic")
        results = (await client.get("/api/chats/search", params={"q": "picnic"})).json()["results"]
    assert [(r["chat_kind"], r["chat_id"], r["name"], r["message_id"]) for r in results] == [
        ("room", room["id"], "Saturday", said.id)]


async def test_another_users_messages_are_never_found(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    await register_user(cfg, "bob", PASSWORD)
    scout = await make_bot(cfg, alice.id, "Scout")
    thread, _ = await app.state.talk.ensure_main_thread(alice.id, scout.id)
    await _say(app, alice.id, thread.id, "user", "My secret kettle plan")
    async with signed_in(app, "bob") as client:
        assert (await client.get("/api/chats/search", params={"q": "kettle"})).json() == {"results": []}


async def test_a_long_or_empty_query_is_refused_and_punctuation_finds_nothing(cfg, app):
    await register_user(cfg, "alice", PASSWORD)
    async with signed_in(app, "alice") as client:
        assert (await client.get("/api/chats/search", params={"q": ""})).status_code == 422
        assert (await client.get("/api/chats/search", params={"q": "x" * 101})).status_code == 422
        assert (await client.get("/api/chats/search")).status_code == 422
        assert (await client.get("/api/chats/search", params={"q": "   "})).json() == {"results": []}


async def test_needs_a_login(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        assert (await client.get("/api/chats/search", params={"q": "kettle"})).status_code == 401
