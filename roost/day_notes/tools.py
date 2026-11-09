"""``add_day_note`` — a bot adds a note to one day of the user's calendar (Board redesign G7).

Pydantic arguments, provenance (bot + taint) on the note, an escaped result. The day is an ISO date or
day words read in local time (forward first, then past). A bot can only add: editing and deleting day
notes are the user's, over HTTP."""

from __future__ import annotations

import html
from datetime import date, datetime
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import MAX_DAY_NOTE_LENGTH
from roost.day_notes.models import DayNoteDraft
from roost.day_notes.service import BAD_DAY_TEXT, DayNoteService
from roost.records.tool_text import ToolText
from roost.talk.domain_tools import RecordContext
from roost.timezones import local_tz
from roost.talk.outcome import ToolOutcome
from roost.tasks.day_words import find_day

_NEEDS = "a day (a date or words like 'tomorrow') and the note's text"
_DAY_LABEL = "%a %-d %b"
_MAX_DAY_ARGUMENT = 80


class AddDayNoteArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    day: ToolText = Field(min_length=1, max_length=_MAX_DAY_ARGUMENT)
    text: ToolText = Field(min_length=1, max_length=MAX_DAY_NOTE_LENGTH + 1)


def _now() -> datetime:
    return datetime.now(local_tz())


def _read_day(words: str, now: datetime) -> date | None:
    text = words.strip()
    if len(text) == 10 and text[4] == "-":
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None
    for direction in ("forward", "past"):
        found = find_day(text, now=now, direction=direction)
        if found is not None:
            return found.day
    return None


class DayNoteTools:
    names = frozenset({"add_day_note"})

    def __init__(self, service: DayNoteService, *, clock: Callable[[], datetime] = _now) -> None:
        self._service = service
        self._clock = clock

    def activity(self, name: str) -> str:
        return "adding a day note"

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        try:
            args = AddDayNoteArgs.model_validate(arguments)
        except ValidationError:
            return ToolOutcome(f"Refused: {name} needs {_NEEDS}.")
        day = _read_day(args.day, self._clock())
        if day is None:
            return ToolOutcome(f"Refused: {BAD_DAY_TEXT}")
        try:
            note = await self._service.add(ctx.user_id, DayNoteDraft(day=day, text=args.text),
                                           bot_id=ctx.bot_id, tainted=ctx.tainted)
        except ValueError as exc:
            return ToolOutcome(f"Refused: {html.escape(str(exc), quote=True)}")
        return ToolOutcome(f"Added a note for {html.escape(note.day.strftime(_DAY_LABEL), quote=True)}.",
                           created=True)
