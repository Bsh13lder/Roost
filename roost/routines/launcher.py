"""``RoutineLauncher``: start one routine run.

A work item's body never reaches the model, so the launcher first posts the routine's instructions as a
``routine`` message in the routine's run-log thread (with the slot line), then queues one ``ROUTINE`` item. The
run row is written first, under the item's id, so the after-run pass always finds it."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from roost.events.hub import EventHub
from roost.routines.models import Routine, RoutineRun
from roost.routines.runs import RoutineRunStore
from roost.routines.texts import slot_line
from roost.talk.store import TalkStore, message_out
from roost.work.models import WorkDraft, WorkKind, routine_origin

if TYPE_CHECKING:
    from roost.talk.runner import TurnRunner


class RoutineLauncher:
    def __init__(self, talk: TalkStore, turns: "TurnRunner", runs: RoutineRunStore, events: EventHub) -> None:
        self._talk = talk
        self._turns = turns
        self._runs = runs
        self._events = events

    async def launch(
        self, user_id: str, routine: Routine, slot_at: datetime, *, late: bool, now: datetime, note: str | None = None,
    ) -> RoutineRun:
        """Record the run as ``queued`` and queue its item. Raises ``SlotAlreadyRecorded`` for a slot already run.
        ``note`` is the run log's line (the page watch says why it ran). A watching routine's page joins the run's
        link scope: its address passed ``askable_url`` and came from the owner or a clean run, never from a page."""
        item_id = str(uuid4())
        run = await self._runs.record(user_id, routine, slot_at, "queued", work_item_id=item_id, note=note)
        body = f"{routine.instructions}\n\n{slot_line(slot_at, now, late=late)}".lstrip()
        message = await self._talk.add_message(user_id, routine.thread_id, "user", body, kind="routine")
        await self._events.publish(user_id, {
            "type": "message", "thread_id": routine.thread_id, "message": message_out(message)})
        await self._turns.submit(user_id, WorkDraft(
            bot_id=routine.bot_id, thread_id=routine.thread_id, kind=WorkKind.ROUTINE,
            origin=routine_origin(routine.name), body=routine.name, tainted=routine.tainted,
            message_id=message.id, link_scope=(routine.watch.url,) if routine.watch is not None else (),
        ), item_id=item_id)
        return run
