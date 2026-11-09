"""A routine run's gate reads the routine's live standing permissions (Step 2): ``RoutineHooks.standing_for`` builds
the frozen ``StandingState`` (routine id, its instructions, live permissions with today's count left), and the
runner puts it in the run's ``ApprovalState``. Any other run, or a routine with none, carries no standing state."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from roost.approvals.sessions import SessionOks
from roost.approvals.store import ApprovalStore
from roost.approvals.wiring import ApprovalWiring
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import DeskFactory
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.scripted import ScriptedModel
from roost.routines.hooks import RoutineHooks
from roost.routines.models import RoutineDraft
from roost.routines.runs import RoutineRunStore
from roost.routines.schedule import parse_schedule
from roost.routines.store import RoutineStore
from roost.standing.models import PermissionIn
from roost.standing.store import PermissionStore
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from roost.talk.turn import RunInputs
from roost.work.models import ORIGIN_YOU, WorkItem, WorkKind, WorkState
from roost.work.runs import madrid_today
from team_helpers import make_bot

NOW = datetime(2026, 10, 23, 8, 0, tzinfo=timezone.utc)
INSTRUCTIONS = "Post the weekly update on x.com."


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


def _item(item_id: str, bot_id: str, thread_id: str, kind: WorkKind = WorkKind.ROUTINE) -> WorkItem:
    return WorkItem(id=item_id, user_id="u", bot_id=bot_id, thread_id=thread_id, kind=kind, origin=ORIGIN_YOU,
                    body="Run it", tainted=False, depth=0, parent_item_id=None, message_id=None,
                    state=WorkState.CLAIMED, run_id=None, inflight=None, result=None, result_tainted=False,
                    created_at=NOW.isoformat(), updated_at=NOW.isoformat())


async def _rig(cfg, *, with_permission: bool = True):
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Poster")
    talk = TalkStore(cfg)
    routines = RoutineStore(cfg, talk)
    routine = await routines.create(user.id, RoutineDraft(
        bot_id=bot.id, name="Weekly post", instructions=INSTRUCTIONS,
        schedule=parse_schedule({"kind": "times", "days": [5], "times": ["10:00"]}), created_by="user"))
    runs = RoutineRunStore(cfg)
    item_id = str(uuid4())
    await runs.record(user.id, routine, NOW, "running", work_item_id=item_id)
    permissions = PermissionStore(cfg)
    if with_permission:
        await permissions.create(user.id, routine.id, PermissionIn(
            host="x.com", action="post", max_per_day=2, until=date(2026, 11, 1)))
    hooks = RoutineHooks(talk, EventHub(cfg), runs, routines, clock=lambda: NOW, permissions=permissions)
    return user.id, bot, routine, hooks, _item(item_id, bot.id, routine.thread_id)


async def test_a_routine_run_gets_its_live_permissions(cfg):
    user_id, _, routine, hooks, item = await _rig(cfg)
    state = await hooks.standing_for(user_id, (item,))
    assert state is not None and state.routine_id == routine.id and state.instructions == INSTRUCTIONS
    assert state.today == madrid_today(NOW)
    assert [(p.host, p.action, p.remaining) for p in state.permissions] == [("x.com", "post", 2)]


async def test_other_runs_and_routines_without_permissions_get_none(cfg):
    user_id, bot, routine, hooks, item = await _rig(cfg, with_permission=False)
    assert await hooks.standing_for(user_id, (item,)) is None
    chat = replace(item, kind=WorkKind.MESSAGE)
    assert await hooks.standing_for(user_id, (chat,)) is None
    assert await hooks.standing_for(user_id, ()) is None
    unknown = replace(item, id=str(uuid4()))
    assert await hooks.standing_for(user_id, (unknown,)) is None


async def test_without_a_permission_store_nothing_is_read(cfg):
    user_id, _, routine, hooks, item = await _rig(cfg)
    bare = RoutineHooks(TalkStore(cfg), EventHub(cfg), RoutineRunStore(cfg), RoutineStore(cfg, TalkStore(cfg)))
    assert await bare.standing_for(user_id, (item,)) is None


async def test_the_runner_puts_it_in_the_runs_approval_state(cfg):
    user_id, bot, routine, hooks, item = await _rig(cfg)
    runner = TurnRunner(cfg, BotStore(cfg), TalkStore(cfg), EventHub(cfg), DeskFactory(cfg), ScriptedModel(),
                        ActivityBoard(), approvals=ApprovalWiring(ApprovalStore(cfg), SessionOks()), routines=hooks)
    inputs = await runner._with_approval(user_id, bot, RunInputs(items=(item,)))
    assert inputs.approval is not None and inputs.approval.standing is not None
    assert inputs.approval.standing.routine_id == routine.id
    chat = await runner._with_approval(user_id, bot, RunInputs(items=(replace(item, kind=WorkKind.MESSAGE),)))
    assert chat.approval is not None and chat.approval.standing is None
