"""``RoutineScheduler``: the one loop that starts routine runs when their slot comes.

One scheduler per gateway (``start.py``). Each tick lists the users, then per user fires the due routines and
reconciles the run log. Limits that keep it cheap and safe:

- a tick is cut after ``SCHEDULER_TICK_TIMEOUT_SECONDS`` and the next one starts fresh;
- a tick fires at most ``ROUTINE_TICK_MAX_FIRES`` routines across all users, the rest wait for the next tick;
- every slot is claimed by a compare-and-swap on ``next_run_at`` (and the run table's unique index is the second
  lock), so two ticks never fire one slot;
- sleeping through n slots gives one ``missed`` row and one run, and ``next_run_at`` moves to the next slot after
  now, so a backlog never builds;
- one routine's or one user's failure is logged (ids and the exception's type name only) and never stops the rest.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace
from datetime import datetime, timedelta

from roost.bots.models import Bot
from roost.bots.store import BotStore
from roost.config import RoostConfig
from roost.constants import (
    ROUTINE_LATE_GRACE_SECONDS,
    RECONCILE_GRACE_SECONDS,
    ROUTINE_SLOT_LOOKBACK_HOURS,
    ROUTINE_SLOT_SCAN_MAX,
    ROUTINE_TICK_MAX_FIRES,
    ROUTINE_TICK_SECONDS,
    SCHEDULER_TICK_TIMEOUT_SECONDS,
)
from roost.db.connection import db_session
from roost.routines.hooks import RoutineHooks
from roost.routines.launcher import RoutineLauncher
from roost.routines.models import Clock, Job, Routine, RoutineRun
from roost.routines.runs import RoutineRunStore, SlotAlreadyRecorded, parse_iso
from roost.routines.schedule import jitter_seconds, next_after, slot_for, slots_between
from roost.routines.store import RoutineStore
from roost.routines.system_reports import madrid_words
from roost.routines.watch import WatchChecker
from roost.routines.watch_models import next_check
from roost.routines.texts import (
    OFF_DUTY_NOTE, STILL_GOING, STILL_WAITING, STOPPED_NOTE, UNFINISHED_TEXT, missed_note, overlap_note,
    paused_for_cap, paused_for_reserve,
)
from roost.work.models import WorkState
from roost.work.queue import WorkQueue
from roost.work.runs import madrid_today, seconds_until_madrid_midnight
from roost.talk.limits import LimitState
from roost.timezones import zone_city

logger = logging.getLogger(__name__)
_ONE_SECOND = timedelta(seconds=1)

WaitingCheck = Callable[[str, str], Awaitable[bool]]


class _Turns:
    """What the scheduler needs from the runner (a protocol in spirit; the runner and test fakes provide it)."""

    queue: WorkQueue

    async def limit_state(self, user_id: str, bot: Bot) -> LimitState: ...


class RoutineScheduler:
    def __init__(
        self, config: RoostConfig, *, clock: Clock, launcher: RoutineLauncher, runs: RoutineRunStore,
        routines: RoutineStore, turns: _Turns, bots: BotStore, usage=None, jobs: Sequence[Job] = (),
        waiting: WaitingCheck | None = None, hooks: RoutineHooks | None = None, watch: WatchChecker | None = None,
    ) -> None:
        self._watch = watch     # None: a watching routine's checks are planned but never queued
        self._config = config
        self._clock = clock
        self._launcher = launcher
        self._runs = runs
        self._routines = routines
        self._turns = turns
        self._bots = bots
        self._usage = usage
        self._jobs = jobs
        self._waiting = waiting
        self._hooks = hooks
        self._paused_noticed: dict[str, str] = {}   # bot id -> the local day its paused Report was posted
        self._overlap_noticed: dict[str, str] = {}  # routine id -> the local day its overlap note was posted

    async def loop(self) -> None:
        while True:
            await self.tick()
            await asyncio.sleep(self._config.scheduler_tick_seconds or ROUTINE_TICK_SECONDS)

    async def tick(self) -> None:
        """One pass over every user. Never raises (a cancel still passes through)."""
        remaining = ROUTINE_TICK_MAX_FIRES
        try:
            async with asyncio.timeout(SCHEDULER_TICK_TIMEOUT_SECONDS):
                for user_id in await self._user_ids():
                    remaining -= await self._tick_user(user_id, remaining)
        except TimeoutError:
            logger.warning("Routine tick cut after %ss", SCHEDULER_TICK_TIMEOUT_SECONDS)
        except Exception as exc:
            logger.warning("Routine tick failed: %s", type(exc).__name__)

    async def _tick_user(self, user_id: str, remaining: int) -> int:
        fired = 0
        try:
            if self._hooks is not None:
                await self._hooks.sweep_asks(user_id, self._clock())   # a card past its deadline is a no
            fired = await self._fire_due(user_id, remaining)
            await self._reconcile(user_id)
            await self._run_jobs(user_id)
        except Exception as exc:
            logger.warning("Routine tick failed for user %s: %s", user_id, type(exc).__name__)
        return fired

    async def _run_jobs(self, user_id: str) -> None:
        """The no-model jobs (reminders; the day summary seeds nothing). One job's failure stops no other."""
        for job in self._jobs:
            try:
                await job.run(user_id, self._clock())
            except Exception as exc:
                logger.warning("Job %s failed for user %s: %s", job.name, user_id, type(exc).__name__)

    async def _run_builtin(self, routine: Routine, slot: datetime) -> None:
        """A built-in routine runs no model: the job that owns its name posts its Report and records the slot."""
        for job in self._jobs:
            if job.builtin == routine.builtin:
                await job.fire(routine.user_id, routine, slot)
                return
        logger.warning("Routine %s (user %s) names a built-in nobody runs", routine.id, routine.user_id)

    async def _user_ids(self) -> tuple[str, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute("SELECT id FROM users ORDER BY rowid")).fetchall()
        return tuple(row["id"] for row in rows)

    async def _fire_due(self, user_id: str, remaining: int) -> int:
        """Fire this user's due routines, oldest first, at most ``remaining``. Returns how many were handled."""
        if remaining <= 0:
            return 0
        now = self._clock()
        handled = 0
        for routine in await self._routines.due(user_id, now, limit=remaining):
            handled += 1
            try:
                await self._fire_one(routine, now)
            except Exception as exc:
                logger.warning("Routine %s (bot %s, user %s) failed to fire: %s",
                               routine.id, routine.bot_id, user_id, type(exc).__name__)
        return handled

    def _due_slots(self, routine: Routine, now: datetime) -> tuple[datetime, ...]:
        """The slots that have come: from the one ``next_run_at`` was planned for (never further back than the
        lookback window) up to now, oldest first."""
        first = slot_for(routine.next_run_at, routine.schedule)
        floor = now - timedelta(hours=ROUTINE_SLOT_LOOKBACK_HOURS)
        after = max(first - _ONE_SECOND, floor)
        return slots_between(routine.schedule, after, now, ROUTINE_SLOT_SCAN_MAX)

    async def _fire_one(self, routine: Routine, now: datetime) -> None:
        if routine.watch is not None:
            await self._fire_watch(routine, now)
            return
        slots = self._due_slots(routine, now)
        # The next slot is planned from now, so a backlog collapses into this one fire.
        following = next_after(routine.schedule, now)
        new_next = following + timedelta(seconds=jitter_seconds(routine.id, following))
        if not await self._routines.claim_slot(routine.user_id, routine.id, routine.next_run_at, new_next, now):
            return   # another tick took this slot
        if routine.builtin is not None:
            await self._run_builtin(routine, slots[-1] if slots else now)
            return
        if not slots:
            return
        await self._decide(routine, slots, now)

    async def _fire_watch(self, routine: Routine, now: datetime) -> None:
        """A watching routine: claim its check (the next one ``every_min`` from now, so a sleep never builds a
        backlog) and queue it. The check reads the page with no model and starts a run only on a change."""
        assert routine.watch is not None
        claimed = await self._routines.claim_slot(
            routine.user_id, routine.id, routine.next_run_at, next_check(routine.watch, now), now)
        if claimed and self._watch is not None:
            await self._watch.queue_check(routine.user_id, routine)

    async def _decide(self, routine: Routine, slots: tuple[datetime, ...], now: datetime) -> None:
        newest = slots[-1]
        bot = await self._bots.get(routine.user_id, routine.bot_id)
        if bot is None:
            return
        if bot.off_duty:
            await self._record(routine, newest, "skipped", note=OFF_DUTY_NOTE)
            return
        if await self._runs.open_for_routine(routine.user_id, routine.id):
            await self._skip_overlap(routine, newest)
            return
        limit = await self._turns.limit_state(routine.user_id, bot)
        if limit.in_reserve or limit.capped:
            await self._hold(routine, newest, limit, now)
            return
        await self._launch(routine, slots, now)

    async def _skip_overlap(self, routine: Routine, slot: datetime) -> None:
        """The last run is still going (note it in the log) or parked on a card for you (say so in a Report)."""
        parked = await self._parked(routine)
        run = await self._record(routine, slot, "skipped", note=STILL_WAITING if parked else STILL_GOING)
        if run is not None and parked:
            await self._report(routine, run, "skipped", STILL_WAITING)
        elif run is not None:
            await self._note_overlap(routine)

    async def _parked(self, routine: Routine) -> bool:
        """True when an open run of this routine is waiting on one of its own Ask cards (else the bot-wide check)."""
        if self._hooks is not None:
            for run in await self._runs.open_for_routine(routine.user_id, routine.id):
                if await self._hooks.parked_on_card(routine.user_id, run):
                    return True
            return False
        return self._waiting is not None and await self._waiting(routine.user_id, routine.bot_id)

    async def _note_overlap(self, routine: Routine) -> None:
        """R1: one quiet note the first time a routine's slot is skipped on a local day, not on every skip."""
        today = madrid_today(self._clock())
        if self._hooks is None or self._overlap_noticed.get(routine.id) == today:
            return
        self._overlap_noticed = {**self._overlap_noticed, routine.id: today}
        try:
            await self._hooks.overlap_note(routine.user_id, routine, overlap_note(routine.name))
        except Exception as exc:
            logger.warning("Posting an overlap note failed for routine %s user %s: %s",
                           routine.id, routine.user_id, type(exc).__name__)

    async def _hold(self, routine: Routine, slot: datetime, limit: LimitState, now: datetime) -> None:
        """Held: inside the usage reserve (one Report per reset window) or at the daily cap (one per local day)."""
        run = await self._record(routine, slot, "held")
        if run is None:
            return
        window, text = _pause(limit, now)
        if self._paused_noticed.get(routine.bot_id) == window:
            return
        self._paused_noticed = {**self._paused_noticed, routine.bot_id: window}
        await self._report(routine, run, "held", text)

    async def _launch(self, routine: Routine, slots: tuple[datetime, ...], now: datetime) -> None:
        cutoff = now - timedelta(seconds=ROUTINE_LATE_GRACE_SECONDS)
        missed = tuple(s for s in slots if s < cutoff)
        newest = slots[-1]
        if missed:
            note = missed_note(len(missed), missed[0], missed[-1])
            run = await self._record(routine, missed[0], "missed", missed_count=len(missed), note=note)
            if run is not None:
                await self._report(routine, run, "missed", note)
        try:
            run = await self._launcher.launch(routine.user_id, routine, newest, late=newest < cutoff, now=now)
        except SlotAlreadyRecorded:
            return
        except Exception as exc:
            logger.warning("Routine %s (bot %s, user %s) could not start: %s",
                           routine.id, routine.bot_id, routine.user_id, type(exc).__name__)
            failed = await self._record(routine, newest, "error")
            if failed is not None:
                await self._report(routine, failed, "error", UNFINISHED_TEXT)
            return
        await self._publish(routine.user_id, run)

    async def _record(
        self, routine: Routine, slot: datetime, state, *, note: str | None = None, missed_count: int = 0,
    ) -> RoutineRun | None:
        try:
            run = await self._runs.record(routine.user_id, routine, slot, state, note=note, missed_count=missed_count)
        except SlotAlreadyRecorded:
            return None
        await self._publish(routine.user_id, run)
        return run

    async def _publish(self, user_id: str, run: RoutineRun) -> None:
        if self._hooks is not None:
            await self._hooks.publish(user_id, run)

    async def _report(self, routine: Routine, run: RoutineRun, kind: str, text: str) -> None:
        if self._hooks is not None:
            await self._hooks.report_slot(routine.user_id, routine, run, kind, text)

    async def _reconcile(self, user_id: str) -> None:
        """Close run rows the after-run pass never reached: a Stop or Retire dropped their item (skipped, "Stopped"),
        or the item finished but the process died before the Report (error). A claimed item moves its row to
        ``running``. A just-finished item is given a moment, because its after-run pass is about to close it."""
        if self._hooks is None:
            return
        now = self._clock()
        for run in await self._runs.open_runs(user_id):
            try:
                await self._reconcile_one(user_id, run, now)
            except Exception as exc:
                logger.warning("Reconciling routine run %s (user %s) failed: %s", run.id, user_id, type(exc).__name__)

    async def _reconcile_one(self, user_id: str, run: RoutineRun, now: datetime) -> None:
        item = await self._turns.queue.get(user_id, run.work_item_id) if run.work_item_id else None
        if item is None or item.state is WorkState.DROPPED:
            await self._hooks.finish(user_id, run, "skipped", note=STOPPED_NOTE)
        elif item.state is WorkState.CLAIMED and run.state == "queued":
            await self._runs.set_state(user_id, run.id, "running", expected=("queued",))
            await self._hooks.publish(user_id, replace(run, state="running"))
        elif item.state is WorkState.DONE and now - parse_iso(item.updated_at) > timedelta(
                seconds=RECONCILE_GRACE_SECONDS):
            if await self._hooks.parked_on_card(user_id, run):
                return    # waiting for you on an Ask card, not lost
            await self._hooks.finish(user_id, run, "error", note=UNFINISHED_TEXT)


def _pause(limit: LimitState, now: datetime) -> tuple[str, str]:
    """The window a paused Report is said once for, and its text."""
    if limit.in_reserve:
        reset = limit.reading.resets_at if limit.reading is not None and limit.reading.resets_at else None
        if reset is None:
            reset = now + timedelta(seconds=seconds_until_madrid_midnight(now))
        return f"reserve {reset.isoformat()}", paused_for_reserve(f"{madrid_words(reset)} {zone_city()} time")
    return f"cap {madrid_today(now)}", paused_for_cap(limit.cap)
