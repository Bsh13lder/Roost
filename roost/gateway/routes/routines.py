"""Routines over HTTP: a bot's scheduled jobs (design §3.6).

- ``GET /api/bots/{bot_id}/routines`` and ``POST`` the same path: list and create.
- ``PATCH`` and ``DELETE /api/routines/{id}``: edit, switch on or off (``enabled``), delete. A built-in routine can
  be re-timed and switched only, and never deleted (422).
- ``POST /api/routines/{id}/run-now``: start a run at once (202), or 409 when one is open or the daily limit is used.
- ``POST /api/routines/{id}/resume``: Resume on a "Finished routine" line (v48): no longer finished, on again and
  planned from now; Delete now is the plain ``DELETE``. A routine's ``finished`` is ``{at, reason, delete_at}`` or null.
- ``GET /api/routines/{id}/runs?before=<run id>``: the run history, newest first, a page at a time.
- ``POST /api/routines/preview``: the words and the next five local times for a schedule, with no write.
- A routine may carry ``watch`` (``{url, part, every_min}``; null stops it): Roost reads that page itself every few
  minutes and runs the routine only when the part changed (docs/plans/2026-11-04-roost-routine-watch.md).

Every route has ``CurrentUser`` and every write has ``RequireOrigin``. ``RoutineService`` does the work and this module
turns its answers into status codes. A bot or routine that is not the user's is a 404, never the object. Times go out
as UTC ISO strings, except the preview's, which are local."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from roost.constants import ROUTINE_INSTRUCTIONS_MAX, ROUTINE_NAME_MAX

from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.routines.finished import finished_out
from roost.routines.models import Routine, RoutineRun
from roost.routines.runs import iso
from roost.routines.service import Conflict, NoSuchBot, NoSuchRoutine, Refused, RoutineService, RoutineView
from roost.routines.watch_models import WatchIn, watch_out

routines_router = APIRouter(prefix="/api", tags=["routines"])

BOT_NOT_FOUND = "Bot not found"
ROUTINE_NOT_FOUND = "Routine not found"

# A hard wire cap well above the service's own limits (which keep their friendly messages).
WIRE_SLACK = 2
MODEL_WIRE_MAX = 64


class RoutineIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(max_length=ROUTINE_NAME_MAX * WIRE_SLACK)
    instructions: str = Field(max_length=ROUTINE_INSTRUCTIONS_MAX * WIRE_SLACK)
    schedule: dict[str, Any]
    enabled: bool = True
    watch: WatchIn | None = None        # "Only run when the page changes"; None: runs on its schedule
    model: str | None = Field(default=None, max_length=MODEL_WIRE_MAX)   # None: the bot's own model


class RoutinePatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str | None = Field(default=None, max_length=ROUTINE_NAME_MAX * WIRE_SLACK)
    instructions: str | None = Field(default=None, max_length=ROUTINE_INSTRUCTIONS_MAX * WIRE_SLACK)
    schedule: dict[str, Any] | None = None
    enabled: bool | None = None
    watch: WatchIn | None = None        # sent as null: stop watching
    model: str | None = Field(default=None, max_length=MODEL_WIRE_MAX)   # sent as null: the bot's own model


class PreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schedule: dict[str, Any] = Field(default_factory=dict)


def _service(request: Request) -> RoutineService:
    return request.app.state.routines


def _text(moment) -> str | None:
    return iso(moment) if moment is not None else None


def routine_out(view: RoutineView) -> dict[str, Any]:
    routine: Routine = view.routine
    return {
        "id": routine.id, "name": routine.name, "instructions": routine.instructions,
        "schedule": routine.schedule.model_dump(), "words": view.words, "enabled": routine.enabled,
        "builtin": routine.builtin, "tainted": routine.tainted, "created_by": routine.created_by,
        "thread_id": routine.thread_id,
        "next_run_at": _text(view.slot), "last_run_at": _text(routine.last_run_at), "last_state": view.last_state,
        "watch": _watch_out(view), "model": routine.model, "last_error": _last_error_out(routine),
        "finished": finished_out(routine),
    }


def _last_error_out(routine: Routine) -> dict[str, Any] | None:
    """v47: the routine's last failure, a fixed word and its time ("Couldn't check (computer didn't answer) · 12:40")."""
    if routine.last_error_kind is None or routine.last_error_at is None:
        return None
    return {"kind": routine.last_error_kind, "at": iso(routine.last_error_at)}


def _watch_out(view: RoutineView) -> dict[str, Any] | None:
    shown = watch_out(view.routine.watch)
    if shown is None:
        return None
    return {**shown, "last_checked_at": _text(view.checked_at), "last_changed_at": _text(view.changed_at)}


def run_out(run: RoutineRun, report_message_id: str | None = None) -> dict[str, Any]:
    return {
        "id": run.id, "slot_at": iso(run.slot_at), "state": run.state, "missed_count": run.missed_count,
        "note": run.note or None, "started_at": _text(run.started_at), "finished_at": _text(run.finished_at),
        "report_message_id": report_message_id,
    }


async def _guarded(pending):
    """Await ``pending``, turning the service's answers into the right status."""
    try:
        return await pending
    except NoSuchBot:
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND) from None
    except NoSuchRoutine:
        raise HTTPException(status_code=404, detail=ROUTINE_NOT_FOUND) from None
    except Refused as exc:
        raise HTTPException(status_code=422, detail=exc.text) from None
    except Conflict as exc:
        raise HTTPException(status_code=409, detail=exc.text) from None


@routines_router.get("/bots/{bot_id}/routines")
async def list_routines(bot_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    views = await _guarded(_service(request).list(user.id, bot_id))
    return {"routines": [routine_out(v) for v in views]}


@routines_router.post("/bots/{bot_id}/routines", status_code=201, dependencies=[RequireOrigin])
async def create_routine(bot_id: str, body: RoutineIn, request: Request, user: CurrentUser) -> dict[str, Any]:
    service = _service(request)
    routine = await _guarded(service.create(user.id, bot_id, body.name, body.instructions, body.schedule,
                                            body.enabled, watch=body.watch, model=body.model))
    return routine_out(await service.view(user.id, routine))


@routines_router.patch("/routines/{routine_id}", dependencies=[RequireOrigin])
async def patch_routine(routine_id: str, body: RoutinePatchIn, request: Request, user: CurrentUser) -> dict[str, Any]:
    service = _service(request)
    routine = await _guarded(service.update(user.id, routine_id, body.model_dump(exclude_unset=True)))
    return routine_out(await service.view(user.id, routine))


@routines_router.delete("/routines/{routine_id}", status_code=204, dependencies=[RequireOrigin])
async def delete_routine(routine_id: str, request: Request, user: CurrentUser) -> Response:
    await _guarded(_service(request).delete(user.id, routine_id))
    return Response(status_code=204)


@routines_router.post("/routines/{routine_id}/run-now", status_code=202, dependencies=[RequireOrigin])
async def run_routine_now(routine_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    run = await _guarded(_service(request).run_now(user.id, routine_id))
    return {"run": run_out(run)}


@routines_router.post("/routines/{routine_id}/resume", dependencies=[RequireOrigin])
async def resume_routine(routine_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    service = _service(request)
    routine = await _guarded(service.resume_finished(user.id, routine_id))
    return routine_out(await service.view(user.id, routine))


@routines_router.get("/routines/{routine_id}/runs")
async def routine_runs(
    routine_id: str, request: Request, user: CurrentUser, before: str | None = None,
) -> dict[str, Any]:
    service = _service(request)
    runs = await _guarded(service.runs(user.id, routine_id, before))
    reports = await _guarded(service.report_ids(user.id, routine_id))
    return {"runs": [run_out(run, reports.get(run.id)) for run in runs]}


@routines_router.post("/routines/preview", dependencies=[RequireOrigin])
async def preview_schedule(body: PreviewIn, request: Request, user: CurrentUser) -> dict[str, Any]:
    try:
        shown = _service(request).preview(body.schedule)
    except Refused as exc:
        raise HTTPException(status_code=422, detail=exc.text) from None
    return {"words": shown.words, "next": list(shown.next)}
