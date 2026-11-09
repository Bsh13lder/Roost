"""On it goes out with words, with the placeholder, before anything loads (plan Task 1)."""

from __future__ import annotations

import asyncio

import pytest

from roost.constants import FIRST_LINE_ACTIVITY
from roost.llm.types import TextDelta, TurnDone
from roost.memory.hooks import MemoryHooks  # noqa: F401 — the real type this fake stands in for
from test_turn import AVATAR, _drain, _runner, bot_id, cfg, user_id  # noqa: F401


class _SlowMemory:
    """A memory hook whose prompt section waits on an event the test controls."""

    summaries = None

    def __init__(self) -> None:
        self.gate = asyncio.Event()
        self.entered = asyncio.Event()

    async def prompt_section(self, user_id, bot_id, text):
        self.entered.set()
        await self.gate.wait()
        return None

    async def after_run(self, run):
        return None


async def test_on_it_with_words_goes_out_before_history_and_memory_load(cfg, user_id, bot_id):
    runner, bots, talk, events, desks, model = _runner(cfg, script=[[TextDelta("ok"), TurnDone("end_turn")]])
    memory = _SlowMemory()
    runner._memory = memory
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "hello")

    sub = events.subscribe(user_id)
    task = asyncio.create_task(runner.run_turn(user_id, bot_id, thread.id))
    await asyncio.wait_for(memory.entered.wait(), timeout=2)
    frames = await _drain(sub, 2)  # published while memory is still loading
    assert frames[0]["type"] == "bot_status"
    assert frames[0]["status"] == "on_it"
    assert frames[0]["activity"] == FIRST_LINE_ACTIVITY
    assert frames[1]["type"] == "message"
    assert frames[1]["message"]["body"] == ""
    assert not task.done()
    memory.gate.set()
    await asyncio.wait_for(task, timeout=5)
    sub.close()


async def test_the_placeholder_closes_when_loading_fails(cfg, user_id, bot_id, monkeypatch):
    runner, bots, talk, events, desks, model = _runner(cfg, script=[])
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "hello")

    async def boom(*args, **kwargs):
        raise RuntimeError("history is broken")

    monkeypatch.setattr(talk, "list_latest_messages", boom)
    sub = events.subscribe(user_id)
    await runner.run_turn(user_id, bot_id, thread.id)
    frames = []
    while True:
        try:
            frames.append(await asyncio.wait_for(sub.__anext__(), timeout=0.5))
        except (asyncio.TimeoutError, StopAsyncIteration):
            break
    sub.close()
    types = [f["type"] for f in frames]
    placeholder = next(f["message"]["id"] for f in frames if f["type"] == "message")
    done_at = next(i for i, f in enumerate(frames) if f["type"] == "message_done" and f["message_id"] == placeholder)
    notice_at = max(i for i, f in enumerate(frames) if f["type"] == "message")
    assert "message_done" in types
    assert done_at < notice_at


async def test_streamed_text_still_replaces_the_placeholder(cfg, user_id, bot_id):
    runner, bots, talk, events, desks, model = _runner(
        cfg, script=[[TextDelta("Hi "), TextDelta("there"), TurnDone("end_turn")]],
    )
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "hello")
    sub = events.subscribe(user_id)
    await runner.run_turn(user_id, bot_id, thread.id)
    frames = await _drain(sub, 7)
    sub.close()
    assert [f["type"] for f in frames] == [
        "bot_status", "message", "text_delta", "text_delta", "message", "message_done", "bot_status",
    ]
    assert frames[1]["message"]["body"] == ""
    assert frames[4]["message"]["body"] == "Hi there"
    assert frames[4]["message"]["id"] == frames[1]["message"]["id"]
