"""``WatchChecker``: "Only run when the page changes" (owner, 2026-11-04, docs/plans/2026-11-04-roost-routine-watch.md).

The scheduler only queues: when a watching routine's check is due it queues one ``trigger`` work item in the
routine's run-log thread (``queue_check``, at most one waiting per routine). The bot's own drain loop
(``roost/talk/runner.py``) claims it alone, never batched with other work and never counted as a run of the day, so
a check never overlaps the bot's runs, and hands it to ``check``, which calls no model:

1. room first: a sleeping Linux computer wakes only when the keeper has room right now (``wake_if_room``); with no
   room the check is skipped quietly and the next one comes at the next interval;
2. the page opens in the bot's browser (a tab already on that site's front page is reused, any other is loaded
   again), the page settles (``wait_ready``), and its areas and text are read (``roost/desk/page_text.py``);
3. a sign-in or blocked page (``detect_block``) runs the routine as usual once, so the model meets the Sign-in or
   Stuck flow, and stays quiet until the page reads again;
4. the watched part (``watch_part.pick_part``) is normalised and fingerprinted. The first snapshot is the baseline;
   the same fingerprint folds into one quiet "No change" run-log line; a new one queues the routine's run with what
   changed (``RoutineHooks`` tells it, escaped as page content, and the run is tainted).

The computer sleeps again on its own (the keeper's idle pause)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from roost.bots.models import Bot
from roost.bots.store import BotStore
from roost.config import RoostConfig
from roost.constants import WATCH_READY_TIMEOUT_S
from roost.crypto.key_manager import get_user_dek
from roost.desk import Desk, DeskBusy
from roost.desk.ready import wait_ready
from roost.desk.stuck import Block, detect_block
from roost.routines.models import Clock, Routine
from roost.routines.runs import RoutineRunStore, SlotAlreadyRecorded, utc_now
from roost.routines.store import RoutineStore
from roost.routines.watch_models import Watch
from roost.routines.watch_part import AreaText, WatchedPart, changed_lines, fingerprint, normalise, pick_part
from roost.routines.watch_store import Snapshot, WatchStore
from roost.routines.watch_texts import (
    BASELINE_NOTE, BLOCKED_NOTE, CHANGED_NOTE, no_change_note, watch_origin,
)
from roost.work.models import WorkDraft, WorkItem, WorkKind

logger = logging.getLogger(__name__)

CheckResult = Literal["gone", "busy", "no_room", "failed", "blocked", "still_blocked", "baseline", "same", "changed"]


@dataclass(frozen=True)
class PageRead:
    part: WatchedPart | None    # None when the page is a wall
    block: Block | None


def is_watch_batch(items: tuple[WorkItem, ...]) -> bool:
    return bool(items) and all(item.kind is WorkKind.TRIGGER for item in items)


class WatchChecker:
    def __init__(
        self, *, config: RoostConfig, bots: BotStore, routines: RoutineStore, runs: RoutineRunStore,
        snapshots: WatchStore, launcher: Any, turns: Any, desks: Any, hooks: Any = None, clock: Clock = utc_now, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic, ready_timeout_s: float = WATCH_READY_TIMEOUT_S,
    ) -> None:
        self._config = config
        self._bots = bots
        self._routines = routines
        self._runs = runs
        self._snapshots = snapshots
        self._launcher = launcher       # RoutineLauncher: a change queues the routine's normal run
        self._turns = turns             # TurnRunner: its queue and submit
        self._desks = desks
        self._hooks = hooks             # RoutineHooks: tells the web about a run-log line; None: nobody is told
        self._clock = clock
        self._sleep = sleep
        self._monotonic = monotonic
        self._ready_timeout_s = ready_timeout_s

    async def queue_check(self, user_id: str, routine: Routine) -> bool:
        """Queue one check of ``routine``'s page; False when it watches nothing, its bot is gone or off duty, or a
        check already waits."""
        if routine.watch is None:
            return False
        bot = await self._bots.get(user_id, routine.bot_id)
        if bot is None or bot.off_duty:
            return False
        if await self._turns.queue.has_open(user_id, routine.bot_id, routine.thread_id, WorkKind.TRIGGER):
            return False
        await self._turns.submit(user_id, WorkDraft(
            bot_id=routine.bot_id, thread_id=routine.thread_id, kind=WorkKind.TRIGGER,
            origin=watch_origin(routine.name), body=routine.id))
        return True

    async def check(self, user_id: str, bot: Bot, item: WorkItem) -> CheckResult:
        """One check of the routine whose run log ``item`` is in. Never raises for a page that can't be read."""
        routine = await self._routines.for_thread(user_id, item.thread_id)
        if routine is None or routine.watch is None or not routine.enabled:
            return "gone"
        if await self._runs.open_for_routine(user_id, routine.id):
            return "busy"       # the last change's run is still going (or waits on a card)
        desk = self._desks.for_bot(bot.id, bot.computer)
        try:
            read = await self._read(desk, routine.watch)
        except DeskBusy:
            return "no_room"
        except Exception as exc:
            logger.warning("A page watch check failed for routine %s bot %s user %s: %s",
                           routine.id, bot.id, user_id, type(exc).__name__)
            return "failed"
        return await self._decide(user_id, routine, read)

    # --- reading the page ------------------------------------------------------------------------------------

    async def _read(self, desk: Desk, watch: Watch) -> PageRead:
        wake = getattr(desk, "wake_if_room", None)
        if wake is not None and not await wake():
            raise DeskBusy("no free computer for a watch check")
        page = await desk.open_page(watch.url)
        block = detect_block(page)
        if block is not None:
            return PageRead(None, block)
        driver = desk.page()
        if driver is None:
            return PageRead(pick_part(watch.part, (), page.text), None)
        await self._settle(driver)
        areas = tuple([AreaText(a.role, a.name, await driver.area_text(a.node_id) or "")
                       for a in await driver.areas()])
        whole = await driver.area_text(None) or page.text
        return PageRead(pick_part(watch.part, areas, whole), None)

    async def _settle(self, driver: Any) -> None:
        """Bring the tab up and wait for the page to settle; a page that never settles is read anyway."""
        try:
            await driver.geometry()
            await wait_ready(driver, self._ready_timeout_s, clock=self._monotonic, sleep=self._sleep)
        except Exception as exc:
            logger.info("A watched page did not settle: %s", type(exc).__name__)

    # --- deciding --------------------------------------------------------------------------------------------

    async def _decide(self, user_id: str, routine: Routine, read: PageRead) -> CheckResult:
        snap = await self._snapshots.get(user_id, routine.id)
        if read.block is not None or read.part is None:
            return await self._blocked(user_id, routine, snap)
        text = read.part.text
        fp = fingerprint(await get_user_dek(self._config, user_id), routine.id, normalise(text))
        if snap is None or not snap.fingerprint:
            await self._snapshots.save(user_id, routine.id, snapshot=text, fingerprint=fp, changed=False)
            await self._quiet(user_id, routine, None, BASELINE_NOTE)
            return "baseline"
        if fp == snap.fingerprint:
            if snap.blocked:
                await self._snapshots.set_blocked(user_id, routine.id, False)
            else:
                await self._snapshots.checked(user_id, routine.id)
            await self._quiet(user_id, routine, None if snap.blocked else snap, None)
            return "same"
        change = changed_lines(snap.snapshot or "", text)
        run = await self._launch(user_id, routine, CHANGED_NOTE)
        await self._snapshots.save(user_id, routine.id, snapshot=text, fingerprint=fp, changed=True,
                                   change_text=change, change_run_id=run.id if run is not None else None)
        return "changed"

    async def _blocked(self, user_id: str, routine: Routine, snap: Snapshot | None) -> CheckResult:
        """A wall: the routine runs as usual once (the model meets the Sign-in or Stuck flow), then stays quiet."""
        if snap is not None and snap.blocked:
            await self._snapshots.checked(user_id, routine.id)
            return "still_blocked"
        await self._snapshots.set_blocked(user_id, routine.id, True)
        await self._launch(user_id, routine, BLOCKED_NOTE)
        return "blocked"

    async def _launch(self, user_id: str, routine: Routine, note: str):
        now = self._clock().replace(microsecond=0)
        try:
            return await self._launcher.launch(user_id, routine, now, late=False, now=now, note=note)
        except SlotAlreadyRecorded:
            return None

    async def _quiet(self, user_id: str, routine: Routine, snap: Snapshot | None, note: str | None) -> None:
        """One run-log line, no model and no Report. "No change" checks in a row fold into one line that counts."""
        if note is None and snap is not None and snap.quiet_run_id:
            count = snap.quiet_count + 1
            folded = await self._runs.set_state(user_id, snap.quiet_run_id, "done", expected=("done",),
                                                note=no_change_note(count))
            if folded is not None:
                await self._snapshots.fold_quiet(user_id, routine.id, folded.id, count)
                await self._publish(user_id, folded)
                return
        try:
            run = await self._runs.record(user_id, routine, self._clock(), "done", note=note or no_change_note(1))
        except SlotAlreadyRecorded:
            return
        if note is None:
            await self._snapshots.fold_quiet(user_id, routine.id, run.id, 1)
        await self._publish(user_id, run)

    async def _publish(self, user_id: str, run) -> None:
        if self._hooks is not None:
            await self._hooks.publish(user_id, run)


def build_watch_checker(state: Any) -> WatchChecker:
    """The gateway's page watch over ``app.state``, handed to the runner (whose drain loop runs each check)."""
    from roost.routines.launcher import RoutineLauncher

    checker = WatchChecker(
        config=state.config, bots=state.bots, routines=state.routine_store, runs=state.routine_runs,
        snapshots=state.watch_store, launcher=RoutineLauncher(state.talk, state.turns, state.routine_runs, state.events),
        turns=state.turns, desks=state.desks, hooks=state.routine_hooks)
    state.turns.set_watch(checker)
    return checker
