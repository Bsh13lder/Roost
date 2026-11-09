"""Full auto, wired through (owner, 2026-10-25): schema v36 ``bots.auto_review``, the approval route and the bot's
wire shape, the run's approval state (your own chat only), and the computer-use runner's review source and the
"(auto-checked)" step line. No real model: the scripted worker."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from roost.approvals.models import ApprovalState, BotApproval
from roost.approvals.sessions import SessionOks
from roost.approvals.store import ApprovalStore
from roost.approvals.wiring import ApprovalWiring
from roost.auto_review.constants import AUTO_REVIEW_MARK
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.db.migrations import MIGRATIONS
from roost.desk import DeskFactory
from roost.desk.fake_cu import FakeScreenState, fake_target, script
from roost.events.hub import EventHub
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.llm.scripted import ScriptedModel
from roost.rooms.models import RoomContext
from roost.talk.gate import GateContext
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from roost.talk.tool_catalog import CATALOG
from roost.talk.turn import RunInputs
from roost.work.models import ORIGIN_YOU, WorkItem, WorkKind, WorkState
from cu_run_helpers import make_cu_rig, step
from team_helpers import make_bot

ORIGIN = {"Origin": "http://127.0.0.1:18800"}
AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}
NOW = datetime(2026, 10, 25, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


# -- the column, the store and the route ----------------------------------------------------------------------

def test_the_migration_is_v36_and_adds_one_column_off_by_default():
    migration = next(m for m in MIGRATIONS if m.version == 36)
    assert migration.name == "auto review"
    [step_] = migration.steps
    assert (step_.table, step_.column, step_.definition) == ("bots", "auto_review", "INTEGER NOT NULL DEFAULT 0")


async def test_the_store_keeps_it_unless_told_and_never_for_another_user(cfg):
    alice = (await register_user(cfg, "alice", "pw-123456")).id
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bot = await make_bot(cfg, alice, "Shopper")
    store = BotStore(cfg)
    assert bot.approval.auto_review is False
    on = await store.set_approval(alice, bot.id, BotApproval("ask", frozenset()), auto_review=True)
    assert on is not None and on.approval.auto_review is True
    kept = await store.set_approval(alice, bot.id, BotApproval("auto_edit", frozenset({"browsing"})))
    assert kept is not None and kept.approval == BotApproval("auto_edit", frozenset({"browsing"}), auto_review=True)
    assert await store.set_approval(bob, bot.id, BotApproval("ask", frozenset()), auto_review=False) is None
    assert (await store.get(alice, bot.id)).approval.auto_review is True


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=ORIGIN).status_code == 201
    return c


def test_the_route_sets_and_keeps_auto_review_and_validates_it():
    c = _client()
    bot = c.post("/api/bots", json={"name": "Scout", "job": "j", "instructions": "i", "avatar": AVATAR},
                 headers=ORIGIN).json()
    assert bot["approval"]["auto_review"] is True                     # on for a new bot (owner, 2026-11-03)
    url = f"/api/bots/{bot['id']}/approval"
    r = c.put(url, json={"mode": "ask", "ask_topics": [], "auto_review": False}, headers=ORIGIN)
    assert r.status_code == 200 and r.json()["approval"]["auto_review"] is False
    r = c.put(url, json={"mode": "ask", "ask_topics": ["files"]}, headers=ORIGIN)
    assert r.json()["approval"]["auto_review"] is False                # left out: kept
    assert c.put(url, json={"mode": "ask", "auto_review": "yes"}, headers=ORIGIN).status_code == 422
    assert c.put(url, json={"mode": "ask", "auto_review": 1}, headers=ORIGIN).status_code == 422
    assert c.put("/api/bots/not-a-bot/approval", json={"mode": "ask", "auto_review": True},
                 headers=ORIGIN).status_code == 404


# -- the run's approval state ---------------------------------------------------------------------------------

def _item(bot_id: str, kind: WorkKind) -> WorkItem:
    return WorkItem(id="i1", user_id="u", bot_id=bot_id, thread_id="t1", kind=kind, origin=ORIGIN_YOU,
                    body="go", tainted=False, depth=0, parent_item_id=None, message_id=None,
                    state=WorkState.CLAIMED, run_id=None, inflight=None, result=None, result_tainted=False,
                    created_at=NOW.isoformat(), updated_at=NOW.isoformat())


async def test_only_your_own_chat_runs_carry_auto_review(cfg):
    user_id = (await register_user(cfg, "alice", "pw-123456")).id
    bot = await make_bot(cfg, user_id, "Shopper")
    bot = await BotStore(cfg).set_approval(user_id, bot.id, BotApproval("ask", frozenset()), auto_review=True)
    runner = TurnRunner(cfg, BotStore(cfg), TalkStore(cfg), EventHub(cfg), DeskFactory(cfg), ScriptedModel(),
                        ActivityBoard(), approvals=ApprovalWiring(ApprovalStore(cfg), SessionOks()))

    async def state(kind: WorkKind, room: RoomContext | None = None) -> ApprovalState:
        inputs = await runner._with_approval(user_id, bot, RunInputs(items=(_item(bot.id, kind),), room=room))
        assert inputs.approval is not None
        return inputs.approval

    assert (await state(WorkKind.MESSAGE)).auto_review is True
    assert (await state(WorkKind.CARD_ANSWER)).auto_review is True
    assert (await state(WorkKind.ROUTINE)).auto_review is False
    assert (await state(WorkKind.HANDOFF)).auto_review is False
    assert (await state(WorkKind.MESSAGE, RoomContext("r1", "Room", (), None))).auto_review is False
    off = replace(bot, approval=BotApproval("ask", frozenset()))
    inputs = await runner._with_approval(user_id, off, RunInputs(items=(_item(bot.id, WorkKind.MESSAGE),)))
    assert inputs.approval is not None and inputs.approval.auto_review is False


# -- the computer-use runner ----------------------------------------------------------------------------------

_PANEL = (fake_target("button", "Frobnicate", 450, 200, tag="button"),
          fake_target("button", "Zorblat", 450, 300, tag="button"))
_SCRIPT = script([
    ("home", FakeScreenState(url="https://shop.example/", title="Shop", targets=_PANEL, text="Panel",
                             on_click={"Frobnicate": "open", "Zorblat": "open"})),
    ("open", FakeScreenState(url="https://shop.example/panel", title="Panel", text="It says hello")),
])


def _full_auto(*, auto_review: bool = True, cards: bool = True) -> GateContext:
    state = ApprovalState("ask", frozenset(), cards, auto_review=auto_review)
    return GateContext(allowed=frozenset(CATALOG), tainted=True, approval=state)


async def _rig(cfg):
    rig = await make_cu_rig(cfg, "On shop.example open the frobnicate panel and tell me what it says")
    rig.page = rig.desk.serve_screen(_SCRIPT)
    return rig


async def test_a_button_the_reviewer_calls_safe_is_clicked_and_the_line_says_auto_checked(cfg):
    rig = await _rig(cfg)
    cu = rig.computer()
    await step(cu, "look", _full_auto())
    done = await step(cu, "click", _full_auto(), target={"text": "Frobnicate"}, expect="the panel opens")
    assert done.parked is None and rig.page.state_name == "open"
    assert f"Clicked 'Frobnicate' {AUTO_REVIEW_MARK}" in rig.lines


async def test_a_button_the_reviewer_does_not_call_safe_parks_on_the_usual_card(cfg):
    rig = await _rig(cfg)
    cu = rig.computer()
    await step(cu, "look", _full_auto())
    asked = await step(cu, "click", _full_auto(), target={"text": "Zorblat"}, expect="something")
    assert asked.parked is not None and asked.parked.floor == "commit_click" and rig.page.state_name == "home"
    assert not any(AUTO_REVIEW_MARK in line for line in rig.lines)


async def test_without_full_auto_the_same_button_asks(cfg):
    rig = await _rig(cfg)
    cu = rig.computer()
    await step(cu, "look", _full_auto(auto_review=False))
    asked = await step(cu, "click", _full_auto(auto_review=False), target={"text": "Frobnicate"}, expect="opens")
    assert asked.parked is not None and rig.page.state_name == "home"
