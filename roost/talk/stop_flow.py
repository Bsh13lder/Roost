"""Stop and steer for ``TurnRunner`` (spec §4.2 Stop; docs/plans/2026-10-22-roost-steer.md).

A mixin, so ``roost/talk/runner.py`` stays one readable drain loop. It reads the runner's queue, run log, talk
store, events, drain tasks and its live ``RunSteer`` per bot (``_steers``).

Stop: the bot's run ends at its next boundary (a streaming step is cut at once, a running tool finishes, calls left
in that step are not run). What waits is dropped first, and the work it handed out is stopped first so an
``ask_bot`` wait ends too. A run that has not ended after ``STOP_GRACE_SECONDS`` is cancelled as before, and its
call in flight is reported "Interrupted, outcome unknown". The chat line lists what the run did.

Steer: ``message_status`` says what a message sent now will meet, and ``debounce`` holds a NEW run on your
messages until the newest one is ``debounce_s`` old (quick messages are one turn).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal, Mapping

from roost.bots.models import BotStatus
from roost.constants import (
    FIRST_LINE_ACTIVITY, MAX_HANDOFF_DEPTH, STEER_DEBOUNCE_MAX_SECONDS, STOP_DONE_LINES_MAX, STOP_GRACE_SECONDS,
)
from roost.talk.chat_feel import publish_status
from roost.talk.notices import interrupted_note, post_notice, stop_note
from roost.talk.steer import RunSteer
from roost.voice.calls import CallRegistry
from roost.work.models import DropReport, HandoffResult, WorkItem, WorkKind, WorkState

if TYPE_CHECKING:
    from roost.talk.runner import TurnRunner

MessageStatus = Literal["steered", "queued", "started"]


def _by_thread(items: tuple[WorkItem, ...]) -> tuple[tuple[str, tuple[WorkItem, ...]], ...]:
    thread_ids = tuple(dict.fromkeys(item.thread_id for item in items))
    return tuple((tid, tuple(i for i in items if i.thread_id == tid)) for tid in thread_ids)


def _age_seconds(created_at: str) -> float:
    return (datetime.now(timezone.utc) - datetime.fromisoformat(created_at)).total_seconds()


class StopFlow:
    """``TurnRunner``'s Stop, its handed-out-work cascade and the steer helpers."""

    _steers: Mapping[str, tuple[str, RunSteer]]   # bot id -> (the run's thread id, its steer)
    _stopping: frozenset[str]
    _debounce_s: float
    _gathering: Mapping[str, str]   # bot id -> the chat whose quick messages the debounce is gathering
    _calls: CallRegistry | None     # voice calls: a call turn never waits for the debounce
    _watching: frozenset[str]       # bots reading a watched page (a few seconds, no model): not busy for a message

    def message_status(self: "TurnRunner", bot_id: str, thread_id: str) -> MessageStatus:
        """What a message to ``bot_id`` in ``thread_id`` meets right now: the bot's steerable run for this chat
        reads it mid-work ("steered"), a busy bot runs it next ("queued"), a free bot starts on it."""
        live = self._steers.get(bot_id)
        if live is not None and live[0] == thread_id and live[1].steerable and not live[1].stopping:
            return "steered"
        if self._gathering.get(bot_id) == thread_id:
            return "steered"   # the debounce is gathering this chat's messages into the run about to start
        return "queued" if bot_id in self.busy_ids() and bot_id not in self._watching else "started"

    async def take_messages(
        self: "TurnRunner", user_id: str, bot_id: str, thread_id: str, run_id: str,
    ) -> tuple[WorkItem, ...]:
        """A run's ``RunSteer.take``: your new messages in its chat, claimed under its run id. None while the bot
        is off duty (they wait until you bring it back) or being stopped."""
        bot = await self._bots.get(user_id, bot_id)
        if bot is None or bot.off_duty or bot_id in self._stopping:
            return ()
        return await self._queue.claim_thread_messages(user_id, bot_id, thread_id, run_id)

    async def debounce(self: "TurnRunner", user_id: str, bot_id: str) -> bool:
        """Before a NEW run on your messages: wait until your newest waiting message is ``debounce_s`` old, at
        most ``STEER_DEBOUNCE_MAX_SECONDS`` in all. The bot says On it with words while it waits, and a message
        to that chat meanwhile is "steered" (it joins the run). True when it waited (and so said On it).
        A thread in a voice call never waits: each spoken turn is one message, and every moment counts."""
        first = await self._queue.first_queued(user_id, bot_id) if self._debounce_s > 0 else None
        if first is None or first.kind is not WorkKind.MESSAGE:
            return False
        if self._calls is not None and self._calls.active(first.thread_id):
            return False
        waited = False
        deadline = time.monotonic() + STEER_DEBOUNCE_MAX_SECONDS
        try:
            while (newest := await self._queue.newest_queued_message_at(user_id, bot_id)) is not None:
                left = min(self._debounce_s - _age_seconds(newest), deadline - time.monotonic())
                if left <= 0:
                    break
                if not waited:
                    waited = True
                    self._gathering = {**self._gathering, bot_id: first.thread_id}
                    await self._say_gathering(user_id, bot_id)
                await asyncio.sleep(left)
        finally:
            self._gathering = {k: v for k, v in self._gathering.items() if k != bot_id}
        return waited

    async def _say_gathering(self: "TurnRunner", user_id: str, bot_id: str) -> None:
        """On it with words at once, as a run would (chat feel): the debounce never looks like silence."""
        bot = await self._bots.get(user_id, bot_id)
        if bot is None or bot.off_duty:
            return
        self._activity.set(bot_id, FIRST_LINE_ACTIVITY)
        await publish_status(self._events, self._bots, user_id, bot_id, BotStatus.ON_IT, FIRST_LINE_ACTIVITY)

    async def stop(self: "TurnRunner", user_id: str, bot_id: str) -> DropReport:
        """Spec §4.2 Stop, at the next boundary: drop what waits, stop the work handed out, let the run end
        (or cancel it after the grace), then say what was dropped and what the run did in each thread."""
        live = self._steers.get(bot_id)
        steer = live[1] if live is not None else None
        if steer is not None:
            steer.request_stop()
        self._stopping = self._stopping | {bot_id}
        try:
            waiting = await self._queue.drop_waiting_for_bot(user_id, bot_id)
            running = await self._queue.claimed_for_bot(user_id, bot_id)
            await self._stop_children(user_id, DropReport(dropped=running))
            graceful = await self._await_run_end(bot_id)
            leftover = await self._queue.drop_claimed_for_bot(user_id, bot_id)
        finally:
            self._stopping = self._stopping - {bot_id}
        ended = tuple(replace(i, inflight=None) for i in running) if graceful else ()
        done = steer.done_lines[:STOP_DONE_LINES_MAX] if steer is not None else ()
        report = DropReport(dropped=(*ended, *waiting.dropped, *leftover.dropped), done=done)
        self._resolve(tuple(i.id for i in report.dropped), HandoffResult(status="dropped"))
        await self._close_dropped(user_id, report)
        await self._settle_status(user_id, bot_id)
        if await self._queue.first_queued(user_id, bot_id) is not None:
            await self.kick(user_id, bot_id)   # a message sent while it was stopping still runs
        return report

    async def _await_run_end(self: "TurnRunner", bot_id: str) -> bool:
        """True when the drain task ended by itself within the grace (no task: nothing to wait for)."""
        task = self._tasks.get(bot_id)
        if task is None or task.done():
            return True
        done, _ = await asyncio.wait({task}, timeout=STOP_GRACE_SECONDS)
        if done:
            return True
        await self._cancel_task(bot_id)
        return False

    async def _stop_children(self: "TurnRunner", user_id: str, parents: DropReport, depth: int = 0) -> None:
        """D-C: "Stopping the asker stops the work it handed out" — down the
        whole chain. Other work the targets had claimed goes back to queued."""
        children = await self._queue.children_of(user_id, tuple(i.id for i in parents.running))
        if not children or depth >= MAX_HANDOFF_DEPTH:
            return
        busy = tuple(dict.fromkeys(c.bot_id for c in children if c.state is WorkState.CLAIMED))
        for bot_id in busy:
            await self._cancel_task(bot_id)
        report = await self._queue.drop_items(user_id, tuple(c.id for c in children))
        self._resolve(tuple(i.id for i in report.dropped), HandoffResult(status="dropped"))
        await self._close_dropped(user_id, report)
        await self._stop_children(user_id, report, depth + 1)
        for bot_id in busy:
            await self._queue.requeue_claimed(user_id, bot_id)
            await self._settle_status(user_id, bot_id)
            await self.kick(user_id, bot_id)

    async def _close_dropped(self: "TurnRunner", user_id: str, report: DropReport) -> None:
        for run_id in report.run_ids:
            await self._runs.finish(user_id, run_id, "stopped")
        running = {i.thread_id for i in report.running}
        for thread_id, items in _by_thread(report.dropped):
            done = report.done if thread_id in running else ()
            await post_notice(self._talk, self._events, user_id, thread_id, stop_note(items, done), kind="dropped")
        for item in report.interrupted:
            await post_notice(self._talk, self._events, user_id, item.thread_id,
                              interrupted_note(item.inflight or ""), kind="interrupted")
