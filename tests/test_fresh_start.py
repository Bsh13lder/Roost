"""Fresh start (owner, 2026-10-25: "Add fresh start ... it can see summary if necessary"): a chat's Fresh start
line hides every earlier web reply from the bot's next runs, so they start clean (no "from web content", remember
and routines work). Nothing is lost: ``search_chat`` still finds the hidden text, and reading it taints only
that run."""

from __future__ import annotations

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.talk.fresh_start import FRESH_START_KIND, FRESH_START_TEXT
from roost.talk.store import TalkStore
from roost.talk.turn import TAINT_PLACEHOLDER_TEXT, _history, _starts_tainted
from team_helpers import GatedModel, frames_so_far, make_bot, wait_idle
from test_reactions import BOT, _user_ids
from test_threads_api import O, _async_client_as


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _web_chat(cfg, user_id: str):
    talk = TalkStore(cfg)
    bot = await make_bot(cfg, user_id, "Gela")
    thread = await talk.create_thread(user_id, bot.id)
    await talk.add_message(user_id, thread.id, "user", "read Francis's chat")
    await talk.add_message(user_id, thread.id, "bot", "WEBWORDS from WhatsApp", tainted=True, author_bot_id=bot.id)
    return talk, bot, thread


async def test_without_fresh_start_the_recent_web_reply_keeps_the_run_tainted(cfg, user_id):
    talk, bot, thread = await _web_chat(cfg, user_id)
    history = await _history(talk, user_id, thread.id, bot.id, {})
    assert _starts_tainted((), history)


async def test_after_fresh_start_the_web_reply_is_hidden_and_the_run_starts_clean(cfg, user_id):
    talk, bot, thread = await _web_chat(cfg, user_id)
    await talk.add_message(user_id, thread.id, "system", FRESH_START_TEXT, kind=FRESH_START_KIND)
    await talk.add_message(user_id, thread.id, "user", "remember: keep replies short")
    history = await _history(talk, user_id, thread.id, bot.id, {})
    assert not _starts_tainted((), history)
    texts = [t.text for t in history.turns]
    assert "read Francis's chat" in texts and TAINT_PLACEHOLDER_TEXT in texts
    assert not any("WEBWORDS" in t for t in texts)


async def test_web_content_after_the_fresh_start_still_taints(cfg, user_id):
    talk, bot, thread = await _web_chat(cfg, user_id)
    await talk.add_message(user_id, thread.id, "system", FRESH_START_TEXT, kind=FRESH_START_KIND)
    await talk.add_message(user_id, thread.id, "bot", "NEWWEB", tainted=True, author_bot_id=bot.id)
    history = await _history(talk, user_id, thread.id, bot.id, {})
    assert _starts_tainted((), history)
    assert "NEWWEB" in [t.text for t in history.turns]


def test_the_placeholder_tells_the_bot_how_to_find_it_again():
    assert "search_chat" in TAINT_PLACEHOLDER_TEXT


# -- the route -----------------------------------------------------------------------------------------------

async def _rig():
    await init_db(load_config())
    app = create_app()
    app.state.turns._model = GatedModel(["hello"], hold=())
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot_id = (await alice.post("/api/bots", json=BOT, headers=O)).json()["id"]
    thread_id = (await alice.post(f"/api/bots/{bot_id}/threads", json={}, headers=O)).json()["id"]
    return app, alice, thread_id


async def test_the_route_posts_the_line_and_publishes_it():
    app, alice, thread_id = await _rig()
    screen = app.state.events.subscribe(next(iter(await _user_ids())))
    response = await alice.post(f"/api/threads/{thread_id}/fresh-start", headers=O)
    assert response.status_code == 200
    line = response.json()
    assert (line["role"], line["kind"], line["body"]) == ("system", FRESH_START_KIND, FRESH_START_TEXT)
    frames = [f for f in await frames_so_far(screen) if f["type"] == "message"]
    assert [f["message"]["id"] for f in frames] == [line["id"]]
    await wait_idle(app.state.turns)
    await alice.aclose()


async def test_another_users_thread_is_404_and_gets_no_line():
    app, alice, thread_id = await _rig()
    bob = await _async_client_as(app, "bob")
    assert (await bob.post(f"/api/threads/{thread_id}/fresh-start", headers=O)).status_code == 404
    kinds = [m["kind"] for m in (await alice.get(f"/api/threads/{thread_id}/messages")).json()]
    assert FRESH_START_KIND not in kinds
    await alice.aclose()
    await bob.aclose()
