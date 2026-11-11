"""A finished routine's words and its chat line (owner, 2026-11-11, docs/plans/2026-11-11-roost-routine-finish.md).

Kept apart from the ``finish_routine`` handler (``finish.py``) because ``RoutineService`` posts the line and the
handler calls the service. Nothing here reads the clock or the database."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Final

from roost.constants import ROUTINE_FINISHED_KEEP_DAYS, ROUTINE_FINISHED_REASON_MAX
from roost.events.hub import EventHub
from roost.routines.models import Routine
from roost.routines.runs import iso
from roost.talk.store import Message, TalkStore, message_out

FINISHED_KIND: Final = "routine_finished"


def delete_at(finished_at: datetime) -> datetime:
    return finished_at + timedelta(days=ROUTINE_FINISHED_KEEP_DAYS)


def clean_reason(raw: str) -> str:
    """One line, within the cap (a bot's text may hold line breaks)."""
    return " ".join(raw.split())[:ROUTINE_FINISHED_REASON_MAX].strip()


def finished_line(name: str, reason: str) -> str:
    """"Finished routine · Watch physio: The appointment is booked. I'll delete it in 7 days.\""""
    head = f"Finished routine · {name}" + (f": {reason.rstrip('.')}" if reason else "")
    return f"{head}. I'll delete it in {ROUTINE_FINISHED_KEEP_DAYS} days."


def finished_out(routine: Routine) -> dict[str, Any] | None:
    """The wire's ``finished``: when, why and when it goes; None for a routine that is not finished."""
    if routine.finished_at is None:
        return None
    return {"at": iso(routine.finished_at), "reason": routine.finished_reason or "",
            "delete_at": iso(delete_at(routine.finished_at))}


async def post_finished_line(
    talk: TalkStore, events: EventHub, user_id: str, thread_id: str, routine: Routine, *, tainted: bool,
) -> Message:
    """The one chat line with Resume and Delete now. UI only: it never reaches the model. A tainted run's line
    wears the "from web content" mark, since its reason came out of such a run."""
    assert routine.finished_at is not None
    reason = routine.finished_reason or ""
    body = json.dumps({"routine_id": routine.id, "name": routine.name, "reason": reason,
                       "delete_at": iso(delete_at(routine.finished_at)), "text": finished_line(routine.name, reason)})
    message = await talk.add_message(user_id, thread_id, "activity", body, tainted=tainted, kind=FINISHED_KIND,
                                     author_bot_id=routine.bot_id)
    await events.publish(user_id, {"type": "message", "thread_id": thread_id, "message": message_out(message)})
    return message
