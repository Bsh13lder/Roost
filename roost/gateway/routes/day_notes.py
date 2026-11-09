"""Day notes over HTTP — the calendars' notes (Board redesign G7).

Same ``DayNoteService`` as the bot tool, so every write publishes ``day_notes_changed`` (id and day only).
The user may delete any of their notes, a bot's included; a note is never edited. Another user's note is a
404. A day is a plain ``YYYY-MM-DD``; a range is at most ``DAY_NOTES_RANGE_MAX_DAYS`` days."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from roost.constants import DAY_NOTES_LIST_LIMIT, DAY_NOTES_RANGE_MAX_DAYS, MAX_DAY_NOTE_LENGTH
from roost.day_notes.models import DayNote, DayNoteDraft
from roost.day_notes.service import BAD_DAY_TEXT, DayNoteService
from roost.gateway.deps import CurrentUser, RequireOrigin

day_notes_router = APIRouter(prefix="/api/day-notes", tags=["day-notes"])

NOT_FOUND_TEXT = "Day note not found"
RETIRED_BOT_TEXT = "A retired bot"
RANGE_ORDER_TEXT = "The range must end on or after the day it starts."
RANGE_LENGTH_TEXT = f"A range can cover at most {DAY_NOTES_RANGE_MAX_DAYS} days."
_DAY_CHARS = 10


def _iso_day(value: str) -> date:
    """A real calendar day written exactly ``YYYY-MM-DD`` (``fromisoformat`` alone also reads other forms)."""
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise ValueError(BAD_DAY_TEXT) from None
    if day.isoformat() != value:
        raise ValueError(BAD_DAY_TEXT)
    return day


Day = Annotated[str, Field(min_length=_DAY_CHARS, max_length=_DAY_CHARS), AfterValidator(lambda v: _iso_day(v).isoformat())]


class DayNoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: Day
    text: str = Field(max_length=MAX_DAY_NOTE_LENGTH * 2)


def _service(request: Request) -> DayNoteService:
    return request.app.state.day_notes


def _range(first: str, last: str) -> tuple[date, date]:
    try:
        start, end = _iso_day(first), _iso_day(last)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if end < start:
        raise HTTPException(status_code=422, detail=RANGE_ORDER_TEXT)
    if (end - start).days + 1 > DAY_NOTES_RANGE_MAX_DAYS:
        raise HTTPException(status_code=422, detail=RANGE_LENGTH_TEXT)
    return start, end


async def _bot_names(request: Request, user_id: str) -> dict[str, str]:
    return {bot.id: bot.name for bot in await request.app.state.bots.list(user_id)}


def note_out(note: DayNote, names: dict[str, str]) -> dict[str, Any]:
    """``DayNoteOut``. ``bot_name`` is read now, so a retired bot's notes say "A retired bot"."""
    name = None
    if note.author_kind == "bot":
        name = names.get(note.bot_id) if note.bot_id else None
        name = name or RETIRED_BOT_TEXT
    return {"id": note.id, "day": note.day.isoformat(), "author_kind": note.author_kind, "bot_id": note.bot_id,
            "bot_name": name, "text": note.text, "created_at": note.created_at, "tainted": note.tainted}


@day_notes_router.get("")
async def list_day_notes(request: Request, user: CurrentUser,
                         first: Annotated[str, Query(alias="from")], last: Annotated[str, Query(alias="to")]):
    start, end = _range(first, last)
    notes = await _service(request).list_range(user.id, start, end, DAY_NOTES_LIST_LIMIT)
    names = await _bot_names(request, user.id)
    return [note_out(note, names) for note in notes]


@day_notes_router.post("", status_code=201, dependencies=[RequireOrigin])
async def add_day_note(body: DayNoteIn, request: Request, user: CurrentUser):
    try:
        note = await _service(request).add(user.id, DayNoteDraft(day=_iso_day(body.day), text=body.text))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return note_out(note, {})


@day_notes_router.delete("/{note_id}", status_code=204, dependencies=[RequireOrigin])
async def delete_day_note(note_id: str, request: Request, user: CurrentUser) -> None:
    if not await _service(request).delete(user.id, note_id):
        raise HTTPException(status_code=404, detail=NOT_FOUND_TEXT)
