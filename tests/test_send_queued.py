"""``POST /api/threads/{id}/messages`` says whether the bot was already On it (plan Task 2)."""

from __future__ import annotations

import httpx

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from team_helpers import GatedModel, until, wait_idle
from test_threads_api import O, VALID_AVATAR, _async_client_as

BOT = {"name": "Scout", "job": "read news", "instructions": "", "avatar": VALID_AVATAR}


async def _rig(model):
    await init_db(load_config())
    app = create_app()
    app.state.turns._model = model
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot_id = (await alice.post("/api/bots", json=BOT, headers=O)).json()["id"]
    thread_id = (await alice.post(f"/api/bots/{bot_id}/threads", json={}, headers=O)).json()["id"]
    return app, alice, bot_id, thread_id


async def test_a_message_to_a_resting_bot_is_not_queued():
    model = GatedModel(["one"], hold=())
    app, alice, bot_id, thread_id = await _rig(model)
    r = await alice.post(f"/api/threads/{thread_id}/messages", json={"text": "hi"}, headers=O)
    assert r.status_code == 202
    body = r.json()
    assert body["queued"] is False
    assert body["message_id"]
    await wait_idle(app.state.turns)
    await alice.aclose()


async def test_a_message_to_a_bot_on_it_in_that_chat_is_steered_into_its_run():
    model = GatedModel(["one", "two"], hold=(1,))
    app, alice, bot_id, thread_id = await _rig(model)
    first = await alice.post(f"/api/threads/{thread_id}/messages", json={"text": "first"}, headers=O)
    await until(lambda: len(model.requests) == 1)
    second = await alice.post(f"/api/threads/{thread_id}/messages", json={"text": "second"}, headers=O)
    assert (first.json()["status"], first.json()["queued"]) == ("started", False)
    assert (second.json()["status"], second.json()["queued"]) == ("steered", False)
    model.release.set()
    await wait_idle(app.state.turns)
    assert len(model.requests) == 2  # the same run read it at its next boundary
    await alice.aclose()


async def test_a_message_to_a_bot_busy_in_another_chat_is_queued():
    model = GatedModel(["one", "two"], hold=(1,))
    app, alice, bot_id, thread_id = await _rig(model)
    await alice.post(f"/api/threads/{thread_id}/messages", json={"text": "first"}, headers=O)
    await until(lambda: len(model.requests) == 1)
    other = (await alice.post(f"/api/bots/{bot_id}/threads", json={}, headers=O)).json()["id"]
    second = await alice.post(f"/api/threads/{other}/messages", json={"text": "elsewhere"}, headers=O)
    assert (second.json()["status"], second.json()["queued"]) == ("queued", True)
    model.release.set()
    await wait_idle(app.state.turns)
    assert len(model.requests) == 2
    await alice.aclose()


async def test_queued_is_still_404_for_another_users_thread():
    app, alice, bot_id, thread_id = await _rig(GatedModel(["x"], hold=()))
    bob = await _async_client_as(app, "bob")
    r = await bob.post(f"/api/threads/{thread_id}/messages", json={"text": "hi"}, headers=O)
    assert r.status_code == 404
    await alice.aclose()
    await bob.aclose()
