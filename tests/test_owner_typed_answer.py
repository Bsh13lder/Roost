"""W1 (docs/plans/2026-10-23-roost-owner-words.md): a typed plain yes or no in a bot's chat answers the one Ask card
waiting there, through the card's own Yes/No path. Two cards, a Proposal, an options card or any other words keep
the usual message path."""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
import pytest

from approval_helpers import ORIGIN
from roost.approvals.models import ApprovalDraft, PendingCall
from roost.approvals.store import ApprovalStore
from roost.approvals.typed_answer import typed_answer
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.talk.store import TalkStore
from team_helpers import make_bot, wait_idle

PASSWORD = "pw-123456"


@pytest.mark.parametrize("text", ["yes", "Yes!", "ok", "OK 👍", "okay.", "sure", "go ahead", "do it", "yes do it",
                                  "ok do it", "sí", "Si", "vale", "dale", "hazlo", "adelante", "yep", "yeah"])
def test_plain_yes_words(text):
    assert typed_answer(text) == "yes"


@pytest.mark.parametrize("text", ["no", "No.", "nope", "don't", "stop", "cancel", "no gracias", "no thanks"])
def test_plain_no_words(text):
    assert typed_answer(text) == "no"


@pytest.mark.parametrize("text", ["yes but change the price first", "ok send it to James and Iurie tomorrow please",
                                  "", "   ", "what is this?", "no wait, read it first", "yes no"])
def test_anything_else_is_not_an_answer(text):
    assert typed_answer(text) is None


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@asynccontextmanager
async def _signed_in(app, username: str):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        login = await client.post("/api/auth/login", json={"username": username, "password": PASSWORD}, headers=ORIGIN)
        assert login.status_code == 200
        try:
            yield client
        finally:
            await wait_idle(app.state.turns, timeout=8)


def _add_task_step() -> PendingCall:
    return PendingCall(tool="add_task", arguments={"title": "CANARY-typed-yes"}, topic="tasks",
                       title="Add a task: “CANARY-typed-yes”")


async def _card(cfg, user_id: str, bot_id: str, thread_id: str, *, kind: str = "ask", step: PendingCall | None = None):
    return await ApprovalStore(cfg).open(user_id, ApprovalDraft(
        bot_id=bot_id, thread_id=thread_id, work_item_id=None, kind=kind, steps=(step or _add_task_step(),),
        request="add it", tainted=False))


async def _setup(cfg):
    alice = await register_user(cfg, "alice", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Scout")
    thread = await TalkStore(cfg).create_thread(alice.id, bot.id)
    return alice, bot, thread


async def _tasks(cfg, user_id: str) -> int:
    async with db_session(cfg) as db:
        return (await (await db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ?", (user_id,))).fetchone())[0]


async def _post(client, thread_id: str, text: str):
    response = await client.post(f"/api/threads/{thread_id}/messages", json={"text": text}, headers=ORIGIN)
    assert response.status_code == 202, response.text
    return response.json()


async def test_typed_yes_answers_the_one_waiting_card(cfg):
    alice, bot, thread = await _setup(cfg)
    card = await _card(cfg, alice.id, bot.id, thread.id)
    app = create_app(cfg)
    async with _signed_in(app, "alice") as client:
        out = await _post(client, thread.id, "ok do it")
    assert out["answered_card"] == card.id and out["status"] == "steered"
    closed = await ApprovalStore(cfg).get(alice.id, card.id)
    assert closed.state.value == "approved"
    assert await _tasks(cfg, alice.id) == 1
    bodies = [m.body for m in await TalkStore(cfg).list_messages(alice.id, thread.id)]
    assert "ok do it" in bodies                                    # your message still shows
    assert any(body.startswith("Yes: ") for body in bodies)         # the card's own Yes line


async def test_typed_no_declines_and_runs_nothing(cfg):
    alice, bot, thread = await _setup(cfg)
    card = await _card(cfg, alice.id, bot.id, thread.id)
    app = create_app(cfg)
    async with _signed_in(app, "alice") as client:
        out = await _post(client, thread.id, "no")
    assert out["answered_card"] == card.id
    assert (await ApprovalStore(cfg).get(alice.id, card.id)).state.value == "declined"
    assert await _tasks(cfg, alice.id) == 0


async def test_two_waiting_cards_keep_the_usual_path(cfg):
    """One open card per bot, so the second waits for another bot in this chat (a mention's handoff)."""
    alice, bot, thread = await _setup(cfg)
    helper = await make_bot(cfg, alice.id, "Helper")
    first = await _card(cfg, alice.id, bot.id, thread.id)
    second = await _card(cfg, alice.id, helper.id, thread.id)
    app = create_app(cfg)
    async with _signed_in(app, "alice") as client:
        out = await _post(client, thread.id, "yes")
    assert out.get("answered_card") is None
    for card in (first, second):
        assert (await ApprovalStore(cfg).get(alice.id, card.id)).state.value == "open"


async def test_a_proposal_card_is_not_answered_by_words(cfg):
    alice, bot, thread = await _setup(cfg)
    card = await _card(cfg, alice.id, bot.id, thread.id, kind="plan")
    app = create_app(cfg)
    async with _signed_in(app, "alice") as client:
        out = await _post(client, thread.id, "yes")
    assert out.get("answered_card") is None
    assert (await ApprovalStore(cfg).get(alice.id, card.id)).state.value == "open"


async def test_an_options_card_is_not_answered_by_words(cfg):
    alice, bot, thread = await _setup(cfg)
    step = PendingCall(tool="ask_choice", arguments={"question": "Which one?", "options": ["A", "B"], "safe": 0},
                       topic="tasks", title="Which one?")
    card = await _card(cfg, alice.id, bot.id, thread.id, step=step)
    app = create_app(cfg)
    async with _signed_in(app, "alice") as client:
        out = await _post(client, thread.id, "yes")
    assert out.get("answered_card") is None
    assert (await ApprovalStore(cfg).get(alice.id, card.id)).state.value == "open"


async def test_a_card_in_another_chat_is_not_answered(cfg):
    alice, bot, thread = await _setup(cfg)
    other = await TalkStore(cfg).create_thread(alice.id, bot.id)
    card = await _card(cfg, alice.id, bot.id, other.id)
    app = create_app(cfg)
    async with _signed_in(app, "alice") as client:
        out = await _post(client, thread.id, "yes")
    assert out.get("answered_card") is None
    assert (await ApprovalStore(cfg).get(alice.id, card.id)).state.value == "open"


async def test_other_words_with_a_card_keep_the_usual_path(cfg):
    alice, bot, thread = await _setup(cfg)
    card = await _card(cfg, alice.id, bot.id, thread.id)
    app = create_app(cfg)
    async with _signed_in(app, "alice") as client:
        out = await _post(client, thread.id, "wait, what does it add?")
    assert out.get("answered_card") is None
    assert (await ApprovalStore(cfg).get(alice.id, card.id)).state.value == "open"
