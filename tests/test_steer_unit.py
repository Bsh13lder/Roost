"""Steer (docs/plans/2026-10-22-roost-steer.md): the per-run ``RunSteer``, its done lines and the step loop's
boundaries, with no database."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from roost.constants import STEER_MAX_RESTARTS, STEER_TURN_PREFIX, STOP_SKIPPED_TEXT
from roost.llm.types import TextDelta, ToolCallRequested, TurnDone
from roost.talk.steer import PAST, RunRestart, RunSteer, RunStopped, past_line, steer_turn
from roost.talk.steps import step_loop
from roost.work.models import WorkItem, WorkKind, WorkState

TOOL_LINES = Path(__file__).resolve().parents[1] / "web" / "src" / "lib" / "toolLines.ts"


def _item(body: str, item_id: str = "w1", tainted: bool = False) -> WorkItem:
    return WorkItem(
        id=item_id, user_id="u", bot_id="b", thread_id="t", kind=WorkKind.MESSAGE, origin="you", body=body,
        tainted=tainted, depth=0, parent_item_id=None, message_id=None, state=WorkState.CLAIMED, run_id="r",
        inflight=None, result=None, result_tainted=False, created_at="", updated_at="",
    )


class _Taker:
    """Hands out ``batches`` one per call, then nothing."""

    def __init__(self, *batches: tuple[WorkItem, ...]):
        self.batches = list(batches)
        self.calls = 0

    async def __call__(self) -> tuple[WorkItem, ...]:
        self.calls += 1
        return self.batches.pop(0) if self.batches else ()


def test_past_lines_read_like_the_chat_steps():
    assert past_line("adding a task") == "Added a task"
    assert past_line("saving a note") == "Saved a note"
    assert past_line("frobbing") == "Frobbing"


def test_the_past_table_matches_the_web_one():
    table = TOOL_LINES.read_text(encoding="utf-8").split("const PAST")[1].split("};")[0]
    web = dict(re.findall(r'\b([a-z]+): "([a-z]+)"', table))
    assert dict(PAST) == web


async def test_a_steer_that_is_not_steerable_takes_nothing():
    taker = _Taker((_item("hi"),))
    steer = RunSteer(take=taker, steerable=False)
    assert await steer.take() == ()
    assert taker.calls == 0


async def test_take_keeps_what_it_took_and_a_stop_takes_nothing_more():
    taker = _Taker((_item("one"),), (_item("two", "w2"),))
    steer = RunSteer(take=taker, steerable=True)
    assert [i.body for i in await steer.take()] == ["one"]
    steer.request_stop()
    assert steer.stopping
    assert await steer.take() == ()
    assert [i.body for i in steer.taken] == ["one"]


async def test_done_lines_and_side_effects():
    steer = RunSteer(take=None, steerable=True)
    assert steer.may_restart()
    steer.note_done("get_time", None, side_effect=False)
    assert steer.may_restart() and steer.done_lines == ()
    steer.note_done("add_task", "adding a task")
    steer.note_done("click", None)
    assert not steer.may_restart()
    assert steer.done_lines == ("Added a task", "Click")


def test_restarts_are_capped():
    steer = RunSteer(take=None, steerable=True)
    for _ in range(STEER_MAX_RESTARTS):
        assert steer.may_restart()
        steer.restarted()
    assert not steer.may_restart()


async def test_wait_stop_returns_once_stopped():
    steer = RunSteer(take=None, steerable=True)
    waiter = asyncio.create_task(steer.wait_stop())
    await asyncio.sleep(0)
    assert not waiter.done()
    steer.request_stop()
    await asyncio.wait_for(waiter, 1)


def test_a_steered_turn_is_a_marked_user_turn():
    turn = steer_turn(_item("also check Tuesday"))
    assert turn.role == "user"
    assert turn.text == STEER_TURN_PREFIX + "also check Tuesday"


# --- the step loop's boundaries --------------------------------------------------------------------------


class _Runner:
    """A ToolRunner stand-in: answers every call with ``ok:<name>``; ``writes`` are reported to the steer."""

    def __init__(self, steer: RunSteer | None = None, writes: frozenset[str] = frozenset()):
        self.block = None
        self.parked = None
        self.tainted = False
        self.calls: list[str] = []
        self._steer = steer
        self._writes = writes

    async def run(self, call: ToolCallRequested) -> str:
        self.calls.append(call.name)
        if self._steer is not None:
            self._steer.note_done(call.name, None, side_effect=call.name in self._writes)
        return f"ok:{call.name}"


class _Model:
    def __init__(self, steps, before=None):
        self.steps = list(steps)
        self.requests: list = []
        self.before = before or {}

    async def stream(self, request):
        self.requests.append(request)
        hook = self.before.get(len(self.requests))
        if hook is not None:
            await hook()
        for event in self.steps.pop(0):
            yield event


def _call(name: str, call_id: str = "c1") -> ToolCallRequested:
    return ToolCallRequested(id=call_id, name=name, arguments={})


def _say(text: str):
    return [TextDelta(text), TurnDone("end_turn")]


async def _loop(model, runner, steer, max_steps: int = 10, deadline_s: float = 30):
    from roost.llm.types import ModelRequest
    said: list[str] = []

    async def on_delta(text: str) -> None:
        said.append(text)

    reply, capped = await step_loop(
        model=model, tool_runner=runner, max_steps=max_steps, deadline_s=deadline_s, on_delta=on_delta, steer=steer,
        request_for=lambda added: ModelRequest(system="s", turns=added, tools=(), model="m"),
    )
    return reply, capped, said


async def test_a_message_taken_after_a_tool_step_reaches_the_next_request():
    steer = RunSteer(take=_Taker((_item("and Tuesday"),)), steerable=True)
    runner = _Runner(steer, writes=frozenset({"add_task"}))
    model = _Model([[TextDelta("On it."), _call("add_task")], _say("Done both.")])
    reply, capped, _ = await _loop(model, runner, steer)
    assert (reply, capped) == ("On it.\n\nDone both.", False)
    last = model.requests[-1].turns
    assert last[-1].role == "user" and last[-1].text.endswith("and Tuesday")
    assert last[-2].role == "tool"


async def test_a_message_that_lands_during_the_final_answer_keeps_the_run_going():
    steer = RunSteer(take=_Taker((_item("one more"),)), steerable=True)
    model = _Model([_say("First answer."), _say("And the second.")])
    reply, _, _ = await _loop(model, _Runner(steer), steer)
    assert reply == "First answer.\n\nAnd the second."
    assert len(model.requests) == 2


async def test_a_run_with_no_side_effects_restarts_with_the_new_messages():
    steer = RunSteer(take=_Taker((_item("actually, Friday"),)), steerable=True)
    model = _Model([[_call("get_time")], _say("never")])
    with pytest.raises(RunRestart) as raised:
        await _loop(model, _Runner(steer), steer)
    assert [i.body for i in raised.value.items] == ["actually, Friday"]
    assert len(model.requests) == 1


async def test_no_restart_after_a_side_effect():
    steer = RunSteer(take=_Taker((_item("also this"),)), steerable=True)
    model = _Model([[_call("add_task")], _say("Done.")])
    reply, _, _ = await _loop(model, _Runner(steer, writes=frozenset({"add_task"})), steer)
    assert reply == "Done."
    assert model.requests[-1].turns[-1].text.endswith("also this")


async def test_stop_at_a_boundary_ends_the_run_before_the_next_model_call():
    steer = RunSteer(take=None, steerable=True)
    runner = _Runner(steer)

    async def stop_then_ok(call):
        steer.request_stop()
        return "ok"
    runner.run = stop_then_ok
    model = _Model([[TextDelta("On it."), _call("get_time")], _say("never")])
    with pytest.raises(RunStopped):
        await _loop(model, runner, steer)
    assert len(model.requests) == 1


async def test_stop_skips_the_rest_of_a_steps_calls():
    steer = RunSteer(take=None, steerable=True)
    ran: list[str] = []

    class _StopsFirst(_Runner):
        async def run(self, call):
            ran.append(call.name)
            steer.request_stop()
            return "ok"
    model = _Model([[_call("add_task", "c1"), _call("add_note", "c2")]])
    with pytest.raises(RunStopped):
        await _loop(model, _StopsFirst(steer), steer)
    assert ran == ["add_task"]


async def test_skipped_calls_say_so():
    from roost.talk.steps import _run_calls
    steer = RunSteer(take=None, steerable=True)
    steer.request_stop()
    turns = await _run_calls(_Runner(steer), [_call("add_task")], steer)
    assert turns[0].text == STOP_SKIPPED_TEXT


async def test_stop_cuts_a_streaming_step_at_once():
    steer = RunSteer(take=None, steerable=True)

    class _Hangs:
        async def stream(self, request):
            yield TextDelta("Dear landl")
            steer.request_stop()
            await asyncio.Event().wait()
            yield TurnDone("end_turn")
    with pytest.raises(RunStopped):
        await asyncio.wait_for(_loop(_Hangs(), _Runner(steer), steer), 2)


async def test_without_a_steer_the_loop_is_unchanged():
    model = _Model([[_call("get_time")], _say("It is noon.")])
    reply, capped, _ = await _loop(model, _Runner(), None)
    assert (reply, capped) == ("It is noon.", False)


async def test_after_an_answer_a_later_message_steers_and_never_restarts():
    steer = RunSteer(take=_Taker((_item("one"),), (_item("two", "w2"),)), steerable=True)
    model = _Model([_say("First."), _say("Second.")])
    reply, _, _ = await _loop(model, _Runner(steer), steer)
    assert reply == "First.\n\nSecond."
    users = [t.text for t in model.requests[-1].turns if t.role == "user"]
    assert [u.removeprefix(STEER_TURN_PREFIX) for u in users] == ["one", "two"]


# --- review fixes: taint rides with a steered message; no take that no step can answer --------------------


async def test_a_tainted_steered_message_taints_the_run_at_a_boundary():
    steer = RunSteer(take=_Taker((_item("from the question book", tainted=True),)), steerable=True)
    runner = _Runner(steer, writes=frozenset({"add_task"}))
    model = _Model([[_call("add_task")], _say("Done.")])
    await _loop(model, runner, steer)
    assert runner.tainted is True


async def test_a_tainted_message_taken_during_the_final_answer_taints_the_run():
    steer = RunSteer(take=_Taker((_item("tainted", tainted=True),)), steerable=True)
    runner = _Runner(steer)
    await _loop(_Model([_say("First."), _say("Second.")]), runner, steer)
    assert runner.tainted is True


async def test_a_clean_steered_message_leaves_the_run_clean():
    steer = RunSteer(take=_Taker((_item("clean"),)), steerable=True)
    runner = _Runner(steer)
    await _loop(_Model([_say("First."), _say("Second.")]), runner, steer)
    assert runner.tainted is False


async def test_no_take_at_the_final_answer_on_the_last_allowed_step():
    taker = _Taker((_item("late"),))
    steer = RunSteer(take=taker, steerable=True)
    reply, capped, _ = await _loop(_Model([_say("Only answer.")]), _Runner(steer), steer, max_steps=1)
    assert (reply, capped) == ("Only answer.", False)
    assert taker.calls == 0 and steer.taken == ()


async def test_no_take_at_the_final_answer_after_the_deadline():
    taker = _Taker((_item("late"),))
    steer = RunSteer(take=taker, steerable=True)
    model = _Model([_say("Only answer.")], before={1: lambda: asyncio.sleep(0.1)})
    reply, capped, _ = await _loop(model, _Runner(steer), steer, deadline_s=0.05)
    assert (reply, capped) == ("Only answer.", False)
    assert taker.calls == 0 and steer.taken == ()
