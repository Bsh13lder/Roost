"""Bots manage routines directly (the owner, 2026-10-21: "If I ask, I ask. If I don't, I don't."): in a clean run
the user's own message started, ``create_routine`` and its kin write at once, under the bot's approval mode. A
tainted run, a routine's own run, a handoff or a room is refused with a short reason and uses the propose tools."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from plan_helpers import call, mode_rig, step
from roost.approvals import topics
from roost.approvals.models import ApprovalState, CardState
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.routines.direct_tools import (
    NOT_HERE_TEXT, TAINTED_TEXT, RoutineWrites,
)
from roost.routines.models import RoutineDraft
from roost.routines.runs import RoutineRunStore
from roost.routines.schedule import parse_schedule
from roost.routines.service import RoutineService
from roost.routines.store import DAY_SUMMARY_BUILTIN, DAY_SUMMARY_NAME, RoutineStore
from roost.routines.tool_specs import DIRECT_ROUTINE_NAMES
from roost.talk.domain_tools import RecordContext
from roost.talk.gate import GateContext, judge
from roost.talk.store import TalkStore
from roost.talk.tool_catalog import CATALOG
from team_helpers import make_bot, say, send, wait_idle

NOW = datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc)      # 10:00 in Madrid
DAILY = {"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["09:00"]}
MONDAYS = {"kind": "times", "days": [1], "times": ["08:30"]}
BRIEF = {"name": "Morning brief", "instructions": "Tell me the news.", "schedule": DAILY}


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture
async def bot(cfg, user_id):
    return await make_bot(cfg, user_id, "Scout")


class Rig:
    def __init__(self, cfg):
        self.talk, self.events, self.bots = TalkStore(cfg), EventHub(cfg), BotStore(cfg)
        self.routines = RoutineStore(cfg, self.talk, clock=lambda: NOW)
        self.service = RoutineService(self.routines, RoutineRunStore(cfg), self.bots, self.talk, self.events,
                                      None, None, clock=lambda: NOW)
        self.tools = RoutineWrites(self.routines, self.service)

    async def run(self, name, arguments, user_id, bot, *, tainted=False, from_routine=False, user_started=True):
        thread, _ = await self.talk.ensure_main_thread(user_id, bot.id)
        ctx = RecordContext(user_id=user_id, bot_id=bot.id, tainted=tainted, thread_id=thread.id,
                            from_routine=from_routine, user_started=user_started)
        return await self.tools.run(name, arguments, ctx)

    async def existing(self, user_id, bot, name="Morning news", **kw):
        return await self.routines.create(user_id, RoutineDraft(
            bot_id=bot.id, name=name, instructions="Read the news.", schedule=parse_schedule(DAILY),
            created_by="user", **kw))

    async def notes(self, user_id, bot):
        thread, _ = await self.talk.ensure_main_thread(user_id, bot.id)
        return [json.loads(m.body)["text"] for m in await self.talk.list_messages(user_id, thread.id)
                if m.kind == "routine_note"]


@pytest.fixture
def rig(cfg):
    return Rig(cfg)


# ---- the catalog and the gate -------------------------------------------------------------------------------

def test_the_direct_tools_carry_the_normal_gate_kinds():
    assert DIRECT_ROUTINE_NAMES == {"create_routine", "update_routine", "pause_routine", "resume_routine",
                                    "delete_routine"}
    assert CATALOG["create_routine"].kind == "write_create"
    for name in ("update_routine", "pause_routine", "resume_routine", "delete_routine"):
        assert CATALOG[name].kind == "write_change"
    for name in DIRECT_ROUTINE_NAMES:
        tool = CATALOG[name]
        assert not tool.no_ask and not tool.allowed_when_tainted and tool.refused_when_tainted
        assert topics.topic_of(name) == "routines"
    assert CATALOG["delete_task"].kind == CATALOG["delete_routine"].kind   # the strictest delete kind there is


@pytest.mark.parametrize(("mode", "decision"), [("ask", "ask"), ("auto_edit", "do"), ("plan", "plan")])
def test_the_approval_mode_decides(mode, decision):
    ctx = GateContext(allowed=frozenset(CATALOG), approval=ApprovalState(mode, frozenset(), True))
    for name in DIRECT_ROUTINE_NAMES:
        assert judge(CATALOG[name], name, {}, ctx).decision == decision


def test_the_routines_topic_switch_asks_in_auto_edit():
    ctx = GateContext(allowed=frozenset(CATALOG),
                      approval=ApprovalState("auto_edit", frozenset({"routines"}), True))
    assert judge(CATALOG["delete_routine"], "delete_routine", {}, ctx).decision == "ask"


@pytest.mark.parametrize("name", sorted(DIRECT_ROUTINE_NAMES))
def test_a_tainted_run_is_refused_by_the_gate_with_the_propose_way(name):
    ctx = GateContext(allowed=frozenset(CATALOG), tainted=True,
                      approval=ApprovalState("auto_edit", frozenset(), True))
    verdict = judge(CATALOG[name], name, {}, ctx)
    assert verdict.decision == "never" and verdict.text == TAINTED_TEXT
    assert "propose_routine" in TAINTED_TEXT


# ---- the handler ----------------------------------------------------------------------------------------------

async def test_create_writes_the_routine_and_leaves_an_activity_line(rig, user_id, bot):
    outcome = await rig.run("create_routine", BRIEF, user_id, bot)

    [routine] = await rig.routines.list_for_bot(user_id, bot.id)
    assert routine.name == "Morning brief" and routine.enabled and routine.created_by == "bot"
    assert routine.tainted is False and routine.next_run_at is not None
    assert outcome.created and not outcome.failed
    assert outcome.text.startswith("Created routine “Morning brief”") and "Madrid" in outcome.text
    assert await rig.notes(user_id, bot) == ["Created routine · Morning brief"]


async def test_update_pause_resume_and_delete(rig, user_id, bot):
    routine = await rig.existing(user_id, bot)

    changed = await rig.run("update_routine", {"routine_id": routine.id, "name": "Weekly news",
                                                "schedule": MONDAYS}, user_id, bot)
    after = await rig.routines.get(user_id, routine.id)
    assert changed.text.startswith("Changed routine “Weekly news”")
    assert after.name == "Weekly news" and after.schedule.days == (1,) and after.instructions == "Read the news."

    paused = await rig.run("pause_routine", {"routine_id": routine.id}, user_id, bot)
    assert paused.text == "Paused routine “Weekly news”." and not (await rig.routines.get(user_id, routine.id)).enabled
    resumed = await rig.run("resume_routine", {"routine_id": routine.id}, user_id, bot)
    assert resumed.text == "Resumed routine “Weekly news”." and (await rig.routines.get(user_id, routine.id)).enabled

    deleted = await rig.run("delete_routine", {"routine_id": routine.id}, user_id, bot)
    assert deleted.text == "Deleted routine “Weekly news”." and await rig.routines.get(user_id, routine.id) is None
    assert await rig.notes(user_id, bot) == [
        "Updated routine · Weekly news", "Paused routine · Weekly news", "Resumed routine · Weekly news",
        "Deleted routine · Weekly news"]


async def test_the_old_day_summary_is_deleted_like_any_routine(rig, user_id, bot):
    summary = await rig.existing(user_id, bot, DAY_SUMMARY_NAME, builtin=DAY_SUMMARY_BUILTIN, enabled=False)

    outcome = await rig.run("delete_routine", {"routine_id": summary.id}, user_id, bot)

    assert outcome.text == "Deleted routine “End-of-day summary”."
    assert await rig.routines.get(user_id, summary.id) is None
    assert await rig.notes(user_id, bot) == ["Deleted routine · End-of-day summary"]


@pytest.mark.parametrize("ctx", [{"user_started": False}, {"from_routine": True, "user_started": False},
                                 {"from_routine": True}])
async def test_a_handoff_room_or_routine_run_is_refused(rig, user_id, bot, ctx):
    routine = await rig.existing(user_id, bot)
    for name, args in (("create_routine", BRIEF), ("delete_routine", {"routine_id": routine.id}),
                       ("pause_routine", {"routine_id": routine.id})):
        outcome = await rig.run(name, args, user_id, bot, **ctx)
        assert outcome.text == NOT_HERE_TEXT and outcome.failed
    assert "propose_routine" in NOT_HERE_TEXT
    assert [r.id for r in await rig.routines.list_for_bot(user_id, bot.id)] == [routine.id]
    assert (await rig.routines.get(user_id, routine.id)).enabled


async def test_a_tainted_run_is_refused_by_the_handler_too(rig, user_id, bot):
    outcome = await rig.run("create_routine", BRIEF, user_id, bot, tainted=True)
    assert outcome.text == TAINTED_TEXT and await rig.routines.list_for_bot(user_id, bot.id) == ()


async def test_another_bots_or_users_routine_is_not_found(rig, cfg, user_id, bot):
    other_bot = await make_bot(cfg, user_id, "Pip")
    theirs = await rig.existing(user_id, other_bot)
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bobs = await rig.existing(bob, await make_bot(cfg, bob, "Bobby"))

    for routine in (theirs, bobs):
        for name in ("update_routine", "pause_routine", "resume_routine", "delete_routine"):
            args = {"routine_id": routine.id, **({"name": "x"} if name == "update_routine" else {})}
            outcome = await rig.run(name, args, user_id, bot)
            assert outcome.text == "Refused: that isn't one of your routines." and outcome.failed
    assert await rig.routines.get(user_id, theirs.id) is not None
    assert await rig.routines.get(bob, bobs.id) is not None


async def test_validation_matches_the_proposal_path(rig, user_id, bot, monkeypatch):
    too_often = {**BRIEF, "schedule": {"kind": "cron", "expr": "*/5 * * * *"}}
    assert (await rig.run("create_routine", too_often, user_id, bot)).text.startswith("Refused:")
    assert (await rig.run("create_routine", {"name": "", "instructions": "x", "schedule": DAILY},
                          user_id, bot)).text.startswith("Refused:")
    assert (await rig.run("create_routine", {**BRIEF, "schedule": {"kind": "times", "days": [1], "times": ["25:00"]}},
                          user_id, bot)).text.startswith("Refused:")
    routine = await rig.existing(user_id, bot)
    assert (await rig.run("update_routine", {"routine_id": routine.id}, user_id, bot)).text.startswith("Refused:")
    import roost.routines.service as service_module
    monkeypatch.setattr(service_module, "ROUTINES_PER_BOT_MAX", 1)
    capped = await rig.run("create_routine", BRIEF, user_id, bot)
    assert capped.text == "Refused: This bot already has 1 routines." and capped.failed
    assert len(await rig.routines.list_for_bot(user_id, bot.id)) == 1


async def test_a_card_step_names_the_routine_and_runs_after_yes(rig, user_id, bot):
    routine = await rig.existing(user_id, bot)
    thread, _ = await rig.talk.ensure_main_thread(user_id, bot.id)
    ctx = RecordContext(user_id=user_id, bot_id=bot.id, tainted=False, thread_id=thread.id, user_started=True)

    pending = await rig.tools.prepare("delete_routine", {"routine_id": routine.id}, ctx)

    assert pending.title == "Delete routine “Morning news”" and pending.topic == "routines"
    after_yes = RecordContext(user_id=user_id, bot_id=bot.id, tainted=False, thread_id=thread.id)
    outcome = await rig.tools.execute("delete_routine", dict(pending.arguments), after_yes)
    assert not outcome.failed and await rig.routines.get(user_id, routine.id) is None


async def test_a_card_from_a_handoff_is_never_made(rig, user_id, bot):
    ctx = RecordContext(user_id=user_id, bot_id=bot.id, tainted=False, thread_id=None)
    assert await rig.tools.prepare("create_routine", BRIEF, ctx) == NOT_HERE_TEXT


# ---- through a real run ---------------------------------------------------------------------------------------

async def _chat(cfg, user_id, bot, mode, script):
    rig, thread = await mode_rig(cfg, user_id, bot, mode, script)
    await send(rig, user_id, bot.id, thread.id, "Every day at 9, tell me the news")
    await wait_idle(rig.runner)
    return rig


async def _routines(cfg, user_id, bot):
    return await RoutineStore(cfg, TalkStore(cfg)).list_for_bot(user_id, bot.id)


async def test_auto_edit_creates_it_in_the_users_own_chat(cfg, user_id, bot):
    await _chat(cfg, user_id, bot, "auto_edit", [step(call("create_routine", "c1", **BRIEF)), say("Done.")])
    [routine] = await _routines(cfg, user_id, bot)
    assert routine.name == "Morning brief"


async def test_ask_every_time_asks_on_a_card_and_yes_creates_it(cfg, user_id, bot):
    rig = await _chat(cfg, user_id, bot, "ask", [step(call("create_routine", "c1", **BRIEF)), say("Asked."),
                                                say("Done.")])
    [card] = await rig.store.list_open(user_id)
    assert [s.tool for s in card.steps] == ["create_routine"] and await _routines(cfg, user_id, bot) == ()

    answered = await rig.service.answer(user_id, card.id, "yes")
    await wait_idle(rig.runner)

    assert answered.state is CardState.APPROVED
    assert [r.name for r in await _routines(cfg, user_id, bot)] == ["Morning brief"]


async def test_review_first_collects_it_into_a_proposal(cfg, user_id, bot):
    rig = await _chat(cfg, user_id, bot, "plan", [step(call("create_routine", "c1", **BRIEF)), say("Planned."),
                                                 say("Done.")])
    [card] = await rig.store.list_open(user_id)
    assert card.kind == "plan" and [s.tool for s in card.steps] == ["create_routine"]

    await rig.service.answer(user_id, card.id, "accept")
    await wait_idle(rig.runner)

    assert [r.name for r in await _routines(cfg, user_id, bot)] == ["Morning brief"]


def test_only_a_one_to_one_run_of_your_own_messages_may_write_routines():
    from roost.talk.turn import RunInputs, _user_chat
    from roost.work.models import WorkItem, WorkKind, WorkState

    def item(kind):
        return WorkItem(id="i", user_id="u", bot_id="b", thread_id="t", kind=kind, origin="o", body="",
                        tainted=False, depth=0, parent_item_id=None, message_id=None, state=WorkState.CLAIMED,
                        run_id="r", inflight=None, result=None, result_tainted=False, created_at="", updated_at="")

    assert _user_chat(RunInputs(items=(item(WorkKind.MESSAGE),))) is True
    assert _user_chat(RunInputs(items=(item(WorkKind.MESSAGE),), room=object())) is False
    for kind in (WorkKind.HANDOFF, WorkKind.ROUTINE):
        assert _user_chat(RunInputs(items=(item(WorkKind.MESSAGE), item(kind)))) is False
    assert _user_chat(RunInputs()) is False
