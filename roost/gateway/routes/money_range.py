"""``GET /api/money/range?from=&to=&project_id=``: the Money tab's list, by day (Board redesign G9, G10).

Answers the expenses of a span of local days (void ones included, newest first), a total per day and for the
whole span. Every sum is the server's and is per currency. ``general_project_id`` is where an edited
expense goes back to General (the projects list hides it). The span is at most ``MONEY_RANGE_MAX_DAYS`` days;
a ``to`` in the future is clamped to today. Another user's ``project_id`` is a 404. Repeating charges are
caught up before anything is read. A read: it needs a session, not an origin header."""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request

from roost.constants import DEFAULT_CURRENCY, MAX_RECORD_ID_LENGTH, MONEY_RANGE_MAX_DAYS
from roost.gateway.deps import CurrentUser
from roost.money.day_totals import day_totals, range_summary
from roost.money.months import today_madrid
from roost.money.project_store import is_general
from roost.money.service import MoneyService
from roost.money.summary import amounts_out, expense_row

money_range_router = APIRouter(prefix="/api/money", tags=["money"])
PROJECT_NOT_FOUND_TEXT = "Project not found"
DAY_TEXT = "A day is written YYYY-MM-DD."
ORDER_TEXT = "The first day can't be after the last."
SPAN_TEXT = f"A range can span at most {MONEY_RANGE_MAX_DAYS} days."
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_Day = Annotated[str, Query(min_length=10, max_length=10)]


def _day(value: str) -> date:
    try:
        if _DAY.match(value):
            return date.fromisoformat(value)
    except ValueError:
        pass
    raise HTTPException(status_code=422, detail=DAY_TEXT)


def _bounds(first: str, last: str) -> tuple[date, date, date]:
    """The requested first and last day, with the last clamped to today (local); and today."""
    start, end = _day(first), _day(last)
    if start > end:
        raise HTTPException(status_code=422, detail=ORDER_TEXT)
    if (end - start).days + 1 > MONEY_RANGE_MAX_DAYS:
        raise HTTPException(status_code=422, detail=SPAN_TEXT)
    today = date.fromisoformat(today_madrid())
    return start, min(end, today), today


@money_range_router.get("/range")
async def money_range(request: Request, user: CurrentUser, from_: Annotated[_Day, Query(alias="from")], to: _Day,
                      project_id: Annotated[str | None, Query(max_length=MAX_RECORD_ID_LENGTH)] = None
                      ) -> dict[str, Any]:
    start, end, _ = _bounds(from_, to)
    service: MoneyService = request.app.state.money
    if project_id is not None and not await service.has_project(user.id, project_id):
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)
    expenses, rules = (), {}
    if start <= end:
        expenses, rules = await service.range(user.id, start, end, project_id)
    projects = {project.id: project for project in await service.projects(user.id)}
    summary = range_summary(expenses)
    general = next((project.id for project in projects.values() if is_general(project)), None)
    return {
        "from": start.isoformat(), "to": end.isoformat(), "currency": DEFAULT_CURRENCY, "general_project_id": general,
        "expenses": [expense_row(e, projects.get(e.project_id), rules.get(e.recurring_id or "")) for e in expenses],
        "days": [{"day": d.day, "count": d.count, "totals": amounts_out(d.totals), "bar_percent": d.bar_percent}
                 for d in day_totals(expenses, DEFAULT_CURRENCY)],
        "summary": {"count": summary.count, "totals": amounts_out(summary.totals)},
    }
