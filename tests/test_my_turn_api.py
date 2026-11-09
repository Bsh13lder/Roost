"""``GET /api/my-turn`` (mobile SERVER_NEEDS M4): everything waiting on you in one answer, so phone and web agree.

The same five sources the web's My turn reads (open Stuck cards, routine proposals, skill proposals, Add a key
requests and the question book), each list in its own route's shape, plus ``rows``: the lines My turn draws, in
the web's order (routine proposals, skill proposals, keys, questions, then Stuck cards newest first), with the
web's words. Only bots still on the team, and only the signed-in user's items."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace

import httpx
import pytest

from roost.config import load_config
from roost.connectors.requests import NewRequest
from roost.db.connection import init_db
from roost.desk.stuck import Block, host_of_url
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.my_turn import stuck_line
from roost.routines.models import ProposalPayload
from roost.routines.schedule import parse_schedule
from roost.skills.models import SkillProposalPayload
from roost.skills.proposals import ProposalRequest
from roost.stuck.models import CardDraft
from roost.stuck.store import StuckStore
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}
PASSWORD = "pw-123456"
TIMES = {"kind": "times", "days": [1, 2, 3], "times": ["10:07"]}
LISTS = ("stuck", "routine_proposals", "skill_proposals", "key_requests", "questions")
ROW_FIELDS = {"kind", "id", "bot_id", "thread_id", "panel", "text", "created_at"}


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


async def _stuck(cfg, app, user_id, bot_id, url):
    thread, _ = await app.state.talk.ensure_main_thread(user_id, bot_id)
    block = Block(reason="challenge", url=url, host=host_of_url(url), note="")
    return await StuckStore(cfg).open(user_id, CardDraft(
        bot_id=bot_id, thread_id=thread.id, work_item_id=None, block=block, request="Find it", tainted=False))


async def _everything(cfg, app, user_id, bot_id):
    """One of each kind for ``bot_id``."""
    state = app.state
    thread, _ = await state.talk.ensure_main_thread(user_id, bot_id)
    payload = ProposalPayload(name="Morning news", instructions="Read it.", schedule=parse_schedule(TIMES))
    await state.proposals.propose(user_id, bot_id, "create", payload, routine_id=None, thread_id=thread.id,
                                  tainted=False, from_routine=False)
    await state.skill_proposals.propose(ProposalRequest(
        user_id=user_id, bot_id=bot_id, action="create", thread_id=thread.id, tainted=False, from_routine=False,
        payload=SkillProposalPayload(name="Post on X", use_when="posting on X", body="1. Open X"), skill=None))
    await state.connector_requests.store.create(NewRequest(
        user_id=user_id, bot_id=bot_id, thread_id=thread.id, service="Weather", base_url="https://api.weather.example",
        why="To read the forecast", auth_style="bearer", auth_name="Authorization", tainted=False))
    await state.questions.note(user_id, bot_id, thread.id, "Daily or weekly?", "weekly", None,
                               routine_id=None, tainted=False)
    await _stuck(cfg, app, user_id, bot_id, "https://shop.example/kettle")


async def test_one_answer_holds_every_list_and_the_rows_in_the_webs_order_and_words(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    scout = await make_bot(cfg, alice.id, "Scout")
    await _everything(cfg, app, alice.id, scout.id)
    async with signed_in(app, "alice") as client:
        mine = (await client.get("/api/my-turn")).json()
        assert mine["stuck"] == (await client.get("/api/stuck")).json()
        assert mine["routine_proposals"] == (await client.get("/api/routine-proposals")).json()["proposals"]
        assert mine["skill_proposals"] == (await client.get("/api/skill-proposals")).json()
        assert mine["key_requests"] == (await client.get("/api/connector-requests")).json()
        assert mine["questions"] == (await client.get("/api/questions")).json()["questions"]

    assert all(set(row) == ROW_FIELDS for row in mine["rows"])
    assert [(row["kind"], row["text"], row["panel"]) for row in mine["rows"]] == [
        ("routine_proposal", "Scout · New routine · Morning news", None),
        ("skill_proposal", "Scout · New skill · Post on X", None),
        ("key_request", "Scout · Add a key · Weather", None),
        ("question", "Scout · Daily or weekly?", "info"),
        ("stuck", "Scout · Stuck on shop.example", None),
    ]
    assert mine["count"] == 5
    assert mine["rows"][-1]["thread_id"] == mine["stuck"][0]["thread_id"]


async def test_a_sign_in_card_and_a_card_with_no_address_read_like_the_web(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    scout, pip = await make_bot(cfg, alice.id, "Scout"), await make_bot(cfg, alice.id, "Pip")
    await _stuck(cfg, app, alice.id, scout.id, "about:blank")
    card = await _stuck(cfg, app, alice.id, pip.id, "https://mail.example/login")
    async with signed_in(app, "alice") as client:
        rows = (await client.get("/api/my-turn")).json()["rows"]
    assert {row["text"] for row in rows} == {"Scout · Needs your help", "Pip · Stuck on mail.example"}
    assert stuck_line("Pip", replace(card, sign_in=True)) == "Pip needs you to sign in to mail.example"
    assert stuck_line("Pip", replace(card, sign_in=True, url="about:blank")) == "Pip · Needs your help"


async def test_another_users_items_never_show_and_an_empty_turn_is_empty(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    await register_user(cfg, "bob", PASSWORD)
    await _everything(cfg, app, alice.id, (await make_bot(cfg, alice.id, "Scout")).id)
    async with signed_in(app, "bob") as client:
        answer = (await client.get("/api/my-turn")).json()
    assert answer == {**{name: [] for name in LISTS}, "rows": [], "count": 0}


async def test_needs_a_login(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        assert (await client.get("/api/my-turn")).status_code == 401
