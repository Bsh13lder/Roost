"""One main chat per bot (memory Task 10): which thread it is, and POST /api/bots/{id}/chat."""

from __future__ import annotations

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.talk.store import TalkStore
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture
async def bot(cfg, user_id):
    return await make_bot(cfg, user_id, "Scout")


@pytest.fixture
def talk(cfg):
    return TalkStore(cfg)


async def test_a_bot_with_no_chat_gets_one(talk, user_id, bot):
    assert await talk.main_thread(user_id, bot.id) is None
    thread, created = await talk.ensure_main_thread(user_id, bot.id)
    assert created is True and thread.kind == "chat" and thread.bot_id == bot.id
    assert await talk.main_thread(user_id, bot.id) == thread


async def test_the_chat_with_the_newest_message_is_the_main_one(talk, user_id, bot):
    first = await talk.create_thread(user_id, bot.id)
    second = await talk.create_thread(user_id, bot.id)
    assert (await talk.main_thread(user_id, bot.id)).id == second.id   # no messages: created_at decides
    await talk.add_message(user_id, first.id, "user", "I was here")
    assert (await talk.main_thread(user_id, bot.id)).id == first.id
    await talk.add_message(user_id, second.id, "user", "and now here")
    assert (await talk.main_thread(user_id, bot.id)).id == second.id


async def test_handoff_and_room_threads_are_never_the_main_chat(talk, user_id, bot, cfg):
    other = await make_bot(cfg, user_id, "Quill")
    chat = await talk.create_thread(user_id, bot.id)
    handoff = await talk.find_or_create_peer_thread(user_id, bot.id, other.id, "From Quill")
    room = await talk.create_thread(user_id, bot.id, kind="room")
    await talk.add_message(user_id, handoff.id, "user", "newest", kind="handoff")
    await talk.add_message(user_id, room.id, "user", "newer still")
    assert (await talk.main_thread(user_id, bot.id)).id == chat.id


async def test_the_same_chat_comes_back_every_time(talk, user_id, bot):
    one, made = await talk.ensure_main_thread(user_id, bot.id)
    two, made_again = await talk.ensure_main_thread(user_id, bot.id)
    assert (made, made_again) == (True, False) and one.id == two.id


async def test_another_users_bot_has_no_chat_for_you(cfg, talk, user_id, bot):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    await talk.create_thread(user_id, bot.id)
    assert await talk.main_thread(bob, bot.id) is None
    app = create_app()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    try:
        await client.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"}, headers=O)
        response = await client.post(f"/api/bots/{bot.id}/chat", headers=O)
        assert response.status_code == 404
    finally:
        await client.aclose()


async def test_posting_in_an_earlier_chat_still_works_over_the_api(cfg, talk, user_id, bot):
    old = await talk.create_thread(user_id, bot.id)
    newest = await talk.create_thread(user_id, bot.id)
    app = create_app()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    try:
        await client.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
        chat = await client.post(f"/api/bots/{bot.id}/chat", headers=O)
        assert chat.status_code == 200 and chat.json()["id"] == newest.id
        assert set(chat.json()) == {"id", "bot_id", "title", "kind", "created_at", "updated_at"}
        posted = await client.post(f"/api/threads/{old.id}/messages", json={"text": "hello old chat"}, headers=O)
        assert posted.status_code in (200, 201, 202)
        again = await client.post(f"/api/bots/{bot.id}/chat", headers=O)
        assert again.json()["id"] == old.id   # the thread you last talked in carries on
        empty = await make_bot(cfg, user_id, "Fresh")
        made = await client.post(f"/api/bots/{empty.id}/chat", headers=O)
        assert made.status_code == 200 and made.json()["bot_id"] == empty.id
        assert (await client.post(f"/api/bots/{empty.id}/chat", headers=O)).json()["id"] == made.json()["id"]
    finally:
        await client.aclose()
