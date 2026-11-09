"""The Ask card's buttons over HTTP (approval plan Task 8)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest

from approval_helpers import ORIGIN
from roost.approvals.models import ApprovalDraft, PendingCall
from roost.approvals.store import ApprovalStore
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.talk.store import TalkStore
from team_helpers import make_bot, wait_idle

PASSWORD = "pw-123456"
CANARY_TITLE = "Add a task: “CANARY-title-9137”"


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


async def _card(cfg, user_id: str, bot_id: str, *, tool="add_task", arguments=None, session_offer=False):
    thread = await TalkStore(cfg).create_thread(user_id, bot_id)
    step = PendingCall(tool=tool, arguments=arguments or {"title": "CANARY-title-9137"}, topic="tasks",
                       title=CANARY_TITLE, session_offer=session_offer)
    return await ApprovalStore(cfg).open(user_id, ApprovalDraft(
        bot_id=bot_id, thread_id=thread.id, work_item_id=None, kind="ask", steps=(step,),
        request="add it", tainted=False, session_offer=session_offer))


async def test_only_one_press_wins(cfg):
    alice = await register_user(cfg, "alice", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Scout")
    card = await _card(cfg, alice.id, bot.id)
    app = create_app(cfg)
    async with _signed_in(app, "alice") as client:
        first = await client.post(f"/api/approvals/{card.id}/answer", json={"answer": "yes"}, headers=ORIGIN)
        second = await client.post(f"/api/approvals/{card.id}/answer", json={"answer": "yes"}, headers=ORIGIN)
        assert first.status_code == 200 and first.json()["state"] == "approved"
        assert second.status_code == 409 and second.json() == {"detail": "Already answered."}
    async with db_session(cfg) as db:
        count = (await (await db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ?", (alice.id,))).fetchone())[0]
    assert count == 1


async def test_two_presses_at_once_run_the_call_once(cfg):
    alice = await register_user(cfg, "alice", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Scout")
    card = await _card(cfg, alice.id, bot.id)
    app = create_app(cfg)
    async with _signed_in(app, "alice") as client:
        url = f"/api/approvals/{card.id}/answer"
        results = await asyncio.gather(*(client.post(url, json={"answer": "yes"}, headers=ORIGIN) for _ in range(2)))
        assert sorted(r.status_code for r in results) == [200, 409]
    async with db_session(cfg) as db:
        count = (await (await db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ?", (alice.id,))).fetchone())[0]
    assert count == 1


async def test_cards_are_sealed_and_another_users_card_is_404(cfg):
    alice = await register_user(cfg, "alice", PASSWORD)
    await register_user(cfg, "bob", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Scout")
    card = await _card(cfg, alice.id, bot.id)
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT steps, request FROM approval_cards WHERE id = ?", (card.id,))).fetchone()
    assert row["steps"].startswith("enc:v2:") and row["request"].startswith("enc:v2:")
    assert "CANARY" not in row["steps"]
    app = create_app(cfg)
    async with _signed_in(app, "bob") as client:
        assert (await client.get(f"/api/approvals/{card.id}")).status_code == 404
        assert (await client.get("/api/approvals")).json() == []
        answer = await client.post(f"/api/approvals/{card.id}/answer", json={"answer": "yes"}, headers=ORIGIN)
        assert answer.status_code == 404
    async with _signed_in(app, "alice") as client:
        body = (await client.get(f"/api/approvals/{card.id}")).json()
        assert body["steps"][0]["title"] == CANARY_TITLE and "request" not in body and "user_id" not in body
        assert [c["id"] for c in (await client.get("/api/approvals")).json()] == [card.id]


async def test_answer_needs_the_origin(cfg):
    alice = await register_user(cfg, "alice", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Scout")
    card = await _card(cfg, alice.id, bot.id)
    app = create_app(cfg)
    async with _signed_in(app, "alice") as client:
        bad = await client.post(f"/api/approvals/{card.id}/answer", json={"answer": "yes"},
                                headers={"Origin": "http://evil.example"})
        assert bad.status_code == 403
        assert (await client.get(f"/api/approvals/{card.id}")).json()["state"] == "open"


async def test_yes_for_this_session_is_only_for_read_cards(cfg):
    alice = await register_user(cfg, "alice", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Scout")
    card = await _card(cfg, alice.id, bot.id)
    app = create_app(cfg)
    async with _signed_in(app, "alice") as client:
        answer = await client.post(f"/api/approvals/{card.id}/answer", json={"answer": "yes_session"}, headers=ORIGIN)
        assert answer.status_code == 422
        assert (await client.get(f"/api/approvals/{card.id}")).json()["state"] == "open"


async def test_a_bad_answer_is_422(cfg):
    alice = await register_user(cfg, "alice", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Scout")
    card = await _card(cfg, alice.id, bot.id)
    app = create_app(cfg)
    async with _signed_in(app, "alice") as client:
        url = f"/api/approvals/{card.id}/answer"
        assert (await client.post(url, json={"answer": "maybe"}, headers=ORIGIN)).status_code == 422
        assert (await client.post(url, json={"answer": "yes", "extra": 1}, headers=ORIGIN)).status_code == 422
        assert (await client.post(url, json={"answer": "accept"}, headers=ORIGIN)).status_code == 422


async def test_a_card_from_a_routine_run_names_its_routine(cfg):
    """Owner, 2026-11-05: My turn opened the bot's chat for a routine's card, and the card was in the run log."""
    from roost.approvals.models import ApprovalDraft as Draft
    from roost.routines.models import RoutineDraft
    from roost.routines.schedule import parse_schedule
    from roost.routines.store import RoutineStore

    alice = await register_user(cfg, "alice", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Gela")
    routine = await RoutineStore(cfg, TalkStore(cfg)).create(alice.id, RoutineDraft(
        bot_id=bot.id, name="Price", instructions="Tell me the price.", created_by="user",
        schedule=parse_schedule({"kind": "times", "days": [1], "times": ["09:00"]})))
    step = PendingCall(tool="add_task", arguments={"title": "x"}, topic="tasks", title="Add a task")
    await ApprovalStore(cfg).open(alice.id, Draft(
        bot_id=bot.id, thread_id=routine.thread_id, work_item_id=None, kind="ask", steps=(step,),
        request="", tainted=True, session_offer=False))
    chat_card = await _card(cfg, alice.id, (await make_bot(cfg, alice.id, "Scout")).id)
    app = create_app(cfg)
    async with _signed_in(app, "alice") as client:
        cards = {c["bot_id"]: c for c in (await client.get("/api/approvals")).json()}
    assert cards[bot.id]["routine_id"] == routine.id
    assert cards[chat_card.bot_id]["routine_id"] is None
