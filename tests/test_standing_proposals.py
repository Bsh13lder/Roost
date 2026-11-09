"""A bot may propose a standing permission with ``propose_routine``; it is stored only on the owner's Approve, which
may keep it, change it or leave it out (Step 2). A bad permission is refused at proposal time and at Approve."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.routines.models import ProposalPayload
from roost.routines.schedule import parse_schedule
from roost.routines.tools import RoutineTools
from roost.standing.models import PermissionIn
from roost.talk.domain_tools import RecordContext
from roost.work.runs import madrid_today
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}
PASSWORD = "pw-123456"
TIMES = {"kind": "times", "days": [1], "times": ["10:07"]}


def _today() -> date:
    return date.fromisoformat(madrid_today(datetime.now(timezone.utc)))


def _perm(**kw) -> dict:
    return {"host": "x.com", "action": "post", "max_per_day": 1, "until": (_today() + timedelta(days=10)).isoformat(),
            **kw}


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


async def _proposal(app, user, bot, permission: dict | None = _perm()):
    thread, _ = await app.state.talk.ensure_main_thread(user.id, bot.id)
    payload = ProposalPayload(name="Weekly post", instructions="Post the update on x.com.",
                              schedule=parse_schedule(TIMES),
                              permission=PermissionIn(**permission) if permission else None)
    return await app.state.proposals.propose(user.id, bot.id, "create", payload, routine_id=None,
                                             thread_id=thread.id, tainted=True, from_routine=False)


async def _routine_permissions(client, bot) -> list[dict]:
    routines = (await client.get(f"/api/bots/{bot.id}/routines")).json()["routines"]
    assert len(routines) == 1
    return (await client.get(f"/api/routines/{routines[0]['id']}/permissions")).json()["permissions"]


async def test_the_card_shows_it_and_approve_stores_it(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Poster")
    proposal = await _proposal(app, alice, bot)
    async with signed_in(app, "alice") as client:
        shown = (await client.get(f"/api/routine-proposals/{proposal.id}")).json()
        assert shown["payload"]["permission"] == _perm()
        assert (await client.post(f"/api/routine-proposals/{proposal.id}/approve", headers=O)).status_code == 200
        stored = await _routine_permissions(client, bot)
        assert [(p["host"], p["action"], p["max_per_day"]) for p in stored] == [("x.com", "post", 1)]


async def test_the_owner_may_change_or_leave_it_out_on_approve(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Poster")
    other = await make_bot(cfg, alice.id, "Writer")
    changed, dropped = await _proposal(app, alice, bot), await _proposal(app, alice, other)
    async with signed_in(app, "alice") as client:
        response = await client.post(f"/api/routine-proposals/{changed.id}/approve", headers=O,
                                     json={"permission": _perm(max_per_day=3, action="send")})
        assert response.status_code == 200, response.text
        assert [(p["action"], p["max_per_day"]) for p in await _routine_permissions(client, bot)] == [("send", 3)]
        response = await client.post(f"/api/routine-proposals/{dropped.id}/approve", headers=O,
                                     json={"permission": None})
        assert response.status_code == 200
        assert await _routine_permissions(client, other) == []


async def test_a_bad_permission_on_approve_is_422_and_writes_nothing(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Poster")
    proposal = await _proposal(app, alice, bot)
    async with signed_in(app, "alice") as client:
        response = await client.post(f"/api/routine-proposals/{proposal.id}/approve", headers=O,
                                     json={"permission": _perm(action="spend")})
        assert (response.status_code, response.json()["detail"]) == (422, "Pick post, send or submit.")
        assert (await client.get(f"/api/bots/{bot.id}/routines")).json()["routines"] == []
        assert (await client.get(f"/api/routine-proposals/{proposal.id}")).json()["state"] == "open"


async def test_a_proposal_without_one_stores_none(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Poster")
    proposal = await _proposal(app, alice, bot, permission=None)
    async with signed_in(app, "alice") as client:
        assert (await client.post(f"/api/routine-proposals/{proposal.id}/approve", headers=O)).status_code == 200
        assert await _routine_permissions(client, bot) == []


async def test_propose_routine_carries_a_permission_and_refuses_a_bad_one(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Poster")
    thread, _ = await app.state.talk.ensure_main_thread(alice.id, bot.id)
    tools = RoutineTools(app.state.routine_store, app.state.proposals)
    ctx = RecordContext(user_id=alice.id, bot_id=bot.id, thread_id=thread.id, tainted=False)
    args = {"name": "Weekly post", "instructions": "Post the update on x.com.", "schedule": TIMES}
    bad = await tools.run("propose_routine", {**args, "permission": _perm(until="2020-01-01")}, ctx)
    assert bad.text == "Refused: Pick an end date from today on."
    good = await tools.run("propose_routine", {**args, "permission": _perm()}, ctx)
    assert good.text.startswith("Asked the user to approve")
    listed = await app.state.proposals.list_open(alice.id)
    assert [v.proposal.payload.permission.host for v in listed] == ["x.com"]
