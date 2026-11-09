"""A bot's Plan over HTTP (design 4.2, 4.5): ``GET`` and ``PUT`` the whole file, ``PATCH`` one item by id.

The server is the only parser: every answer is ``{content, revision, items, unreadable}``. A save carries the
revision it read, and a stale one is a 409 whose body holds the current copy, as notes do. A bot that is not the
user's is a 404, never the object. Writes publish ``plan_changed`` through ``PlanService``."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from roost.constants import PLAN_MAX_BYTES
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.plan import grammar
from roost.plan.grammar import PlanRefused
from roost.plan.models import Plan
from roost.plan.service import PlanService
from roost.records.revision import RevisionConflict

plan_router = APIRouter(prefix="/api/bots/{bot_id}/plan", tags=["plan"])
CONFLICT_TEXT = "The Plan changed since you opened it."
BOT_NOT_FOUND = "Bot not found"
ITEM_NOT_FOUND = "Item not found"
Status = Literal["planned", "on_it", "done", "dropped"]


class PlanPutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(max_length=PLAN_MAX_BYTES * 2)
    base_revision: int = Field(ge=1)


class ItemPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=1)
    status: Status | None = None
    text: str | None = Field(default=None, min_length=1, max_length=1000)
    date: str | None = Field(default=None, max_length=10)
    time: str | None = Field(default=None, max_length=5)
    tags: list[str] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _something(self) -> "ItemPatchIn":
        if not (self.model_fields_set - {"base_revision"}):
            raise ValueError("Say what to change.")
        return self

    def changes(self) -> dict:
        return {name: getattr(self, name) for name in self.model_fields_set - {"base_revision"}}


def _service(request: Request) -> PlanService:
    return request.app.state.plan


def plan_out(plan: Plan) -> dict:
    doc = grammar.parse(plan.content)
    return {
        "content": plan.content, "revision": plan.revision, "unreadable": doc.unreadable,
        "items": [{
            "id": i.id, "status": i.status, "text": i.text, "tags": list(i.tags), "date": i.date, "time": i.time,
            "done_on": i.done_on, "dropped_on": i.dropped_on, "scheduled": i.scheduled, "indent": i.indent,
            "line_no": i.line_no, "tainted": i.id in plan.item_taint,
        } for i in doc.items],
    }


def _conflict(exc: RevisionConflict) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": CONFLICT_TEXT, "current": plan_out(exc.current)})


@plan_router.get("")
async def get_plan(bot_id: str, request: Request, user: CurrentUser):
    plan = await _service(request).read(user.id, bot_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND)
    return plan_out(plan)


@plan_router.put("", dependencies=[RequireOrigin])
async def put_plan(bot_id: str, body: PlanPutIn, request: Request, user: CurrentUser):
    try:
        plan = await _service(request).put_text(user.id, bot_id, body.content, base_revision=body.base_revision)
    except RevisionConflict as exc:
        return _conflict(exc)
    except PlanRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if plan is None:
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND)
    return plan_out(plan)


@plan_router.patch("/items/{item_id}", dependencies=[RequireOrigin])
async def patch_item(bot_id: str, item_id: str, body: ItemPatchIn, request: Request, user: CurrentUser):
    service = _service(request)
    if await service.read(user.id, bot_id) is None:
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND)
    try:
        plan = await service.patch_item(user.id, bot_id, item_id, body.base_revision, body.changes())
    except RevisionConflict as exc:
        return _conflict(exc)
    except PlanRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if plan is None:
        raise HTTPException(status_code=404, detail=ITEM_NOT_FOUND)
    return plan_out(plan)
