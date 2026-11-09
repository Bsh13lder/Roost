"""``POST /api/threads/{id}/messages/{message_id}/remember``: the Remember it button on a ``memory_offer`` line
saves the memory as the user's own word, once, and only for the user who owns the line."""

from __future__ import annotations

import json
import sqlite3

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.memory.offers import parse_offer, post_memory_offer
from roost.talk.store import TalkStore
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}
BAD_O = {"Origin": "http://evil.example"}


async def _login(app, cfg, username):
    await register_user(cfg, username, "pw-123456")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    assert (await client.post("/api/auth/login", json={"username": username, "password": "pw-123456"},
                              headers=O)).status_code == 200
    return client, (await client.get("/api/auth/me")).json()["id"]


@pytest.fixture
async def rig():
    cfg = load_config()
    await init_db(cfg)
    app = create_app()
    alice, alice_id = await _login(app, cfg, "alice")
    bob, bob_id = await _login(app, cfg, "bob")
    scout = await make_bot(cfg, alice_id, "Scout")
    thread = await TalkStore(cfg).create_thread(alice_id, scout.id)
    yield cfg, app, alice, alice_id, bob, scout, thread
    await alice.aclose()
    await bob.aclose()


async def _offer(cfg, app, user_id, bot_id, thread_id, text="Task alerts only, no budget alerts.",
                 kind="preference"):
    return await post_memory_offer(TalkStore(cfg), app.state.events, user_id, thread_id, bot_id, text, kind, 5)


def _url(thread_id, message_id):
    return f"/api/threads/{thread_id}/messages/{message_id}/remember"


def _rows(cfg, sql, params=()):
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


async def test_remember_it_saves_the_bots_memory_as_the_users_word(rig):
    cfg, app, alice, alice_id, bob, scout, thread = rig
    offer = await _offer(cfg, app, alice_id, scout.id, thread.id)
    r = await alice.post(_url(thread.id, offer.id), json={}, headers=O)
    assert r.status_code == 200
    out = r.json()
    assert out["memory"]["text"] == "Task alerts only, no budget alerts."
    assert out["memory"]["bot_id"] == scout.id and out["memory"]["source"] == "user"
    assert not out["memory"]["tainted"] and out["memory"]["importance"] == 5
    assert out["message"]["id"] == offer.id and out["message"]["kind"] == "memory_offer"
    assert json.loads(out["message"]["body"])["memory_id"] == out["memory"]["id"]
    stored = await TalkStore(cfg).get_message(alice_id, offer.id)
    assert parse_offer(stored.body).memory_id == out["memory"]["id"] and stored.tainted
    assert _rows(cfg, "SELECT kind, scope, source FROM memories") == [("preference", scout.id, "user")]


async def test_about_you_goes_to_the_shared_memory(rig):
    cfg, app, alice, alice_id, bob, scout, thread = rig
    offer = await _offer(cfg, app, alice_id, scout.id, thread.id, "Ana likes orchids.", "about_you")
    r = await alice.post(_url(thread.id, offer.id), json={}, headers=O)
    assert r.status_code == 200 and r.json()["memory"]["bot_id"] is None
    assert _rows(cfg, "SELECT scope FROM memories") == [("*",)]


async def test_pressing_twice_saves_once(rig):
    cfg, app, alice, alice_id, bob, scout, thread = rig
    offer = await _offer(cfg, app, alice_id, scout.id, thread.id)
    first = await alice.post(_url(thread.id, offer.id), json={}, headers=O)
    second = await alice.post(_url(thread.id, offer.id), json={}, headers=O)
    assert first.status_code == second.status_code == 200
    assert first.json()["memory"]["id"] == second.json()["memory"]["id"]
    assert _rows(cfg, "SELECT COUNT(*) FROM memories") == [(1,)]


async def test_another_users_line_is_a_404(rig):
    cfg, app, alice, alice_id, bob, scout, thread = rig
    offer = await _offer(cfg, app, alice_id, scout.id, thread.id)
    r = await bob.post(_url(thread.id, offer.id), json={}, headers=O)
    assert r.status_code == 404
    assert _rows(cfg, "SELECT COUNT(*) FROM memories") == [(0,)]


async def test_a_wrong_thread_or_a_plain_message_is_a_404(rig):
    cfg, app, alice, alice_id, bob, scout, thread = rig
    offer = await _offer(cfg, app, alice_id, scout.id, thread.id)
    other = await TalkStore(cfg).create_thread(alice_id, scout.id)
    plain = await TalkStore(cfg).add_message(alice_id, thread.id, "bot", "hello", author_bot_id=scout.id)
    assert (await alice.post(_url(other.id, offer.id), json={}, headers=O)).status_code == 404
    assert (await alice.post(_url(thread.id, plain.id), json={}, headers=O)).status_code == 404
    assert (await alice.post(_url(thread.id, "nope"), json={}, headers=O)).status_code == 404


async def test_the_body_is_strict_and_the_origin_is_checked(rig):
    cfg, app, alice, alice_id, bob, scout, thread = rig
    offer = await _offer(cfg, app, alice_id, scout.id, thread.id)
    assert (await alice.post(_url(thread.id, offer.id), json={"text": "x"}, headers=O)).status_code == 422
    assert (await alice.post(_url(thread.id, offer.id), json={}, headers=BAD_O)).status_code == 403
    assert _rows(cfg, "SELECT COUNT(*) FROM memories") == [(0,)]
