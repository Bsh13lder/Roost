"""Helpers shared by the work-queue, handoff and room tests (not a test module).

``tests/`` has no ``__init__.py``, so pytest's default import mode puts it
on ``sys.path`` and test modules import this file as ``team_helpers``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable

from roost.approvals.models import BotApproval
from roost.bots.models import Avatar, Bot, BotDraft, BotPatch
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.desk import DeskFactory
from roost.events.hub import EventHub, Subscription
from roost.llm.types import TextDelta, TurnDone
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from roost.work.models import ORIGIN_YOU, WorkDraft, WorkItem, WorkKind

AVATAR = Avatar("round", "#22c55e", "none")


# The approval these tests were written for: Ask every time, no auto-review (new bots now start in Auto-edit with
# auto-review on, owner 2026-11-03; tests of that default build their bots through the store or the route).
TEST_APPROVAL = BotApproval("ask", frozenset())


async def make_bot(cfg, user_id: str, name: str, job: str = "helps out") -> Bot:
    """A bot on the Mac Brave desk, which these team tests fake (new bots default to the Linux computer)."""
    store = BotStore(cfg)
    bot = await store.create(user_id, BotDraft(name=name, job=job, instructions="", avatar=AVATAR))
    await store.set_approval(user_id, bot.id, TEST_APPROVAL, auto_review=False)
    updated = await store.update(user_id, bot.id, BotPatch(computer="mac_brave"))
    assert updated is not None
    return updated


@dataclass(frozen=True)
class Rig:
    runner: TurnRunner
    bots: BotStore
    talk: TalkStore
    events: EventHub
    desks: DeskFactory
    model: Any


def make_rig(cfg, model) -> Rig:
    bots, talk, events, desks = BotStore(cfg), TalkStore(cfg), EventHub(cfg), DeskFactory(cfg)
    runner = TurnRunner(cfg, bots, talk, events, desks, model, ActivityBoard())
    return Rig(runner=runner, bots=bots, talk=talk, events=events, desks=desks, model=model)


async def send(rig: Rig, user_id: str, bot_id: str, thread_id: str, text: str) -> WorkItem:
    """What ``POST /api/threads/{id}/messages`` does: store the message, queue it."""
    message = await rig.talk.add_message(user_id, thread_id, "user", text)
    return await rig.runner.submit(user_id, WorkDraft(
        bot_id=bot_id, thread_id=thread_id, kind=WorkKind.MESSAGE,
        origin=ORIGIN_YOU, body=text, message_id=message.id,
    ))


async def until(predicate: Callable[[], bool], timeout: float = 3.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


def _busy(runner: TurnRunner) -> list["asyncio.Task[None]"]:
    """Drain loops still running, and settles still waiting to finish after one (stuck flow R9)."""
    return [task for task in (*runner._tasks.values(), *runner._settling) if not task.done()]


async def wait_idle(runner: TurnRunner, timeout: float = 5.0) -> None:
    """Wait until no bot has a drain loop running (a handoff can start new ones)
    and no ``TurnRunner.settle`` still waits to finish after one."""
    async with asyncio.timeout(timeout):
        while True:
            running = _busy(runner)
            if not running:
                await asyncio.sleep(0)     # a drain loop that just ended may still have a settle to start
                running = _busy(runner)
            if not running:
                return
            await asyncio.wait(running, timeout=0.05)


async def frames_so_far(subscription: Subscription) -> list[dict]:
    frames: list[dict] = []
    while True:
        try:
            frames.append(await asyncio.wait_for(subscription.__anext__(), timeout=0.2))
        except TimeoutError:
            return frames


class GatedModel:
    """Answers with ``replies`` in call order; calls numbered in ``hold``
    (1-based) wait until ``release`` is set."""

    def __init__(self, replies, hold=(1,)):
        self.replies = tuple(replies)
        self.hold = frozenset(hold)
        self.release = asyncio.Event()
        self.requests: list = []

    async def stream(self, request):
        self.requests.append(request)
        call_number = len(self.requests)
        if call_number in self.hold:
            await self.release.wait()
        yield TextDelta(self.replies[call_number - 1])
        yield TurnDone("end_turn")


class BarrierModel:
    """Wraps ``inner``; calls for the bots named in ``gated`` all wait until
    every one of them has started — they can only finish if they run at
    the same time (a sequential run times out after 2 s and fails)."""

    def __init__(self, inner, gated: frozenset[str]):
        self._inner = inner
        self._gated = gated
        self._barrier = asyncio.Barrier(len(gated))

    async def stream(self, request):
        if request.agent in self._gated:
            await asyncio.wait_for(self._barrier.wait(), timeout=2)
        async for event in self._inner.stream(request):
            yield event


class StartTogetherModel:
    """Like ``BarrierModel``, but only each gated bot's FIRST call waits:
    the runs start together, then go on freely (later steps never block)."""

    def __init__(self, inner, gated: frozenset[str]):
        self._inner = inner
        self._waiting = gated
        self._barrier = asyncio.Barrier(len(gated))

    async def stream(self, request):
        if request.agent in self._waiting:
            self._waiting = self._waiting - {request.agent}
            await asyncio.wait_for(self._barrier.wait(), timeout=2)
        async for event in self._inner.stream(request):
            yield event


class HoldFirstCallModel:
    """Wraps ``inner``; ``agent``'s very first ``stream()`` call waits for
    ``release`` before the inner model answers it, setting ``held`` as
    soon as it starts waiting -- simulates a bot that is busy answering
    one chat when more work (e.g. a room post) arrives for it elsewhere."""

    def __init__(self, inner, agent: str):
        self._inner = inner
        self._waiting = frozenset({agent})
        self.held = asyncio.Event()
        self.release = asyncio.Event()

    async def stream(self, request):
        if request.agent in self._waiting:
            self._waiting = self._waiting - {request.agent}
            self.held.set()
            await self.release.wait()
        async for event in self._inner.stream(request):
            yield event


def ask(call_id: str, bot: str, task: str):
    from roost.llm.types import ToolCallRequested
    return ToolCallRequested(id=call_id, name="ask_bot", arguments={"bot": bot, "task": task})


def say(text: str):
    return [TextDelta(text), TurnDone("end_turn")]


class RecordingModel:
    """Wraps ``inner`` and keeps every ``ModelRequest`` it was asked to stream."""

    def __init__(self, inner):
        self._inner = inner
        self.requests: list = []

    async def stream(self, request):
        self.requests.append(request)
        async for event in self._inner.stream(request):
            yield event


def team_model(scripts) -> RecordingModel:
    from roost.llm.scripted_team import ScriptedTeamModel
    return RecordingModel(ScriptedTeamModel(scripts))


def make_room_service(rig: Rig, cfg):
    from roost.rooms.service import RoomService
    from roost.rooms.store import RoomStore
    return RoomService(rig.bots, rig.talk, RoomStore(cfg), rig.runner)
