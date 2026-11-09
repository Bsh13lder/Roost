"""The proposal routes: list, approve, decline; another user's proposal is 404; a second press is 409."""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.routines.models import ProposalPayload
from roost.routines.schedule import parse_schedule
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}
PASSWORD = "pw-123456"
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


async def _proposal(app, user, bot):
    thread, _ = await app.state.talk.ensure_main_thread(user.id, bot.id)
    payload = ProposalPayload(name="Morning news", instructions="Read it.", schedule=parse_schedule(TIMES))
    return await app.state.proposals.propose(user.id, bot.id, "create", payload, routine_id=None,
                                             thread_id=thread.id, tainted=True, from_routine=True)


async def test_list_approve_and_decline(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Scout")
    first, second = await _proposal(app, alice, bot), await _proposal(app, alice, bot)
    async with signed_in(app, "alice") as client:
        listed = (await client.get("/api/routine-proposals?state=open")).json()["proposals"]
        assert {p["id"] for p in listed} == {first.id, second.id}
        assert listed[0]["tainted"] is True and listed[0]["from_routine"] is True and len(listed[0]["next"]) == 3

        approved = await client.post(f"/api/routine-proposals/{first.id}/approve", headers=O)
        declined = await client.post(f"/api/routine-proposals/{second.id}/decline", headers=O)

        assert approved.status_code == 200 and approved.json()["state"] == "approved"
        assert declined.json()["state"] == "declined"
        routines = (await client.get(f"/api/bots/{bot.id}/routines")).json()["routines"]
        assert [(r["name"], r["created_by"], r["tainted"]) for r in routines] == [("Morning news", "bot", True)]
        assert (await client.get("/api/routine-proposals")).json() == {"proposals": []}


async def test_approving_twice_is_409(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Scout")
    proposal = await _proposal(app, alice, bot)
    async with signed_in(app, "alice") as client:
        assert (await client.post(f"/api/routine-proposals/{proposal.id}/approve", headers=O)).status_code == 200
        again = await client.post(f"/api/routine-proposals/{proposal.id}/approve", headers=O)
        assert again.status_code == 409 and "Try again" in again.json()["detail"]
        assert len((await client.get(f"/api/bots/{bot.id}/routines")).json()["routines"]) == 1


async def test_another_users_proposal_is_404(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    await register_user(cfg, "bob", PASSWORD)
    proposal = await _proposal(app, alice, await make_bot(cfg, alice.id, "Scout"))
    async with signed_in(app, "bob") as client:
        assert (await client.get("/api/routine-proposals")).json() == {"proposals": []}
        assert (await client.post(f"/api/routine-proposals/{proposal.id}/approve", headers=O)).status_code == 404
        assert (await client.post(f"/api/routine-proposals/{proposal.id}/decline", headers=O)).status_code == 404
    async with signed_in(app, "alice") as client:
        assert len((await client.get("/api/routine-proposals")).json()["proposals"]) == 1


async def test_every_write_needs_the_origin(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    proposal = await _proposal(app, alice, await make_bot(cfg, alice.id, "Scout"))
    async with signed_in(app, "alice") as client:
        bad = {"Origin": "http://evil.example"}
        assert (await client.post(f"/api/routine-proposals/{proposal.id}/approve", headers=bad)).status_code == 403
        assert (await client.post(f"/api/routine-proposals/{proposal.id}/decline", headers=bad)).status_code == 403
        assert len((await client.get("/api/routine-proposals")).json()["proposals"]) == 1


async def test_an_approval_that_cannot_apply_stays_open(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Scout")
    thread, _ = await app.state.talk.ensure_main_thread(alice.id, bot.id)
    payload = ProposalPayload(name="Ghost", instructions="x", schedule=parse_schedule(TIMES))
    stale = await app.state.proposals.propose(alice.id, bot.id, "create", payload, routine_id=None,
                                              thread_id=thread.id, tainted=False, from_routine=False)
    import roost.routines.service as service
    service_cap, service.ROUTINES_PER_BOT_MAX = service.ROUTINES_PER_BOT_MAX, 0
    try:
        async with signed_in(app, "alice") as client:
            refused = await client.post(f"/api/routine-proposals/{stale.id}/approve", headers=O)
    finally:
        service.ROUTINES_PER_BOT_MAX = service_cap
    assert refused.status_code == 422
    async with signed_in(app, "alice") as client:
        assert (await client.get("/api/routine-proposals")).json()["proposals"][0]["state"] == "open"
