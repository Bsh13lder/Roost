"""Ask cards (approval plan Task 8): an approval parks the run, Yes runs the stored call, No tells the bot."""

from __future__ import annotations

import pytest

from approval_helpers import CardRig, make_card_rig, set_mode
from roost.approvals.models import ApprovalState, CardState
from roost.approvals.texts import NEEDS_YOUR_OK_TEXT, NO_LINE, NOT_PERFORMED_TEXT, PARKED_TEXT, YES_LINE
from roost.bots.models import BotStatus
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.desk import DeskFactory
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.scripted_team import ScriptedTeamModel
from roost.llm.types import TextDelta, ToolCallRequested, TurnDone
from roost.talk.gate import Gate
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from roost.talk.tool_runner import ToolRunner
from roost.talk.tools import run_tool_names
from team_helpers import RecordingModel, Rig, ask, make_bot, say, send, wait_idle


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _add_task(call_id: str, title: str = "Call bank"):
    return ToolCallRequested(id=call_id, name="add_task", arguments={"title": title})


def _tool_step(*calls):
    return [*calls, TurnDone("tool_use")]


def _model(scripts) -> RecordingModel:
    return RecordingModel(ScriptedTeamModel(scripts))


async def _count(cfg, sql: str, *params) -> int:
    async with db_session(cfg) as db:
        return (await (await db.execute(sql, params)).fetchone())[0]


async def _tasks(cfg, user_id: str) -> int:
    return await _count(cfg, "SELECT COUNT(*) FROM tasks WHERE user_id = ?", user_id)


async def _kinds(rig: CardRig, user_id: str, thread_id: str, kind: str):
    return [m for m in await rig.talk.list_messages(user_id, thread_id) if m.kind == kind]


async def _parked(cfg, user_id: str, script=None):
    """A bot in Ask every time whose first message makes it ask to add a task."""
    bot = await make_bot(cfg, user_id, "Scout")
    rig = make_card_rig(cfg, _model({"Scout": script or [_tool_step(_add_task("c1")), say("Added it.")]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "Add a task to call the bank")
    await wait_idle(rig.runner)
    return rig, bot, thread


async def test_an_ask_parks_the_run_after_its_step_and_posts_one_card(cfg, user_id):
    rig, bot, thread = await _parked(cfg, user_id)
    cards = await rig.store.list_open(user_id)
    assert len(cards) == 1 and cards[0].bot_id == bot.id and cards[0].kind == "ask"
    assert [s.tool for s in cards[0].steps] == ["add_task"]
    assert cards[0].steps[0].title.startswith("Add a task")
    assert len(await _kinds(rig, user_id, thread.id, "approval")) == 1
    assert await _tasks(cfg, user_id) == 0
    assert len(rig.model.requests) == 1          # the run stopped after the step that asked


async def test_later_calls_in_that_step_are_not_performed(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Scout")
    runner = ToolRunner(
        user_id=user_id, bot_id=bot.id, desk=DeskFactory(cfg).for_bot(bot.id), gate=Gate(cfg),
        activity=ActivityBoard(), events=EventHub(cfg), allowed=run_tool_names(bot, team=False),
        domain=make_card_rig(cfg, None).runner.domain,
        approval=ApprovalState("ask", frozenset(), True),
        thread_id=None,
    )
    first = await runner.run(_add_task("a"))
    second = await runner.run(_add_task("b", "Another"))
    assert first == PARKED_TEXT and second == NOT_PERFORMED_TEXT
    assert runner.parked is not None and runner.parked.tool == "add_task"
    assert await _tasks(cfg, user_id) == 0


async def test_the_bot_shows_asking_you_until_the_card_closes(cfg, user_id):
    rig, bot, thread = await _parked(cfg, user_id)
    assert (await rig.bots.get(user_id, bot.id)).status is BotStatus.ASKING_YOU
    card = (await rig.store.list_open(user_id))[0]
    await rig.service.answer(user_id, card.id, "no")
    await wait_idle(rig.runner)
    assert (await rig.bots.get(user_id, bot.id)).status is BotStatus.RESTING


async def test_yes_runs_exactly_the_stored_call_and_carries_on(cfg, user_id):
    rig, bot, thread = await _parked(cfg, user_id)
    card = (await rig.store.list_open(user_id))[0]
    answered = await rig.service.answer(user_id, card.id, "yes")
    await wait_idle(rig.runner)
    assert answered.state is CardState.APPROVED
    assert await _tasks(cfg, user_id) == 1
    results = await _kinds(rig, user_id, thread.id, "approval_result")
    assert len(results) == 1
    assert await _count(cfg, "SELECT COUNT(*) FROM work_items WHERE user_id = ? AND kind = 'card_answer'", user_id) == 1
    lines = await _kinds(rig, user_id, thread.id, "card_answer")
    assert [m.body for m in lines] == [YES_LINE.format(title=card.steps[0].title)]
    second = rig.model.requests[-1]
    assert any(t.role == "user" and t.text == results[0].body for t in second.turns)
    assert await _tasks(cfg, user_id) == 1       # the continuing run did not add it again
    assert (await rig.store.get(user_id, card.id)).state is CardState.APPROVED


async def test_no_runs_nothing_and_tells_the_bot(cfg, user_id):
    rig, bot, thread = await _parked(cfg, user_id)
    card = (await rig.store.list_open(user_id))[0]
    answered = await rig.service.answer(user_id, card.id, "no")
    await wait_idle(rig.runner)
    assert answered.state is CardState.DECLINED
    assert await _tasks(cfg, user_id) == 0
    assert await _kinds(rig, user_id, thread.id, "approval_result") == []
    lines = await _kinds(rig, user_id, thread.id, "card_answer")
    assert [m.body for m in lines] == [NO_LINE.format(title=card.steps[0].title)]
    assert any(t.text == lines[0].body for t in rig.model.requests[-1].turns)


async def test_a_newer_ask_replaces_an_open_card(cfg, user_id):
    rig, bot, thread = await _parked(
        cfg, user_id, [_tool_step(_add_task("c1")), _tool_step(_add_task("c2", "Pay rent")), say("ok")])
    first = (await rig.store.list_open(user_id))[0]
    await send(rig, user_id, bot.id, thread.id, "Also add a task to pay the rent")
    await wait_idle(rig.runner)
    open_cards = await rig.store.list_open(user_id)
    assert len(open_cards) == 1 and open_cards[0].id != first.id
    assert (await rig.store.get(user_id, first.id)).state is CardState.EXPIRED


async def test_a_handoff_or_room_run_gets_needs_your_ok_and_no_card(cfg, user_id):
    chief = await make_bot(cfg, user_id, "Chief")
    scout = await make_bot(cfg, user_id, "Scout")
    model = _model({
        "Chief": [_tool_step(ask("h1", "Scout", "add a task")), say("done")],
        "Scout": [_tool_step(_add_task("c1")), say("could not")],
    })
    rig = make_card_rig(cfg, model)
    thread = await rig.talk.create_thread(user_id, chief.id)
    await send(rig, user_id, chief.id, thread.id, "ask Scout")
    await wait_idle(rig.runner, timeout=8)
    assert await rig.store.list_open(user_id) == ()
    seen = [t.text for r in model.requests if r.agent == "Scout" for t in r.turns if t.role == "tool"]
    assert NEEDS_YOUR_OK_TEXT in seen
    assert await _tasks(cfg, user_id) == 0


async def test_restart_keeps_asking_you_for_an_open_card(cfg, user_id):
    rig, bot, thread = await _parked(cfg, user_id)
    await rig.bots.set_status(user_id, bot.id, BotStatus.RESTING)
    await rig.runner.restore_asking_on_boot()
    assert (await rig.bots.get(user_id, bot.id)).status is BotStatus.ASKING_YOU


async def test_turnrunner_without_approvals_keeps_todays_behaviour(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Scout")
    model = _model({"Scout": [_tool_step(_add_task("c1")), say("Added it.")]})
    bots, talk, events, desks = BotStore(cfg), TalkStore(cfg), EventHub(cfg), DeskFactory(cfg)
    runner = TurnRunner(cfg, bots, talk, events, desks, model, ActivityBoard())
    thread = await talk.create_thread(user_id, bot.id)
    await send(Rig(runner, bots, talk, events, desks, model), user_id, bot.id, thread.id, "go")
    await wait_idle(runner)
    assert await _tasks(cfg, user_id) == 1


async def test_the_ask_card_shows_every_stored_argument_and_drops_unknown_ones(cfg, user_id):
    call = ToolCallRequested(id="c1", name="log_expense", arguments={
        "amount": 9999, "income": True, "note": "coffee", "sneaky": "x"})
    rig, bot, thread = await _parked(cfg, user_id, [_tool_step(call), say("ok")])
    card = (await rig.store.list_open(user_id))[0]
    step = card.steps[0]
    assert [r.key for r in step.rows][:2] == ["amount", "income"]
    assert "sneaky" not in step.arguments and {r.key for r in step.rows} == set(step.arguments)


async def test_a_step_that_cannot_be_shown_opens_no_card(cfg, user_id):
    deep: dict = {"a": 1}
    for _ in range(12):
        deep = {"n": deep}
    call = ToolCallRequested(id="c1", name="add_task", arguments={"title": "x", "notes": deep})
    rig, bot, thread = await _parked(cfg, user_id, [_tool_step(call), say("ok")])
    assert await rig.store.list_open(user_id) == ()


async def test_a_parked_run_that_only_said_on_it_leaves_just_its_card(cfg, user_id):
    # Owner, 2026-11-04: each card's run left an "On it: …" bubble of its own above the card.
    script = [[TextDelta("On it: adding the task."), _add_task("c1"), TurnDone("tool_use")], say("Added it.")]
    rig, bot, thread = await _parked(cfg, user_id, script)
    bot_rows = [m.kind for m in await rig.talk.list_messages(user_id, thread.id) if m.role == "bot"]
    assert bot_rows == ["approval"]
