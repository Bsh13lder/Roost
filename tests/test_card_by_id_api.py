"""One card by its id (mobile SERVER_NEEDS M1a): ``GET /api/stuck/{id}`` and ``GET /api/routine-proposals/{id}``.

Each answers the same shape as its list, also once the card is closed, and another user's id is a 404."""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.desk.stuck import Block, host_of_url
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.routines.models import ProposalPayload
from roost.routines.schedule import parse_schedule
from roost.stuck.models import CardDraft, CardState
from roost.stuck.store import StuckStore
from roost.talk.store import TalkStore
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}
PASSWORD = "pw-123456"
URL = "https://shop.example/kettle"
TIMES = {"kind": "times", "days": [1, 2, 3], "times": ["10:07"]}


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


async def _card(cfg, user_id, bot_id):
    thread = await TalkStore(cfg).create_thread(user_id, bot_id)
    block = Block(reason="challenge", url=URL, host=host_of_url(URL), note="")
    return await StuckStore(cfg).open(user_id, CardDraft(
        bot_id=bot_id, thread_id=thread.id, work_item_id=None, block=block, request="Find it", tainted=True))


async def _proposal(app, user, bot):
    thread, _ = await app.state.talk.ensure_main_thread(user.id, bot.id)
    payload = ProposalPayload(name="Morning news", instructions="Read it.", schedule=parse_schedule(TIMES))
    return await app.state.proposals.propose(user.id, bot.id, "create", payload, routine_id=None,
                                             thread_id=thread.id, tainted=False, from_routine=False)


async def test_a_stuck_card_by_id_matches_the_list_and_stays_readable_once_closed(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    card = await _card(cfg, alice.id, (await make_bot(cfg, alice.id, "Scout")).id)
    async with signed_in(app, "alice") as client:
        listed = (await client.get("/api/stuck")).json()
        one = await client.get(f"/api/stuck/{card.id}")
        assert one.status_code == 200 and one.json() == listed[0]

        await StuckStore(cfg).close(alice.id, card.id, CardState.GIVEN_UP)
        closed = (await client.get(f"/api/stuck/{card.id}")).json()
        assert closed["state"] == "given_up" and closed["closed_at"] is not None
        assert (await client.get("/api/stuck/no-such-card")).status_code == 404


async def test_another_users_stuck_card_is_404(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    await register_user(cfg, "bob", PASSWORD)
    card = await _card(cfg, alice.id, (await make_bot(cfg, alice.id, "Scout")).id)
    async with signed_in(app, "bob") as client:
        answer = await client.get(f"/api/stuck/{card.id}")
        assert answer.status_code == 404 and answer.json() == {"detail": "Card not found"}


async def test_a_routine_proposal_by_id_matches_the_list_and_shows_its_decision(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    proposal = await _proposal(app, alice, await make_bot(cfg, alice.id, "Scout"))
    async with signed_in(app, "alice") as client:
        listed = (await client.get("/api/routine-proposals")).json()["proposals"]
        one = await client.get(f"/api/routine-proposals/{proposal.id}")
        assert one.status_code == 200 and one.json() == listed[0]

        assert (await client.post(f"/api/routine-proposals/{proposal.id}/decline", headers=O)).status_code == 200
        assert (await client.get(f"/api/routine-proposals/{proposal.id}")).json()["state"] == "declined"


async def test_another_users_routine_proposal_is_404(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    await register_user(cfg, "bob", PASSWORD)
    proposal = await _proposal(app, alice, await make_bot(cfg, alice.id, "Scout"))
    async with signed_in(app, "bob") as client:
        answer = await client.get(f"/api/routine-proposals/{proposal.id}")
        assert answer.status_code == 404 and answer.json() == {"detail": "Proposal not found"}
