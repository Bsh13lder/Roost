"""Steer (docs/plans/2026-10-22-roost-steer.md) through ``TurnRunner``: a message sent while the bot's run for
that chat works is read mid-run, a run that did nothing yet restarts, quick messages become one turn, and Stop
ends the run at the next boundary with a line of what it did."""

from __future__ import annotations

import asyncio

import pytest

import roost.talk.stop_flow as stop_flow
from roost.bots.status import ActivityBoard
from roost.config import load_config
from roost.constants import FIRST_LINE_ACTIVITY, STEER_TURN_PREFIX
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.llm.scripted import ScriptedModel
from roost.llm.types import TextDelta, ToolCallRequested, TurnDone
from roost.talk.runner import TurnRunner
from roost.work.models import WorkDraft, WorkKind
from team_helpers import Rig, make_bot, make_rig, send, wait_idle


class HoldModel:
    """Wraps a ``ScriptedModel``; the calls numbered in ``hold`` (1-based) wait for ``release(n)``."""

    def __init__(self, script, hold=()):
        self._inner = ScriptedModel(script=script)
        self.requests: list = []
        self.reached = {n: asyncio.Event() for n in hold}
        self._release = {n: asyncio.Event() for n in hold}

    def release(self, n: int) -> None:
        self._release[n].set()

    async def stream(self, request):
        self.requests.append(request)
        n = len(self.requests)
        if n in self.reached:
            self.reached[n].set()
            await self._release[n].wait()
        async for event in self._inner.stream(request):
            yield event


def _call(name: str, call_id: str = "c1", **arguments) -> ToolCallRequested:
    return ToolCallRequested(id=call_id, name=name, arguments=arguments)


def _tool_step(*events):
    return [*events, TurnDone("tool_use")]


def _say(text: str):
    return [TextDelta(text), TurnDone("end_turn")]


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


async def _runs(cfg, user_id):
    async with db_session(cfg) as db:
        rows = await (await db.execute(
            "SELECT id, outcome FROM runs WHERE user_id = ? ORDER BY started_at", (user_id,))).fetchall()
    return [(row["id"], row["outcome"]) for row in rows]


async def _states(cfg, user_id):
    async with db_session(cfg) as db:
        rows = await (await db.execute(
            "SELECT state, run_id FROM work_items WHERE user_id = ? ORDER BY rowid", (user_id,))).fetchall()
    return [(row["state"], row["run_id"]) for row in rows]


async def _start(rig: Rig, user_id, bot, text: str, wait_for: int = 1):
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, text)
    await asyncio.wait_for(rig.model.reached[wait_for].wait(), 2)
    return thread


async def test_a_message_sent_mid_run_is_read_by_that_run(cfg, user_id, bot):
    model = HoldModel([_tool_step(TextDelta("On it."), _call("add_task", title="Call bank")), _say("Done both.")],
                      hold=(1,))
    rig = make_rig(cfg, model)
    thread = await _start(rig, user_id, bot, "add a task to call the bank")
    assert rig.runner.message_status(bot.id, thread.id) == "steered"
    await send(rig, user_id, bot.id, thread.id, "and remind me Tuesday")
    model.release(1)
    await wait_idle(rig.runner)

    runs = await _runs(cfg, user_id)
    assert len(runs) == 1 and runs[0][1] == "done"
    assert await _states(cfg, user_id) == [("done", runs[0][0]), ("done", runs[0][0])]
    steered = model.requests[1].turns[-1]
    assert (steered.role, steered.text) == ("user", STEER_TURN_PREFIX + "and remind me Tuesday")
    shown = [(m.role, m.body) for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "text"]
    assert shown == [("user", "add a task to call the bank"), ("user", "and remind me Tuesday"),
                     ("bot", "On it.\n\nDone both.")]


async def test_a_message_in_another_chat_waits_for_its_own_run(cfg, user_id, bot):
    model = HoldModel([_say("one"), _say("two")], hold=(1,))
    rig = make_rig(cfg, model)
    thread = await _start(rig, user_id, bot, "first")
    other = await rig.talk.create_thread(user_id, bot.id)
    assert rig.runner.message_status(bot.id, other.id) == "queued"
    await send(rig, user_id, bot.id, other.id, "elsewhere")
    model.release(1)
    await wait_idle(rig.runner)
    assert len(await _runs(cfg, user_id)) == 2
    assert [m.body for m in await rig.talk.list_messages(user_id, thread.id) if m.role == "bot"] == ["one"]


async def test_a_run_that_did_nothing_yet_restarts_with_both_messages(cfg, user_id, bot):
    model = HoldModel([_tool_step(TextDelta("Checking the time."), _call("get_time")), _say("Both covered.")],
                      hold=(1,))
    rig = make_rig(cfg, model)
    thread = await _start(rig, user_id, bot, "what time is it")
    await send(rig, user_id, bot.id, thread.id, "and in Tokyo")
    model.release(1)
    await wait_idle(rig.runner)

    runs = await _runs(cfg, user_id)
    assert runs == [(runs[0][0], "done")]           # one run id for the turn, counted once
    restarted = [t.text for t in model.requests[1].turns if t.role == "user"]
    assert restarted == ["what time is it", "and in Tokyo"]   # a fresh start: plain history, no steer mark
    bots = [m.body for m in await rig.talk.list_messages(user_id, thread.id) if m.role == "bot"]
    assert bots == ["Both covered."]                  # the first attempt's words were dropped with it


async def test_no_restart_once_a_write_happened(cfg, user_id, bot):
    model = HoldModel([_tool_step(_call("add_task", title="Call bank")), _tool_step(_call("get_time", "c2")),
                       _say("Done.")], hold=(2,))
    rig = make_rig(cfg, model)
    thread = await _start(rig, user_id, bot, "add a task", wait_for=2)
    await send(rig, user_id, bot.id, thread.id, "thanks")
    model.release(2)
    await wait_idle(rig.runner)
    assert len(model.requests) == 3
    assert model.requests[2].turns[-1].text == STEER_TURN_PREFIX + "thanks"
    async with db_session(cfg) as db:
        assert (await (await db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ?", (user_id,))).fetchone())[0] == 1


async def test_steering_never_clears_taint(cfg, user_id, bot):
    model = HoldModel([_tool_step(_call("add_task", title="Read news")),
                       _tool_step(_call("open_page", "c2", url="https://example.com")), _say("Read it.")], hold=(2,))
    rig = make_rig(cfg, model)
    thread = await _start(rig, user_id, bot, "read the news", wait_for=2)
    await send(rig, user_id, bot.id, thread.id, "quickly please")
    model.release(2)
    await wait_idle(rig.runner)
    reply = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.role == "bot"][-1]
    assert reply.body == "Read it." and reply.tainted


async def test_a_handoff_run_is_not_steered(cfg, user_id, bot):
    model = HoldModel([_say("handoff answer"), _say("your answer")], hold=(1,))
    rig = make_rig(cfg, model)
    thread = await rig.talk.create_thread(user_id, bot.id)
    await rig.runner.submit(user_id, WorkDraft(bot_id=bot.id, thread_id=thread.id, kind=WorkKind.HANDOFF,
                                               origin="from Chief", body="look this up"))
    await asyncio.wait_for(model.reached[1].wait(), 2)
    assert rig.runner.message_status(bot.id, thread.id) == "queued"
    await send(rig, user_id, bot.id, thread.id, "hello")
    model.release(1)
    await wait_idle(rig.runner)
    assert len(await _runs(cfg, user_id)) == 2
    assert all(t.text != STEER_TURN_PREFIX + "hello" for r in model.requests for t in r.turns)


async def test_a_resting_bot_starts(cfg, user_id, bot):
    rig = make_rig(cfg, HoldModel([_say("hi")]))
    thread = await rig.talk.create_thread(user_id, bot.id)
    assert rig.runner.message_status(bot.id, thread.id) == "started"


async def test_quick_messages_become_one_turn(cfg, user_id, bot):
    rig = make_rig(cfg, HoldModel([_say("One answer.")]))
    runner = TurnRunner(cfg, rig.bots, rig.talk, rig.events, rig.desks, rig.model, ActivityBoard(), debounce_s=0.3)
    rig = Rig(runner=runner, bots=rig.bots, talk=rig.talk, events=rig.events, desks=rig.desks, model=rig.model)
    thread = await rig.talk.create_thread(user_id, bot.id)
    sub = rig.events.subscribe(user_id)
    await send(rig, user_id, bot.id, thread.id, "hi")
    await asyncio.sleep(0.1)
    assert rig.runner.message_status(bot.id, thread.id) == "steered"
    other = await rig.talk.create_thread(user_id, bot.id)
    assert rig.runner.message_status(bot.id, other.id) == "queued"
    await send(rig, user_id, bot.id, thread.id, "are you there")
    first = await asyncio.wait_for(sub.__anext__(), 1)
    assert (first["type"], first["status"], first["activity"]) == ("bot_status", "on_it", FIRST_LINE_ACTIVITY)
    sub.close()
    await wait_idle(rig.runner)
    assert len(await _runs(cfg, user_id)) == 1
    assert [t.text for t in rig.model.requests[0].turns if t.role == "user"] == ["hi", "are you there"]


async def test_a_debounce_that_finds_nothing_to_run_settles_the_bot(cfg, user_id, bot):
    rig = make_rig(cfg, HoldModel([_say("never")]))
    runner = TurnRunner(cfg, rig.bots, rig.talk, rig.events, rig.desks, rig.model, ActivityBoard(), debounce_s=0.3)
    rig = Rig(runner=runner, bots=rig.bots, talk=rig.talk, events=rig.events, desks=rig.desks, model=rig.model)
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "hi")
    await asyncio.sleep(0.05)
    await rig.runner.stop(user_id, bot.id)
    await wait_idle(rig.runner)
    assert rig.model.requests == []
    assert (await rig.bots.get(user_id, bot.id)).status.value == "resting"


# --- Stop ------------------------------------------------------------------------------------------------


async def test_stop_ends_at_the_next_boundary_and_lists_what_was_done(cfg, user_id, bot):
    model = HoldModel([_tool_step(TextDelta("On it."), _call("add_task", title="Call bank")), _say("never")],
                      hold=(2,))
    rig = make_rig(cfg, model)
    thread = await _start(rig, user_id, bot, "add a task", wait_for=2)
    await send(rig, user_id, bot.id, thread.id, "waiting one")
    report = await rig.runner.stop(user_id, bot.id)
    await wait_idle(rig.runner)

    assert [i.body for i in report.running] == ["add a task"] and report.interrupted == ()
    assert report.done == ("Added a task",)
    notes = [m.body for m in await rig.talk.list_messages(user_id, thread.id) if m.role == "system"]
    assert notes == ["Stopped. Done so far: Added a task. Dropped 1 waiting message: “waiting one”."]
    assert [o for _, o in await _runs(cfg, user_id)] == ["stopped"]
    bots = [m.body for m in await rig.talk.list_messages(user_id, thread.id) if m.role == "bot"]
    assert bots == ["On it."]


async def test_a_run_that_does_not_reach_a_boundary_is_cancelled_after_the_grace(cfg, user_id, bot, monkeypatch):
    monkeypatch.setattr(stop_flow, "STOP_GRACE_SECONDS", 0.2)
    rig = make_rig(cfg, HoldModel([_tool_step(_call("hang"))]))
    hung = asyncio.Event()

    async def hang(call):
        hung.set()
        await asyncio.Event().wait()
    thread = await rig.talk.create_thread(user_id, bot.id)
    import roost.talk.tool_runner as tool_runner_module
    monkeypatch.setattr(tool_runner_module.ToolRunner, "run", lambda self, call: hang(call))
    await send(rig, user_id, bot.id, thread.id, "go")
    await asyncio.wait_for(hung.wait(), 2)
    await asyncio.wait_for(rig.runner.stop(user_id, bot.id), 3)
    await wait_idle(rig.runner)
    assert [o for _, o in await _runs(cfg, user_id)] == ["stopped"]
    assert [m.body for m in await rig.talk.list_messages(user_id, thread.id) if m.role == "system"] == ["Stopped."]


# --- review fixes ----------------------------------------------------------------------------------------


async def test_a_tainted_message_steered_into_a_clean_run_taints_it(cfg, user_id, bot):
    """A question-book answer can be a tainted message item: steering it in must taint the run that reads it."""
    model = HoldModel([_tool_step(_call("add_task", title="Call bank")), _say("First."), _say("Second.")],
                      hold=(2,))
    rig = make_rig(cfg, model)
    thread = await _start(rig, user_id, bot, "add a task", wait_for=2)
    await rig.runner.submit(user_id, WorkDraft(
        bot_id=bot.id, thread_id=thread.id, kind=WorkKind.MESSAGE, origin="you", body="answer", tainted=True,
    ))
    model.release(2)
    await wait_idle(rig.runner)
    assert len(model.requests) == 3
    reply = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.role == "bot"][-1]
    assert reply.tainted


async def test_a_message_queued_during_stops_grace_still_runs(cfg, user_id, bot, monkeypatch):
    """Stop drops only what the stopped run holds: a message sent while it was stopping is answered next."""
    import roost.talk.tool_runner as tool_runner_module
    rig = make_rig(cfg, HoldModel([_tool_step(_call("slow")), _say("Answered the new one.")]))
    entered, finish = asyncio.Event(), asyncio.Event()

    async def slow(call):
        entered.set()
        await finish.wait()
        return "ok"
    monkeypatch.setattr(tool_runner_module.ToolRunner, "run", lambda self, call: slow(call))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "go")
    await asyncio.wait_for(entered.wait(), 2)
    stopping = asyncio.create_task(rig.runner.stop(user_id, bot.id))
    await asyncio.sleep(0.05)
    assert rig.runner.message_status(bot.id, thread.id) == "queued"
    await send(rig, user_id, bot.id, thread.id, "and this one")
    finish.set()
    report = await asyncio.wait_for(stopping, 3)
    await wait_idle(rig.runner)
    assert "and this one" not in [i.body for i in report.dropped]
    bots = [m.body for m in await rig.talk.list_messages(user_id, thread.id) if m.role == "bot"]
    assert bots[-1] == "Answered the new one."
