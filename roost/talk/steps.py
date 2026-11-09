"""The one step loop a run and a helper share: stream the model, run its tool
calls through a ``ToolRunner``, feed the results back, repeat.

Moved out of ``roost/talk/turn.py``. The loop knows nothing about chats,
threads or events: its caller builds each request (``request_for``) and hears
each streamed chunk (``on_delta``), so a bot's reply and a helper's silent
work run the same code.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import replace
from typing import Awaitable, Callable

from roost.llm.types import (
    SCREENSHOT_GONE,
    SCREENSHOT_SHOWN,
    ChatTurn,
    ImagePart,
    Model,
    ModelRequest,
    TextDelta,
    ToolCallRequested,
    TurnDone,
)
from roost.constants import STOP_SKIPPED_TEXT
from roost.usage.scope import note_usage
from roost.talk.steer import RunRestart, RunSteer, RunStopped, steer_turn
from roost.talk.tool_runner import ToolRunner
from roost.talk.tools import PARALLEL_TOOLS
from roost.work.models import WorkItem

# ``request_for(added)`` builds the next request from the turns this loop has added so far.
RequestFor = Callable[[tuple[ChatTurn, ...]], ModelRequest]
OnDelta = Callable[[str], Awaitable[None]]


PARAGRAPH_BREAK = "\n\n"
LOOK_TOOL = "look"
SCREENSHOT_MEDIA_TYPE = "image/jpeg"


def _newest_image(tool_runner: object) -> bytes | None:
    """The runner's newest look image (C3, ``ComputerUse`` through ``ToolRunner.newest_image``); a runner
    without screen tools has none."""
    newest = getattr(tool_runner, "newest_image", None)
    return newest() if callable(newest) else None


def with_screen(request: ModelRequest, image: bytes | None) -> ModelRequest:
    """The request the model sees: the newest look's image attached (if any), and every other look turn
    rewritten to say its screenshot is not shown. Builds new turns; the stored ones never change."""
    looks = [i for i, turn in enumerate(request.turns) if turn.role == "tool" and turn.tool_name == LOOK_TOOL]
    if not looks and image is None:
        return request
    keep = looks[-1] if looks and image is not None else None
    turns = tuple(
        replace(turn, text=turn.text.replace(SCREENSHOT_SHOWN, SCREENSHOT_GONE)) if i in looks and i != keep else turn
        for i, turn in enumerate(request.turns)
    )
    # Your attached pictures (chat pictures, owner 2026-11-05) stay first; the screen's look comes after them.
    shot = ImagePart(SCREENSHOT_MEDIA_TYPE, image, after_turn=keep) if image is not None else None
    images = (*request.images, shot) if shot is not None else request.images
    return replace(request, turns=turns, images=images)


async def _stream_step(
    model: Model, request: ModelRequest, on_delta: OnDelta, *, live: bool = True, lead: str = "",
) -> tuple[str, list[ToolCallRequested]]:
    """One ``model.stream()`` call: hand each ``TextDelta`` to ``on_delta`` and
    accumulate it, collect every ``ToolCallRequested``. ``TurnDone`` carries a
    ``stop_reason`` this loop doesn't need: its arrival ends the ``async for``.
    ``live=False`` holds the text back (the caller decides later whether it is reply text)."""
    text = ""
    tool_calls: list[ToolCallRequested] = []
    try:
        async for event in model.stream(request):
            if isinstance(event, TextDelta):
                text += event.text
                if live:
                    await on_delta(event.text)
            elif isinstance(event, ToolCallRequested):
                tool_calls.append(event)
            elif isinstance(event, TurnDone):
                await note_usage(request.model, event.usage)
    except BaseException:
        # A held-back step that dies (an error, a Stop) still shows what it had said: it was heading
        # for the answer, and the caller keeps what streamed as a cut-short reply.
        if not live and text:
            await on_delta(lead + text)
        raise
    return text, tool_calls


def _max_steps(tool_runner: object, default: int) -> int:
    """C3: a run that used its screen gets ``CU_MAX_MODEL_STEPS`` (``ToolRunner.step_limit``)."""
    limit = getattr(tool_runner, "step_limit", None)
    return limit(default) if callable(limit) else default


async def _run_calls(
    tool_runner: ToolRunner, calls: list[ToolCallRequested], steer: RunSteer | None = None,
) -> tuple[ChatTurn, ...]:
    """One step's tool calls: every ``PARALLEL_TOOLS`` call at once, the
    rest one by one; results go back to the model in call order. After Stop,
    the calls not yet started are not run (``STOP_SKIPPED_TEXT``)."""
    begin = getattr(tool_runner, "begin_step", None)
    if callable(begin):
        begin()   # C3: one screen action per model step
    parallel = tuple(call for call in calls if call.name in PARALLEL_TOOLS)
    results = dict(zip((c.id for c in parallel), await asyncio.gather(*(tool_runner.run(c) for c in parallel))))
    for call in calls:
        if call.id not in results:
            stopped = steer is not None and steer.stopping
            results = {**results, call.id: STOP_SKIPPED_TEXT if stopped else await tool_runner.run(call)}
    return tuple(ChatTurn("tool", results[c.id], tool_call_id=c.id, tool_name=c.name) for c in calls)


async def _stream_or_stop(
    model: Model, request: ModelRequest, on_delta: OnDelta, steer: RunSteer | None, *, live: bool, lead: str,
) -> tuple[str, list[ToolCallRequested]]:
    """``_stream_step``, cut at once by Stop: a streaming step has no side effects, so it never waits."""
    streaming = _stream_step(model, request, on_delta, live=live, lead=lead)
    if steer is None:
        return await streaming
    step = asyncio.ensure_future(streaming)
    stop = asyncio.ensure_future(steer.wait_stop())
    try:
        await asyncio.wait({step, stop}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (step, stop):
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
    if step.cancelled() or not step.done():
        raise RunStopped()
    return step.result()


def _join(
    tool_runner: ToolRunner, added: tuple[ChatTurn, ...], news: tuple[WorkItem, ...],
) -> tuple[ChatTurn, ...]:
    """Your new messages join the run as user turns. A tainted one (a question-book answer can be) taints the
    run, as it would have tainted a run of its own (``_starts_tainted``): steering never launders taint."""
    if any(item.tainted for item in news):
        tool_runner.tainted = True
    return added + tuple(steer_turn(item) for item in news)


async def _boundary(
    steer: RunSteer | None, tool_runner: ToolRunner, added: tuple[ChatTurn, ...], *, answered: bool,
) -> tuple[ChatTurn, ...]:
    """Between steps: Stop ends the run; your new messages join it as user turns, or restart a run that has
    done nothing yet and has not answered yet."""
    if steer is None:
        return added
    if steer.stopping:
        raise RunStopped()
    news = await steer.take()
    if not news:
        return added
    if steer.may_restart() and not answered:
        raise RunRestart(news)
    return _join(tool_runner, added, news)


async def step_loop(
    *, model: Model, request_for: RequestFor, tool_runner: ToolRunner, max_steps: int, deadline_s: float,
    on_delta: OnDelta, steer: RunSteer | None = None, on_progress: OnDelta | None = None,
) -> tuple[str, bool]:
    """Returns ``(reply_text, step_capped)``. Exits early (``step_capped=False``)
    the moment a step produces no tool calls (a natural ``TurnDone``) and no new
    message of yours came meanwhile, or right
    after the step whose calls set ``tool_runner.block`` (Stuck flow R1) or ``tool_runner.parked`` (an Ask card). Is
    capped (``True``) when ``max_steps`` steps all asked for another tool call,
    or ``deadline_s`` passed between steps. With a ``steer`` (steer design), raises ``RunStopped`` after Stop and
    ``RunRestart`` when a message comes before the run did anything. ``on_progress`` (progress lines, owner
    2026-11-01) hears a later step's words that come before its tool calls; they never join the reply."""
    reply_text = ""
    added: tuple[ChatTurn, ...] = ()
    deadline = time.monotonic() + deadline_s

    steps = 0
    answered = False
    while steps < _max_steps(tool_runner, max_steps):
        steps += 1
        if time.monotonic() > deadline:
            return reply_text, True
        if steps > 1:
            added = await _boundary(steer, tool_runner, added, answered=answered)
        elif steer is not None and steer.stopping:
            raise RunStopped()
        first = not added
        request = with_screen(request_for(added), _newest_image(tool_runner))
        step_text, tool_calls = await _stream_or_stop(
            model, request, on_delta, steer, live=first, lead=PARAGRAPH_BREAK if reply_text else "")
        if first:
            reply_text = step_text
        elif step_text and not tool_calls:
            # The final answer: its own paragraph after the first line. Narration
            # in the steps between is activity, not reply text (one "On it:" per run).
            lead = PARAGRAPH_BREAK if reply_text else ""
            reply_text += lead + step_text
            await on_delta(lead + step_text)
        elif step_text and on_progress is not None:
            await on_progress(step_text)   # narration before this step's tool calls: its own chat line
        if step_text:
            added = added + (ChatTurn("assistant", step_text),)
        if not tool_calls:
            # A message that came while the answer streamed: one more step, so the reply covers both. Taken
            # only when a step is left to read it; otherwise it waits in the queue for the next run.
            room = steps < _max_steps(tool_runner, max_steps) and time.monotonic() <= deadline
            news = await steer.take() if steer is not None and room else ()
            if not news:
                return reply_text, False
            answered = True
            added = _join(tool_runner, added, news)
            continue
        added = added + await _run_calls(tool_runner, tool_calls, steer)
        if tool_runner.block is not None or tool_runner.parked is not None:
            # D-A5: a Stuck run ends here, and so does a run that asked (Ask card); TurnRunner leaves the card.
            return reply_text, False
    return reply_text, True
