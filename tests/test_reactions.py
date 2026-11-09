"""Tapbacks (chat-feel Task 8): ``PUT /api/threads/{id}/messages/{id}/reaction``.

A reaction is a ``reaction`` message (role user, sealed body JSON ``{"target_id", "key"}``); it is published as
a ``message`` frame, never replayed to the model, queues no work, and is never a chat-list preview."""

from __future__ import annotations

import json

import httpx

from roost.config import load_config
from roost.constants import REACTION_KEYS
from roost.db.connection import db_session, init_db
from roost.gateway.app import create_app
from roost.talk.reactions import ReactionIn, reaction_body
from team_helpers import GatedModel, wait_idle
from test_threads_api import BAD_O, O, VALID_AVATAR, _async_client_as

BOT = {"name": "Scout", "job": "read news", "instructions": "", "avatar": VALID_AVATAR}


async def _rig():
    await init_db(load_config())
    app = create_app()
    app.state.turns._model = GatedModel(["hello"], hold=())
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot_id = (await alice.post("/api/bots", json=BOT, headers=O)).json()["id"]
    thread_id = (await alice.post(f"/api/bots/{bot_id}/threads", json={}, headers=O)).json()["id"]
    sent = await alice.post(f"/api/threads/{thread_id}/messages", json={"text": "hi"}, headers=O)
    await wait_idle(app.state.turns)
    return app, alice, bot_id, thread_id, sent.json()["message_id"]


def _url(thread_id: str, message_id: str) -> str:
    return f"/api/threads/{thread_id}/messages/{message_id}/reaction"


async def _count(table_kind: str) -> int:
    async with db_session(load_config()) as db:
        row = await (await db.execute("SELECT COUNT(*) FROM messages WHERE kind = ?", (table_kind,))).fetchone()
    return row[0]


def test_the_body_is_json_and_the_keys_are_fixed():
    assert json.loads(reaction_body("m1", "heart")) == {"target_id": "m1", "key": "heart"}
    assert json.loads(reaction_body("m1", None)) == {"target_id": "m1", "key": None}
    assert REACTION_KEYS == ("thumbs_up", "heart", "laugh", "check", "question")
    assert ReactionIn(key=None).key is None


async def test_a_reaction_is_stored_sealed_and_published():
    app, alice, bot_id, thread_id, message_id = await _rig()
    sub = app.state.events.subscribe(next(iter(await _user_ids())))
    r = await alice.put(_url(thread_id, message_id), json={"key": "heart"}, headers=O)
    assert r.status_code == 200
    out = r.json()
    assert out["kind"] == "reaction" and out["role"] == "user"
    assert json.loads(out["body"]) == {"target_id": message_id, "key": "heart"}
    async with db_session(load_config()) as db:
        [row] = await (await db.execute("SELECT body FROM messages WHERE id = ?", (out["id"],))).fetchall()
    assert row["body"].startswith("enc:v2") and "heart" not in row["body"]
    frames = [f async for f in _drain(sub)]
    assert [f["message"]["id"] for f in frames if f["type"] == "message" and f["message"]["kind"] == "reaction"] == [out["id"]]
    await alice.aclose()


async def _user_ids():
    async with db_session(load_config()) as db:
        return [row["id"] for row in await (await db.execute("SELECT id FROM users")).fetchall()]


async def _drain(sub):
    from team_helpers import frames_so_far
    for frame in await frames_so_far(sub):
        yield frame


async def test_a_reaction_never_reaches_the_model_or_queues_work():
    app, alice, bot_id, thread_id, message_id = await _rig()
    model = app.state.turns._model
    before = len(model.requests)
    async with db_session(load_config()) as db:
        items_before = (await (await db.execute("SELECT COUNT(*) FROM work_items")).fetchone())[0]
    await alice.put(_url(thread_id, message_id), json={"key": "check"}, headers=O)
    await wait_idle(app.state.turns)
    async with db_session(load_config()) as db:
        items_after = (await (await db.execute("SELECT COUNT(*) FROM work_items")).fetchone())[0]
    assert items_after == items_before and len(model.requests) == before
    from roost.talk.turn import _MODEL_KINDS
    assert "reaction" not in _MODEL_KINDS
    await alice.aclose()


async def test_clearing_stores_a_null_key():
    app, alice, bot_id, thread_id, message_id = await _rig()
    r = await alice.put(_url(thread_id, message_id), json={"key": None}, headers=O)
    assert r.status_code == 200 and json.loads(r.json()["body"])["key"] is None
    await alice.aclose()


async def test_an_unknown_key_is_422():
    app, alice, bot_id, thread_id, message_id = await _rig()
    for body in ({"key": "poop"}, {"key": "heart", "extra": 1}, {}):
        r = await alice.put(_url(thread_id, message_id), json=body, headers=O)
        assert r.status_code == 422, body
    assert await _count("reaction") == 0
    await alice.aclose()


async def test_a_reaction_on_another_threads_message_is_404():
    app, alice, bot_id, thread_id, message_id = await _rig()
    other = (await alice.post(f"/api/bots/{bot_id}/threads", json={}, headers=O)).json()["id"]
    assert (await alice.put(_url(other, message_id), json={"key": "heart"}, headers=O)).status_code == 404
    assert (await alice.put(_url(thread_id, "nope"), json={"key": "heart"}, headers=O)).status_code == 404
    assert await _count("reaction") == 0
    await alice.aclose()


async def test_another_users_thread_is_404():
    app, alice, bot_id, thread_id, message_id = await _rig()
    bob = await _async_client_as(app, "bob")
    assert (await bob.put(_url(thread_id, message_id), json={"key": "heart"}, headers=O)).status_code == 404
    assert await _count("reaction") == 0
    await alice.aclose()
    await bob.aclose()


async def test_a_reaction_is_never_a_chat_preview():
    app, alice, bot_id, thread_id, message_id = await _rig()
    before = await alice.get("/api/chats")
    await alice.put(_url(thread_id, message_id), json={"key": "heart"}, headers=O)
    after = await alice.get("/api/chats")
    pick = lambda r: [(row["preview"], row["last_at"]) for row in r.json() if row["id"] == bot_id]
    assert pick(after) == pick(before)
    assert "heart" not in json.dumps(after.json())
    await alice.aclose()


async def test_the_route_needs_the_origin():
    app, alice, bot_id, thread_id, message_id = await _rig()
    r = await alice.put(_url(thread_id, message_id), json={"key": "heart"}, headers=BAD_O)
    assert r.status_code == 403
    assert await _count("reaction") == 0
    await alice.aclose()
