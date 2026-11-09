"""Money reports over HTTP (Task 14): the trend, the CSV export and the General inbox. All reads.

- ``GET /api/money/trend?months=&project_id=``: per month, per currency (never mixed); 1..24 months.
- ``GET /api/money/export.csv?from=&to=&project_id=``: months ``YYYY-MM``, a spreadsheet-safe CSV attachment.
- ``GET /api/money/general?before=``: the expenses sitting in General, newest first, a page at a time.

Another user's ``project_id`` is a 404. Repeating charges are caught up before anything is read."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, Response

from roost.constants import CSV_EXPORT_MAX_ROWS, MAX_RECORD_ID_LENGTH, MONEY_TREND_MONTHS, MONEY_TREND_MONTHS_MAX
from roost.gateway.deps import CurrentUser
from roost.money.months import current_month, month_bounds
from roost.money.reports import csv_text, range_name, trend_out
from roost.money.service import MoneyService
from roost.money.summary import expense_row

money_reports_router = APIRouter(prefix="/api/money", tags=["money"])
PROJECT_NOT_FOUND_TEXT = "Project not found"
MONTHS_ORDER_TEXT = "The first month can't be after the last."
DAY_TEXT = "A day is written YYYY-MM-DD."
_ProjectId = Annotated[str | None, Query(max_length=MAX_RECORD_ID_LENGTH)]


def _service(request: Request) -> MoneyService:
    return request.app.state.money


async def _own_project(service: MoneyService, user_id: str, project_id: str | None) -> None:
    if project_id is not None and not await service.has_project(user_id, project_id):
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)


def _month(value: str) -> str:
    try:
        month_bounds(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return value


@money_reports_router.get("/trend")
async def money_trend(request: Request, user: CurrentUser, project_id: _ProjectId = None,
                      months: Annotated[int, Query(ge=1, le=MONEY_TREND_MONTHS_MAX)] = MONEY_TREND_MONTHS):
    service = _service(request)
    await _own_project(service, user.id, project_id)
    return trend_out(await service.trend(user.id, months, project_id))


@money_reports_router.get("/export.csv")
async def export_csv(request: Request, user: CurrentUser, project_id: _ProjectId = None,
                     from_: Annotated[str | None, Query(alias="from", max_length=7)] = None,
                     to: Annotated[str | None, Query(max_length=7)] = None) -> Response:
    service = _service(request)
    await _own_project(service, user.id, project_id)
    first = _month(from_ or to or current_month())
    last = _month(to or from_ or current_month())
    if first > last:
        raise HTTPException(status_code=422, detail=MONTHS_ORDER_TEXT)
    expenses, cut = await service.export_range(user.id, first, last, project_id, CSV_EXPORT_MAX_ROWS)
    names = {project.id: project.name for project in await service.projects(user.id)}
    headers = {"Content-Disposition": f'attachment; filename="{range_name(first, last)}"',
               "X-Rows-Cut": "yes" if cut else "no", "Cache-Control": "no-store"}
    return Response(csv_text(expenses, names), media_type="text/csv; charset=utf-8", headers=headers)


@money_reports_router.get("/general")
async def general_inbox(request: Request, user: CurrentUser,
                        before: Annotated[str | None, Query(max_length=10)] = None) -> dict[str, Any]:
    if before is not None:
        try:
            if date.fromisoformat(before).isoformat() != before:
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=422, detail=DAY_TEXT) from None
    service = _service(request)
    expenses, following = await service.general_inbox(user.id, before)
    projects = {project.id: project for project in await service.projects(user.id)}
    return {"expenses": [expense_row(e, projects.get(e.project_id)) for e in expenses], "next": following}
