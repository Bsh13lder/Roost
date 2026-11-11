"""``WatchFailures``: what happens when a page watch's check can't read the page (owner, 2026-11-10,
docs/plans/2026-11-10-roost-self-healing.md). Before this a failed check logged a warning and returned "failed":
bot 1016fb46's watch said nothing for half an hour while its tab was frozen.

- Failures in a row fold into one run-log row (state ``error``, "Couldn't check: the computer didn't answer · 3
  times"), like the "No change" fold: never a row per failure. A skip for room stays quiet once; from the second in
  a row it is the same kind of line.
- The routine keeps its last error (``routines.last_error_kind``, ``last_error_at``, v47) for the History.
- At ``WATCH_FAILS_STUCK`` in a row the bot's main chat gets one quiet line saying what it can't check and why.
- A check that reads the page clears all of it (the store's ``_CLEAR_FAILS`` and ``clear``)."""

from __future__ import annotations

import logging
from typing import Any

from roost.constants import ROUTINE_ERROR_NO_ROOM, WATCH_FAILS_STUCK, WATCH_NO_ROOM_NOTE_AFTER
from roost.routines.models import Clock, Routine, RoutineRun
from roost.routines.runs import RoutineRunStore, SlotAlreadyRecorded
from roost.routines.store import RoutineStore
from roost.routines.watch_store import Snapshot, WatchStore
from roost.routines.watch_texts import couldnt_check_note

logger = logging.getLogger(__name__)


class WatchFailures:
    def __init__(
        self, *, runs: RoutineRunStore, snapshots: WatchStore, routines: RoutineStore, hooks: Any, clock: Clock,
    ) -> None:
        self._runs = runs
        self._snapshots = snapshots
        self._routines = routines
        self._hooks = hooks         # RoutineHooks: the chat line and the run-log event; None: nobody is told
        self._clock = clock

    async def note(self, user_id: str, routine: Routine, kind: str) -> None:
        """One more check that could not read the page, for the reason ``kind`` (a ROUTINE_ERROR_* word)."""
        snap = await self._snapshots.get(user_id, routine.id)
        count = (snap.fail_count if snap is not None else 0) + 1
        await self._routines.set_last_error(user_id, routine.id, kind, self._clock())
        if kind == ROUTINE_ERROR_NO_ROOM and count < WATCH_NO_ROOM_NOTE_AFTER:
            await self._snapshots.note_fail(user_id, routine.id, snap.fail_run_id if snap else None, count)
            return
        run = await self._fold(user_id, routine, snap, kind, count)
        kept_run_id = run.id if run is not None else (snap.fail_run_id if snap else None)
        await self._snapshots.note_fail(user_id, routine.id, kept_run_id, count)
        if run is not None and self._hooks is not None:
            await self._hooks.publish(user_id, run)
        if count == WATCH_FAILS_STUCK and self._hooks is not None:
            await self._hooks.watch_failing(user_id, routine, kind)

    async def clear(self, user_id: str, routine: Routine) -> None:
        """A check read the page: the routine's last error goes (the snapshot's own count goes with its write)."""
        if routine.last_error_kind is not None:
            await self._routines.set_last_error(user_id, routine.id, None, None)

    async def _fold(
        self, user_id: str, routine: Routine, snap: Snapshot | None, kind: str, count: int,
    ) -> RoutineRun | None:
        """The run-log row these failures fold into: the open fold's row with its count raised, else a new one."""
        note = couldnt_check_note(kind, count)
        if snap is not None and snap.fail_run_id:
            folded = await self._runs.set_state(user_id, snap.fail_run_id, "error", expected=("error",), note=note)
            if folded is not None:
                return folded
        try:
            return await self._runs.record(user_id, routine, self._clock(), "error", note=note)
        except SlotAlreadyRecorded:
            logger.info("A failed watch check of routine %s had its slot recorded already", routine.id)
            return None
