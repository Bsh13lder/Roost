"""All routines in one place, and the routine templates.

- ``GET /api/routines``: every routine of the user's bots, each with its bot's id and name, the next run in the install's zone
  time (``next_run_madrid``, ``None`` while paused) and the last run's result.
- ``GET /api/routines/runs?limit=``: the newest runs across every routine (1 to ``ROUTINE_RECENT_RUNS_MAX``).
- ``GET /api/routines/occurrences?from=&to=&bot_id=``: the upcoming run times of the user's enabled routines on the
  local days ``from``..``to`` (at most ``ROUTINE_OCCURRENCE_SPAN_DAYS_MAX`` days, from now on, oldest first, at most
  ``ROUTINE_OCCURRENCES_MAX`` with ``truncated`` when cut), for the calendars; ``bot_id`` narrows to one bot (another
  user's is 404). A backwards or too long window is 422.
- ``GET /api/routine-templates``: the built-in templates, with their schedules in words.
- ``POST /api/bots/{bot_id}/routines/from-template``: add a template to one of your bots (201), through the same
  ``RoutineService.create`` as ``POST /api/bots/{bot_id}/routines``. An unknown template is 422, another user's bot
  404.

Every route has ``CurrentUser``; the write has ``RequireOrigin``."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from roost.constants import ROUTINE_OCCURRENCE_SPAN_DAYS_MAX, ROUTINE_RECENT_RUNS_DEFAULT, ROUTINE_RECENT_RUNS_MAX
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.gateway.routes.routines import BOT_NOT_FOUND, _guarded, routine_out, run_out
from roost.routines.hub import HubRoutine, HubRun, RoutinesHub
from roost.routines.occurrences import Occurrence
from roost.routines.service import NoSuchBot
from roost.routines.runs import iso
from roost.routines.schedule import parse_schedule, readable
from roost.routines.templates import ROUTINE_TEMPLATES, RoutineTemplate
from roost.timezones import local_tz

routines_hub_router = APIRouter(prefix="/api", tags=["routines"])

TEMPLATE_ID_MAX = 64
BOT_ID_MAX = 64
BACKWARDS_TEXT = "The last day comes before the first."
TOO_LONG_TEXT = f"Pick at most {ROUTINE_OCCURRENCE_SPAN_DAYS_MAX} days."


class FromTemplateIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    template_id: str = Field(min_length=1, max_length=TEMPLATE_ID_MAX)


def _hub(request: Request) -> RoutinesHub:
    return request.app.state.routines_hub


def hub_routine_out(entry: HubRoutine) -> dict[str, Any]:
    slot, last = entry.view.slot, entry.last_run
    return {
        **routine_out(entry.view), "bot_id": entry.view.routine.bot_id, "bot_name": entry.bot_name,
        "next_run_madrid": slot.astimezone(local_tz()).isoformat(timespec="minutes") if slot is not None else None,
        "last_note": (last.note or None) if last is not None else None,
        "last_finished_at": iso(last.finished_at) if last is not None and last.finished_at is not None else None,
    }


def hub_run_out(entry: HubRun) -> dict[str, Any]:
    return {**run_out(entry.run), "routine_id": entry.run.routine_id, "routine_name": entry.routine_name,
            "bot_id": entry.run.bot_id, "bot_name": entry.bot_name}


def occurrence_out(entry: Occurrence) -> dict[str, Any]:
    return {"routine_id": entry.routine_id, "routine_name": entry.routine_name, "bot_id": entry.bot_id,
            "bot_name": entry.bot_name, "at": iso(entry.at), "day": entry.day, "time": entry.time,
            "log_thread_id": entry.thread_id}


def template_out(template: RoutineTemplate) -> dict[str, Any]:
    schedule = parse_schedule(template.schedule, name=template.name)
    return {"id": template.id, "name": template.name, "instructions": template.instructions,
            "schedule": schedule.model_dump(), "words": readable(schedule), "needs_edit": template.needs_edit}


@routines_hub_router.get("/routines")
async def all_routines(request: Request, user: CurrentUser) -> dict[str, Any]:
    return {"routines": [hub_routine_out(entry) for entry in await _hub(request).list_all(user.id)]}


@routines_hub_router.get("/routines/runs")
async def recent_runs(
    request: Request, user: CurrentUser,
    limit: int = Query(default=ROUTINE_RECENT_RUNS_DEFAULT, ge=1, le=ROUTINE_RECENT_RUNS_MAX),
) -> dict[str, Any]:
    return {"runs": [hub_run_out(entry) for entry in await _hub(request).recent_runs(user.id, limit)]}


@routines_hub_router.get("/routines/occurrences")
async def routine_occurrences(
    request: Request, user: CurrentUser,
    first: date = Query(alias="from"), last: date = Query(alias="to"),
    bot_id: str | None = Query(default=None, min_length=1, max_length=BOT_ID_MAX),
) -> dict[str, Any]:
    if last < first:
        raise HTTPException(status_code=422, detail=BACKWARDS_TEXT)
    if (last - first).days + 1 > ROUTINE_OCCURRENCE_SPAN_DAYS_MAX:
        raise HTTPException(status_code=422, detail=TOO_LONG_TEXT)
    try:
        page = await _hub(request).occurrences(user.id, first, last, bot_id=bot_id)
    except NoSuchBot as exc:
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND) from exc
    return {"occurrences": [occurrence_out(entry) for entry in page.occurrences], "truncated": page.truncated}


@routines_hub_router.get("/routine-templates")
async def routine_templates(user: CurrentUser) -> dict[str, Any]:
    return {"templates": [template_out(template) for template in ROUTINE_TEMPLATES]}


@routines_hub_router.post("/bots/{bot_id}/routines/from-template", status_code=201, dependencies=[RequireOrigin])
async def add_template(bot_id: str, body: FromTemplateIn, request: Request, user: CurrentUser) -> dict[str, Any]:
    routine = await _guarded(_hub(request).add_template(user.id, bot_id, body.template_id))
    return routine_out(await request.app.state.routines.view(user.id, routine))
