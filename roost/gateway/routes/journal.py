"""The Bot Journal over HTTP, read-only (obsidian track, part 2).

``GET /api/bots/{id}/journal`` lists the bot's recent days, ``GET /api/bots/{id}/journal/{day}`` returns one
day's Markdown, and ``GET /api/journal/search?q=`` finds days across the user's bots. Another user's bot is a
404; a day is a plain ``YYYY-MM-DD``. Only bots write a journal, so there is no write route."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request

from roost.constants import JOURNAL_SEARCH_LIMIT, MAX_NOTE_QUERY_LENGTH
from roost.gateway.deps import CurrentUser
from roost.journal.markdown import entry_lines
from roost.journal.models import JournalDay
from roost.journal.service import JournalService

journal_router = APIRouter(tags=["journal"])

NO_BOT_TEXT = "Bot not found"
NO_DAY_TEXT = "Nothing in the journal for that day"
BAD_DAY_TEXT = "A day is written like 2026-10-22."
RETIRED_BOT_TEXT = "A retired bot"
_DAY_CHARS = 10


def _service(request: Request) -> JournalService:
    return request.app.state.journal


def _day(value: str) -> date:
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=BAD_DAY_TEXT) from None
    if len(value) != _DAY_CHARS or day.isoformat() != value:
        raise HTTPException(status_code=422, detail=BAD_DAY_TEXT)
    return day


async def _own_bot(request: Request, user_id: str, bot_id: str) -> None:
    if await request.app.state.bots.get(user_id, bot_id) is None:
        raise HTTPException(status_code=404, detail=NO_BOT_TEXT)


def day_summary_out(day: JournalDay) -> dict[str, Any]:
    return {"day": day.day.isoformat(), "entries": len(entry_lines(day.content)), "tainted": day.tainted,
            "updated_at": day.updated_at}


@journal_router.get("/api/bots/{bot_id}/journal")
async def list_journal_days(bot_id: str, request: Request, user: CurrentUser):
    await _own_bot(request, user.id, bot_id)
    return {"days": [day_summary_out(day) for day in await _service(request).recent(user.id, bot_id)]}


@journal_router.get("/api/bots/{bot_id}/journal/{day}")
async def read_journal_day(bot_id: str, day: str, request: Request, user: CurrentUser):
    await _own_bot(request, user.id, bot_id)
    found = await _service(request).read(user.id, bot_id, _day(day))
    if found is None:
        raise HTTPException(status_code=404, detail=NO_DAY_TEXT)
    return {**day_summary_out(found), "bot_id": bot_id, "content": found.content}


@journal_router.get("/api/journal/search")
async def search_journals(request: Request, user: CurrentUser,
                          q: Annotated[str, Query(max_length=MAX_NOTE_QUERY_LENGTH)] = ""):
    hits = await _service(request).search(user.id, q, limit=JOURNAL_SEARCH_LIMIT)
    names = {bot.id: bot.name for bot in await request.app.state.bots.list(user.id)}
    return [{"bot_id": hit.bot_id, "bot_name": names.get(hit.bot_id, RETIRED_BOT_TEXT), "day": hit.day.isoformat(),
             "lines": list(hit.lines), "tainted": hit.tainted} for hit in hits]
