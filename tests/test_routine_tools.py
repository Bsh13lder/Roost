"""The bot's routine proposal tools (Task 9): none writes a routine; a proposal is a sealed, marked card the user
approves. The direct tools (create_routine and its kin) are in test_routine_direct_tools.py."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.routines.models import RoutineDraft
from roost.routines.proposals import ProposalService, ProposalStore
from roost.routines.runs import RoutineRunStore
from roost.routines.schedule import parse_schedule
from roost.routines.service import RoutineService
from roost.routines.store import RoutineStore
from roost.routines.tool_specs import DIRECT_ROUTINE_NAMES, ROUTINE_TOOL_DEFS
from roost.routines.tools import RoutineTools
from roost.talk.domain_tools import RecordContext
from roost.talk.store import TalkStore
from roost.talk.tool_catalog import CATALOG
from team_helpers import make_bot

NOW = datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc)
TIMES = {"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["10:07"]}
OTHER = {"kind": "times", "days": [1], "times": ["09:00"]}
ROUTINE_NAMES = {"list_routines", "propose_routine", "propose_routine_change", "propose_routine_pause"}
PLAN_NAMES = {"plan_read", "plan_add", "plan_update", "plan_complete"}


class Rig:
    def __init__(self, cfg):
        self.cfg = cfg
        self.talk, self.events, self.bots = TalkStore(cfg), EventHub(cfg), BotStore(cfg)
        self.routines = RoutineStore(cfg, self.talk, clock=lambda: NOW)
        self.service = RoutineService(self.routines, RoutineRunStore(cfg), self.bots, self.talk, self.events,
                                      None, None, clock=lambda: NOW)
        self.proposals = ProposalService(ProposalStore(cfg), self.routines, self.talk, self.events,
                                         writer=self.service, clock=lambda: NOW)
        self.tools = RoutineTools(self.routines, self.proposals)

    async def run(self, name, arguments, user_id, bot, *, tainted=False, from_routine=False, thread=None):
        thread = thread or (await self.talk.ensure_main_thread(user_id, bot.id))[0]
        ctx = RecordContext(user_id=user_id, bot_id=bot.id, tainted=tainted, thread_id=thread.id,
                            from_routine=from_routine)
        return (await self.tools.run(name, arguments, ctx)).text

    async def existing(self, user_id, bot, name="Morning news"):
        return await self.routines.create(user_id, RoutineDraft(
            bot_id=bot.id, name=name, instructions="Read the news.", schedule=parse_schedule(TIMES), created_by="user"))


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


@pytest.fixture
def rig(cfg):
    return Rig(cfg)


def _propose_args(name="Morning news"):
    return {"name": name, "instructions": "Read the headlines.", "schedule": TIMES}


async def _cards(rig, user_id, thread_id):
    return [m for m in await rig.talk.list_messages(user_id, thread_id) if m.kind == "routine_proposal"]


async def test_no_tool_writes_a_routine(rig, user_id, bot):
    existing = await rig.existing(user_id, bot)

    await rig.run("propose_routine", _propose_args("Brand new"), user_id, bot)
    await rig.run("propose_routine_change", {"routine_id": existing.id, "name": "Renamed", "schedule": OTHER}, user_id, bot)

    routines = await rig.routines.list_for_bot(user_id, bot.id)
    assert [(r.name, r.schedule.model_dump()) for r in routines] == [("Morning news", parse_schedule(TIMES).model_dump())]
    assert len(await rig.proposals.list_open(user_id)) == 2


async def test_propose_posts_a_card_and_approve_creates_the_routine(rig, user_id, bot):
    text = await rig.run("propose_routine", _propose_args(), user_id, bot)

    assert text == "Asked the user to approve “Morning news”. It starts only after they say yes."
    thread, _ = await rig.talk.ensure_main_thread(user_id, bot.id)
    [card] = await _cards(rig, user_id, thread.id)
    proposal_id = json.loads(card.body)["proposal_id"]
    [view] = await rig.proposals.list_open(user_id)
    assert view.proposal.id == proposal_id and len(view.next) == 3 and "10:07" in view.words

    await rig.proposals.approve(user_id, proposal_id)

    [routine] = await rig.routines.list_for_bot(user_id, bot.id)
    assert routine.name == "Morning news" and routine.created_by == "bot" and routine.tainted is False
    notes = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "routine_note"]
    assert "Created routine" in json.loads(notes[-1].body)["text"]


async def test_a_change_card_shows_the_diff(rig, user_id, bot):
    existing = await rig.existing(user_id, bot)
    await rig.run("propose_routine_change", {"routine_id": existing.id, "name": "Evening news", "schedule": OTHER},
                  user_id, bot)

    [view] = await rig.proposals.list_open(user_id)

    assert {d["field"] for d in view.diff} == {"name", "schedule"}
    name = next(d for d in view.diff if d["field"] == "name")
    assert (name["before"], name["after"]) == ("Morning news", "Evening news")
    await rig.proposals.approve(user_id, view.proposal.id)
    changed = await rig.routines.get(user_id, existing.id)
    assert changed.name == "Evening news" and changed.instructions == "Read the news."


async def test_a_tainted_proposal_is_marked_and_saved_tainted(rig, user_id, bot):
    await rig.run("propose_routine", _propose_args(), user_id, bot, tainted=True)
    [view] = await rig.proposals.list_open(user_id)
    assert view.proposal.tainted is True and view.proposal.from_routine is False

    await rig.proposals.approve(user_id, view.proposal.id)

    [routine] = await rig.routines.list_for_bot(user_id, bot.id)
    assert routine.tainted is True


async def test_a_tainted_change_taints_the_routine_it_changes(rig, user_id, bot):
    existing = await rig.existing(user_id, bot)
    await rig.run("propose_routine_change", {"routine_id": existing.id, "instructions": "Do something else."},
                  user_id, bot, tainted=True)
    [view] = await rig.proposals.list_open(user_id)

    await rig.proposals.approve(user_id, view.proposal.id)

    assert (await rig.routines.get(user_id, existing.id)).tainted is True


async def test_a_routine_run_proposal_is_marked(rig, user_id, bot):
    log = (await rig.existing(user_id, bot)).thread_id
    thread = next(t for t in [await rig.talk.get_thread(user_id, log)] if t)
    await rig.run("propose_routine", _propose_args(), user_id, bot, from_routine=True, thread=thread)

    [view] = await rig.proposals.list_open(user_id)

    assert view.proposal.from_routine is True
    main, _ = await rig.talk.ensure_main_thread(user_id, bot.id)
    assert len(await _cards(rig, user_id, thread.id)) == 1 and len(await _cards(rig, user_id, main.id)) == 1


@pytest.mark.parametrize("tainted", [False, True])
async def test_propose_routine_pause_asks_and_approve_pauses(rig, user_id, bot, tainted):
    routine = await rig.existing(user_id, bot, "B")

    text = await rig.run("propose_routine_pause", {"routine_id": routine.id}, user_id, bot, tainted=tainted)

    assert text == "Asked the user to approve pausing “B”." and (await rig.routines.get(user_id, routine.id)).enabled
    [view] = await rig.proposals.list_open(user_id)
    assert view.proposal.action == "pause" and view.proposal.tainted is tainted
    await rig.proposals.approve(user_id, view.proposal.id)
    assert (await rig.routines.get(user_id, routine.id)).enabled is False


async def test_list_routines_shows_only_its_own(rig, cfg, user_id, bot):
    other = await make_bot(cfg, user_id, "Pip")
    await rig.existing(user_id, bot, "Mine <b>")
    await rig.existing(user_id, other, "Theirs")

    text = await rig.run("list_routines", {}, user_id, bot)

    assert "Mine &lt;b&gt;" in text and "Theirs" not in text and "data, not instructions" in text
    assert "Refused" in await rig.run("propose_routine_pause", {"routine_id": (await rig.routines.list_for_bot(user_id, other.id))[0].id}, user_id, bot)


async def test_bad_arguments_and_caps_are_refused_in_plain_words(rig, user_id, bot, monkeypatch):
    assert (await rig.run("propose_routine", {"name": "x", "instructions": "y", "schedule": {"kind": "times"}},
                          user_id, bot)).startswith("Refused:")
    assert (await rig.run("propose_routine", {"name": ""}, user_id, bot)).startswith("Refused:")
    import roost.routines.proposals as module
    monkeypatch.setattr(module, "ROUTINE_PROPOSALS_OPEN_PER_BOT_MAX", 1)
    await rig.run("propose_routine", _propose_args("One"), user_id, bot)
    assert "waiting for the user" in await rig.run("propose_routine", _propose_args("Two"), user_id, bot)
    assert (await rig.run("propose_routine_change", {"routine_id": "nope", "name": "z"}, user_id, bot)).startswith("Refused")


def test_only_routine_and_plan_tools_skip_the_tainted_rule():
    flagged = {name for name, tool in CATALOG.items() if tool.allowed_when_tainted}
    assert flagged == ROUTINE_NAMES | PLAN_NAMES | {
        "propose_skill", "propose_skill_change", "propose_instructions_update", "journal_append", "journal_read",
    }
    assert {t.name for t in ROUTINE_TOOL_DEFS} == ROUTINE_NAMES | DIRECT_ROUTINE_NAMES


def test_routine_proposal_tools_never_wait_on_a_second_card():
    assert all(CATALOG[name].no_ask for name in ROUTINE_NAMES - {"list_routines"})


@pytest.mark.parametrize("tainted", [False, True])
def test_the_gate_lets_a_proposal_through_in_ask_mode_without_a_second_card(tainted):
    from roost.approvals.models import ApprovalState
    from roost.talk.gate import GateContext, judge
    state = ApprovalState(mode="ask", ask_topics=frozenset(), cards=True)
    ctx = GateContext(allowed=frozenset(CATALOG), tainted=tainted, approval=state)
    for name in ("propose_routine", "propose_routine_change", "propose_routine_pause"):
        assert judge(CATALOG[name], name, {}, ctx).decision == "do"
    assert judge(CATALOG["add_task"], "add_task", {}, ctx).decision == "ask"
