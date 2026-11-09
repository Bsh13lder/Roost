"""``DayNoteService`` — the rules both doors (routes and the bot tool) share, and the live frame.

A note is 1..``MAX_DAY_NOTE_LENGTH`` characters once trimmed, on a real day within
``DAY_NOTE_MAX_YEARS`` of today (local), and a day holds at most ``MAX_DAY_NOTES_PER_DAY``.
The frame carries only the id and the day, never the text."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from typing import Callable, Literal

from roost.constants import DAY_NOTE_MAX_YEARS, MAX_DAY_NOTE_LENGTH, MAX_DAY_NOTES_PER_DAY
from roost.day_notes.models import DayNote, DayNoteDraft
from roost.day_notes.store import DayNoteStore
from roost.events.hub import EventHub
from roost.timezones import local_tz

DayNoteChange = Literal["created", "deleted"]
LENGTH_TEXT = f"A day note can be up to {MAX_DAY_NOTE_LENGTH} characters."
FULL_DAY_TEXT = f"That day already has {MAX_DAY_NOTES_PER_DAY} notes."
BAD_DAY_TEXT = "That isn't a day I can read."
_YEAR_DAYS = 366


def madrid_today() -> date:
    return datetime.now(local_tz()).date()


def check_day(day: date, today: date) -> None:
    """``ValueError`` (a plain sentence) when ``day`` is too far from ``today`` either way."""
    if abs((day - today).days) > DAY_NOTE_MAX_YEARS * _YEAR_DAYS:
        raise ValueError(BAD_DAY_TEXT)


class DayNoteService:
    def __init__(self, store: DayNoteStore, events: EventHub, *, today: Callable[[], date] = madrid_today) -> None:
        self._store = store
        self._events = events
        self._today = today

    async def list_range(self, user_id: str, first: date, last: date, limit: int) -> tuple[DayNote, ...]:
        return await self._store.list_range(user_id, first, last, limit)

    async def add(self, user_id: str, draft: DayNoteDraft, *, bot_id: str | None = None,
                  tainted: bool = False) -> DayNote:
        """``ValueError``: the text, the day or the day's cap breaks a rule (nothing is written)."""
        text = draft.text.strip()
        if not 1 <= len(text) <= MAX_DAY_NOTE_LENGTH:
            raise ValueError(LENGTH_TEXT)
        check_day(draft.day, self._today())
        note = await self._store.add(user_id, replace(draft, text=text), bot_id=bot_id, tainted=tainted,
                                     max_per_day=MAX_DAY_NOTES_PER_DAY)
        if note is None:
            raise ValueError(FULL_DAY_TEXT)
        await self._changed(user_id, "created", note)
        return note

    async def delete(self, user_id: str, note_id: str) -> bool:
        """The user's own door only: no tool deletes. ``False``: no such note (or not theirs)."""
        found = await self._store.get(user_id, note_id)
        if found is None or not await self._store.delete(user_id, note_id):
            return False
        await self._changed(user_id, "deleted", found)
        return True

    async def _changed(self, user_id: str, change: DayNoteChange, note: DayNote) -> None:
        await self._events.publish(user_id, {"type": "day_notes_changed", "change": change, "id": note.id,
                                             "day": note.day.isoformat()})
