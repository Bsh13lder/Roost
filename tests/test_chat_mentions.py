"""@bot in a bot's chat: the mention parser, the router that hands the message over, and the HTTP route."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from typing import AsyncIterator

import httpx
import pytest

import roost.talk.runner as runner_module
from roost.config import load_config
from roost.constants import MENTIONS_PER_MESSAGE_MAX
from roost.db.connection import db_session, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.talk.mentions import MentionRouter, chat_mentions
from roost.work.models import HandoffResult
from team_helpers import GatedModel, make_bot, make_rig, say, team_model, until, wait_idle

ORIGIN = {"Origin": "http://127.0.0.1:18800"}
PASSWORD = "pw-123456"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", PASSWORD)).id


@pytest.fixture
async def team(cfg, user_id):
    return {name: await make_bot(cfg, user_id, name) for name in ("Chief", "Scout", "Quill", "Scout Two")}


def _team(team) -> tuple:
    return tuple(team.values())


# --- the parser --------------------------------------------------------------------------------------------------

def test_a_message_that_starts_with_a_mention_is_for_that_bot_only(team):
    found = chat_mentions("@Scout find the market hours", _team(team), team["Chief"].id)
    assert found.bot_ids == (team["Scout"].id,) and found.addressed_only is True


def test_a_mention_later_in_the_text_also_goes_to_the_chat_bot(team):
    found = chat_mentions("Plan Saturday, and ask @scout for prices", _team(team), team["Chief"].id)
    assert found.bot_ids == (team["Scout"].id,) and found.addressed_only is False


def test_the_chat_bot_unknown_names_and_email_addresses_are_ignored(team):
    for text in ("@Chief hello", "@Nobody hello", "write to me@scout.com", "@Scouting is fun", "@everyone hi"):
        found = chat_mentions(text, _team(team), team["Chief"].id)
        assert found.bot_ids == () and found.addressed_only is False, text


def test_mentions_keep_text_order_and_the_longest_name_wins(team):
    found = chat_mentions("  @Quill and @Scout Two, then @Scout", _team(team), team["Chief"].id)
    assert found.bot_ids == (team["Quill"].id, team["Scout Two"].id, team["Scout"].id)
    assert found.addressed_only is True


def test_at_most_a_few_bots_per_message(team):
    many = {f"B{n}": n for n in range(MENTIONS_PER_MESSAGE_MAX + 2)}
    text = " ".join(f"@{name}" for name in many)
    bots = tuple(replace(team["Scout"], id=f"id-{n}", name=name) for name, n in many.items())
    found = chat_mentions(text, bots, team["Chief"].id)
    assert found.bot_ids == tuple(f"id-{n}" for n in range(MENTIONS_PER_MESSAGE_MAX))


# --- the router --------------------------------------------------------------------------------------------------

def _router(rig) -> MentionRouter:
    return MentionRouter(rig.talk, rig.events, rig.runner)


async def _messages(rig, user_id, thread_id):
    return [(m.role, m.kind, m.author_bot_id, m.body) for m in await rig.talk.list_messages(user_id, thread_id)]


async def test_the_mentioned_bot_answers_in_the_same_chat(cfg, user_id, team):
    rig = make_rig(cfg, team_model({"Scout": [say("Opens at 9:00")]}))
    chief, scout = team["Chief"], team["Scout"]
    thread = await rig.talk.create_thread(user_id, chief.id)
    router = _router(rig)
    await router.route(user_id, chief, thread.id, "@Scout when does the market open?", (scout,))
    await router.wait()
    await wait_idle(rig.runner)

    assert await _messages(rig, user_id, thread.id) == [
        ("activity", "handoff", None, "You → Scout: @Scout when does the market open?"),
        ("bot", "text", scout.id, "Opens at 9:00"),
    ]
    from_chief = next(t for t in await rig.talk.list_threads(user_id, scout.id) if t.title == "From Chief")
    assert await _messages(rig, user_id, from_chief.id) == [
        ("user", "handoff", None, "You → Scout: @Scout when does the market open?"),
        ("bot", "text", scout.id, "Opens at 9:00"),
    ]
    async with db_session(cfg) as db:
        [item] = await (await db.execute(
            "SELECT kind, state, tainted, depth FROM work_items WHERE bot_id = ?", (scout.id,))).fetchall()
    assert (item["kind"], item["state"], item["tainted"], item["depth"]) == ("handoff", "done", 0, 1)
    scout_call = next(r for r in rig.model.requests if r.agent == "Scout")
    assert scout_call.turns[-1].role == "user" and "when does the market open?" in scout_call.turns[-1].text


async def test_an_off_duty_bot_gets_a_notice_instead(cfg, user_id, team):
    rig = make_rig(cfg, team_model({}))
    chief, quill = team["Chief"], team["Quill"]
    await rig.runner.set_off_duty(user_id, quill.id, True)
    quill = await rig.bots.get(user_id, quill.id)
    thread = await rig.talk.create_thread(user_id, chief.id)
    router = _router(rig)
    await router.route(user_id, chief, thread.id, "@Quill write it", (quill,))
    await router.wait()
    assert await _messages(rig, user_id, thread.id) == [("system", "notice", None, "Quill is off duty.")]


async def test_a_bot_that_does_not_answer_in_time_leaves_a_notice(cfg, user_id, team, monkeypatch):
    monkeypatch.setattr(runner_module, "HANDOFF_TIMEOUT_S", 0.05)
    model = GatedModel(["late answer"], hold=(1,))
    rig = make_rig(cfg, model)
    chief, scout = team["Chief"], team["Scout"]
    thread = await rig.talk.create_thread(user_id, chief.id)
    router = _router(rig)
    await router.route(user_id, chief, thread.id, "@Scout slow job", (scout,))
    await router.wait()
    rows = await _messages(rig, user_id, thread.id)
    assert rows[-1][:2] == ("system", "notice") and rows[-1][3].startswith("Scout did not answer")
    model.release.set()
    await wait_idle(rig.runner)


async def test_two_bots_are_asked_at_once_and_each_answers(cfg, user_id, team):
    rig = make_rig(cfg, team_model({"Scout": [say("52 EUR")], "Quill": [say("rice, eggs")]}))
    chief = team["Chief"]
    thread = await rig.talk.create_thread(user_id, chief.id)
    router = _router(rig)
    await router.route(user_id, chief, thread.id, "@Scout @Quill plan Saturday", (team["Scout"], team["Quill"]))
    await router.wait()
    await wait_idle(rig.runner)
    answers = {(m[2], m[3]) for m in await _messages(rig, user_id, thread.id) if m[0] == "bot"}
    assert answers == {(team["Scout"].id, "52 EUR"), (team["Quill"].id, "rice, eggs")}


async def test_close_cancels_open_asks(cfg, user_id, team):
    model = GatedModel(["never"], hold=(1,))
    rig = make_rig(cfg, model)
    thread = await rig.talk.create_thread(user_id, team["Chief"].id)
    router = _router(rig)
    await router.route(user_id, team["Chief"], thread.id, "@Scout wait", (team["Scout"],))
    await until(lambda: bool(model.requests))
    await router.close()
    await router.wait()
    await rig.runner.stop(user_id, team["Scout"].id)
    model.release.set()
    await wait_idle(rig.runner)


# --- over HTTP ---------------------------------------------------------------------------------------------------

@asynccontextmanager
async def signed_in(app, username: str) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        assert (await client.post("/api/auth/login", json={"username": username, "password": PASSWORD},
                                  headers=ORIGIN)).status_code == 200
        yield client


async def _http_rig(cfg, user_id):
    app = create_app(cfg)
    chief = await make_bot(cfg, user_id, "Chief")
    scout = await make_bot(cfg, user_id, "Scout")
    thread, _ = await app.state.talk.ensure_main_thread(user_id, chief.id)
    return app, chief, scout, thread


async def _settle(app):
    await app.state.mentions.wait()
    await wait_idle(app.state.turns, timeout=8)


async def test_post_routes_an_addressed_message_to_the_mentioned_bot_only(cfg, user_id):
    app, chief, scout, thread = await _http_rig(cfg, user_id)
    async with signed_in(app, "alice") as client:
        posted = await client.post(f"/api/threads/{thread.id}/messages", json={"text": "@scout hi there"},
                                   headers=ORIGIN)
        assert posted.status_code == 202
        assert posted.json()["mentioned"] == [scout.id] and posted.json()["queued"] is False
        await _settle(app)
    rows = await app.state.talk.list_messages(user_id, thread.id)
    assert [(m.role, m.author_bot_id) for m in rows] == [("user", None), ("activity", None), ("bot", scout.id)]
    async with db_session(cfg) as db:
        chief_items = await (await db.execute(
            "SELECT COUNT(*) FROM work_items WHERE bot_id = ?", (chief.id,))).fetchone()
    assert chief_items[0] == 0


async def test_post_with_a_mention_later_still_goes_to_the_chat_bot(cfg, user_id):
    app, chief, scout, thread = await _http_rig(cfg, user_id)
    async with signed_in(app, "alice") as client:
        posted = await client.post(f"/api/threads/{thread.id}/messages", json={"text": "hello, and ask @Scout too"},
                                   headers=ORIGIN)
        assert posted.json()["mentioned"] == [scout.id]
        await _settle(app)
    authors = [m.author_bot_id for m in await app.state.talk.list_messages(user_id, thread.id) if m.role == "bot"]
    assert sorted(authors) == sorted([chief.id, scout.id])


async def test_post_without_a_known_mention_is_unchanged(cfg, user_id):
    app, chief, scout, thread = await _http_rig(cfg, user_id)
    stranger = (await register_user(cfg, "bob", PASSWORD)).id
    await make_bot(cfg, stranger, "Mallory")
    async with signed_in(app, "alice") as client:
        posted = await client.post(f"/api/threads/{thread.id}/messages", json={"text": "@Mallory and @Nobody hi"},
                                   headers=ORIGIN)
        assert posted.json()["mentioned"] == []
        await _settle(app)
    authors = [m.author_bot_id for m in await app.state.talk.list_messages(user_id, thread.id) if m.role == "bot"]
    assert authors == [chief.id]


async def test_mentions_only_route_in_a_bots_chat(cfg, user_id):
    app, chief, scout, _thread = await _http_rig(cfg, user_id)
    peer = await app.state.talk.find_or_create_peer_thread(user_id, chief.id, scout.id, title="From Scout")
    async with signed_in(app, "alice") as client:
        posted = await client.post(f"/api/threads/{peer.id}/messages", json={"text": "@Scout hi"}, headers=ORIGIN)
        assert posted.json()["mentioned"] == []
        await _settle(app)


# --- answers that are not answers ------------------------------------------------------------------------------

class _Turns:
    """A ``hand_off`` stand-in: answers with ``result`` (after running ``prepare``), or raises it."""

    def __init__(self, result):
        self.result = result

    async def hand_off(self, user_id, asker_bot_id, target_bot_id, prepare):
        assert asker_bot_id == "you"
        await prepare()
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


async def _route_with(rig, user_id, team, result) -> list:
    thread = await rig.talk.create_thread(user_id, team["Chief"].id)
    router = MentionRouter(rig.talk, rig.events, _Turns(result))
    await router.route(user_id, team["Chief"], thread.id, "@Scout go", (team["Scout"],))
    await router.wait()
    return [(m.role, m.body) for m in await rig.talk.list_messages(user_id, thread.id)][1:]


async def test_an_empty_answer_a_refusal_and_an_error_each_leave_a_notice(cfg, user_id, team):
    rig = make_rig(cfg, team_model({}))
    cases = (
        (HandoffResult(status="done", text="  "), "Scout finished without an answer."),
        (HandoffResult(status="refused"), "Scout is busy with this chat's work. Try again in a moment."),
        (RuntimeError("boom"), "Scout ran into a problem and did not answer."),
    )
    for result, text in cases:
        assert await _route_with(rig, user_id, team, result) == [("system", text)]


async def test_a_tainted_answer_stays_tainted(cfg, user_id, team):
    rig = make_rig(cfg, team_model({}))
    thread = await rig.talk.create_thread(user_id, team["Chief"].id)
    router = MentionRouter(rig.talk, rig.events, _Turns(HandoffResult(status="done", text="from a page", tainted=True)))
    await router.route(user_id, team["Chief"], thread.id, "@Scout read it", (team["Scout"],))
    await router.wait()
    answer = (await rig.talk.list_messages(user_id, thread.id))[-1]
    assert (answer.body, answer.tainted, answer.author_bot_id) == ("from a page", True, team["Scout"].id)
