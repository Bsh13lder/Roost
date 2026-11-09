"""``GET /api/dates/parse``: how the gateway reads a typed date (look & feel redesign P1). The web's
date pickers show it under the box while the user types, and read a typed day with it before saving.
``kind=due`` (the default) is the reading a task's due gets (``roost.tasks.due.parse_due``); ``kind=spent``
is the reading an expense's day gets (``roost.money.months.parse_spent_at``: "yesterday", "ayer",
"2 days ago", never a future day). Both are on the install's zone, and the route changes nothing."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from roost.constants import MAX_DUE_TEXT_LENGTH
from roost.gateway.deps import CurrentUser
from roost.money.months import parse_spent_at
from roost.tasks.due import parse_due

dates_router = APIRouter(prefix="/api/dates", tags=["dates"])

DateKind = Literal["due", "spent"]


def _read_day(text: str, kind: DateKind) -> str | None:
    """The day (or, for a due that names a time, the local time) the words mean; ``None`` for no text.
    Raises ``ValueError`` with the parser's plain sentence when it can't read them."""
    if not text.strip():
        return None
    if kind == "spent":
        return parse_spent_at(text)
    return parse_due(text).due_date


@dates_router.get("/parse")
async def parse_date(user: CurrentUser, text: str = Query(default="", max_length=MAX_DUE_TEXT_LENGTH),
                     kind: DateKind = "due"):
    """``{"due_date": "2026-10-16"}``, ``{"due_date": "2026-10-16T09:00:00+02:00"}`` when a due's words
    name a time, ``{"due_date": null}`` for no text; 422 with the parser's sentence when it can't read it."""
    try:
        return {"due_date": _read_day(text, kind)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
