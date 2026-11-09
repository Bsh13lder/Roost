"""A voice call's runs through ``TurnRunner`` (docs/plans/2026-10-30-roost-voice.md §3, contract A's effects): no
steer debounce before a call turn, the voice section and the call model in a spoken run of the user's own message,
neither in a handoff, and the memory capture after a call turn left to a background task."""

from __future__ import annotations

import asyncio

import pytest

from roost.bots.status import ActivityBoard
from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.llm.registry import CALL_MODEL, DEFAULT_BOT_MODEL
from roost.llm.scripted import ScriptedModel
from roost.talk.chat_feel import FIRST_LINE_RULE
from roost.talk.runner import TurnRunner
from roost.voice.calls import CallRegistry
from roost.voice.prompt import voice_section
from roost.work.models import WorkDraft, WorkKind
from team_helpers import Rig, RecordingModel, make_bot, make_rig, send, wait_idle

_DEBOUNCE_S = 1.5


class HeldMemory:
    """Stands in for ``MemoryHooks``: ``after_run`` waits until the test lets it go."""

    summaries = None

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.runs = 0

    async def prompt_section(self, user_id: str, bot_id: str, newest_text: str):
        return None

    async def after_run(self, run) -> None:
        self.runs += 1
        await self.release.wait()


@pytest.fixture
async def world():
    cfg = load_config()
    await init_db(cfg)
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Scout")
    return cfg, user.id, bot


def _rig(cfg, calls: CallRegistry, memory=None) -> Rig:
    base = make_rig(cfg, RecordingModel(ScriptedModel()))
    runner = TurnRunner(cfg, base.bots, base.talk, base.events, base.desks, base.model, ActivityBoard(),
                        debounce_s=_DEBOUNCE_S, calls=calls, memory=memory)
    return Rig(runner=runner, bots=base.bots, talk=base.talk, events=base.events, desks=base.desks, model=base.model)


async def test_a_call_turn_starts_at_once_and_speaks_with_the_call_model(world):
    cfg, user_id, bot = world
    calls = CallRegistry()
    rig = _rig(cfg, calls)
    thread = await rig.talk.create_thread(user_id, bot.id)
    calls.beat(user_id, thread.id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "what time is it")
    await wait_idle(rig.runner, timeout=1.0)   # well under the debounce: the call skipped it
    request = rig.model.requests[0]
    assert request.model == CALL_MODEL
    assert voice_section() in request.system and FIRST_LINE_RULE not in request.system


async def test_a_typed_turn_still_waits_for_the_debounce_and_keeps_the_chat_rules(world):
    cfg, user_id, bot = world
    rig = _rig(cfg, CallRegistry())
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "what time is it")
    await asyncio.sleep(0.4)
    assert rig.model.requests == [] and rig.runner.message_status(bot.id, thread.id) == "steered"
    await wait_idle(rig.runner)
    request = rig.model.requests[0]
    assert request.model == DEFAULT_BOT_MODEL
    assert voice_section() not in request.system and FIRST_LINE_RULE in request.system


async def test_a_handoff_in_a_call_thread_is_not_spoken(world):
    cfg, user_id, bot = world
    calls = CallRegistry()
    rig = _rig(cfg, calls)
    thread = await rig.talk.create_thread(user_id, bot.id)
    calls.beat(user_id, thread.id, bot.id)
    await rig.runner.submit(user_id, WorkDraft(bot_id=bot.id, thread_id=thread.id, kind=WorkKind.HANDOFF,
                                               origin="from Chief", body="look this up"))
    await wait_idle(rig.runner)
    request = rig.model.requests[0]
    assert request.model == DEFAULT_BOT_MODEL and voice_section() not in request.system


async def test_memory_capture_after_a_call_turn_does_not_hold_the_bot(world):
    cfg, user_id, bot = world
    calls = CallRegistry()
    memory = HeldMemory()
    rig = _rig(cfg, calls, memory=memory)
    thread = await rig.talk.create_thread(user_id, bot.id)
    calls.beat(user_id, thread.id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "remember I like trains")
    await wait_idle(rig.runner, timeout=1.0)   # the run is over while the capture still waits
    assert memory.runs == 1 and rig.runner._background.pending == 1
    await send(rig, user_id, bot.id, thread.id, "and planes")   # the next turn is not blocked by it
    await wait_idle(rig.runner, timeout=1.0)
    assert len(rig.model.requests) == 2
    memory.release.set()
    await rig.runner._background.wait_idle()
    assert rig.runner._background.pending == 0


async def test_memory_capture_after_a_typed_turn_is_still_awaited(world):
    cfg, user_id, bot = world
    memory = HeldMemory()
    rig = _rig(cfg, CallRegistry(), memory=memory)
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "hello")
    with pytest.raises(TimeoutError):
        await wait_idle(rig.runner, timeout=_DEBOUNCE_S + 0.5)
    assert memory.runs == 1 and rig.runner._background.pending == 0
    memory.release.set()
    await wait_idle(rig.runner)
