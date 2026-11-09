"""Repeating expenses over HTTP (Task 12): the rules and "Upcoming charges".

- ``GET/POST /api/money/recurring``, ``PATCH/DELETE /api/money/recurring/{id}``: a rule makes a charge on each
  occurrence, lazily, when money is read (``RecurringService.catch_up``).
- ``GET /api/money/upcoming?project_id=``: the charges due in the next 31 days.

Another user's rule is a 404; another user's project is "No such project." (422). Every write needs the origin."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from roost.constants import (
    MAX_EXPENSE_NOTE_LENGTH, MAX_EXPENSE_VENDOR_LENGTH, MAX_RECORD_ID_LENGTH, PROJECT_STATUSES,
)
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.money.amounts import JsonAmount, parse_amount
from roost.money.currency import OptionalCurrencyCode
from roost.money.months import today_madrid
from roost.money.recurring import Recurring, recurring_out, upcoming_out
from roost.money.service import MoneyService

money_recurring_router = APIRouter(prefix="/api/money", tags=["money"])
RULE_NOT_FOUND_TEXT = "Repeating expense not found"
PROJECT_NOT_FOUND_TEXT = "Project not found"
DAY_TEXT = "A day is written YYYY-MM-DD."
NOTHING_TO_CHANGE_TEXT = "Send at least one thing to change."
CANT_CLEAR_TEXT = "{field} can't be cleared."


def _day(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(DAY_TEXT) from None
    if parsed.isoformat() != value:
        raise ValueError(DAY_TEXT)
    return value


class RecurringIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: JsonAmount
    project_id: str = Field(min_length=1, max_length=MAX_RECORD_ID_LENGTH)
    cadence: Literal["weekly", "monthly", "yearly"]
    anchor_day: str | None = Field(default=None, max_length=10)
    note: str | None = Field(default=None, max_length=MAX_EXPENSE_NOTE_LENGTH)
    vendor: str | None = Field(default=None, max_length=MAX_EXPENSE_VENDOR_LENGTH)
    currency: OptionalCurrencyCode = None
    ends_on: str | None = Field(default=None, max_length=10)

    _days = field_validator("anchor_day", "ends_on")(_day)


class RecurringPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: JsonAmount | None = None
    note: str | None = Field(default=None, max_length=MAX_EXPENSE_NOTE_LENGTH)
    vendor: str | None = Field(default=None, max_length=MAX_EXPENSE_VENDOR_LENGTH)
    ends_on: str | None = Field(default=None, max_length=10)
    project_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)

    _days = field_validator("ends_on")(_day)

    @model_validator(mode="after")
    def _something_to_change(self) -> "RecurringPatchIn":
        if not self.model_fields_set:
            raise ValueError(NOTHING_TO_CHANGE_TEXT)
        for field in ("amount", "project_id"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(CANT_CLEAR_TEXT.format(field=field))
        return self

    def changes(self) -> dict[str, Any]:
        sent = self.model_fields_set
        found: dict[str, Any] = {}
        if "amount" in sent:
            found["amount"] = parse_amount(self.amount)
        if "note" in sent:
            found["description"] = (self.note or "").strip() or None
        if "vendor" in sent:
            found["vendor"] = (self.vendor or "").strip() or None
        if "ends_on" in sent:
            found["ends_on"] = self.ends_on
        if "project_id" in sent:
            found["project_id"] = self.project_id
        return found


def _service(request: Request) -> MoneyService:
    return request.app.state.money


def _refused(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


async def _own_project(service: MoneyService, user_id: str, project_id: str | None) -> None:
    """A ``project_id`` filter that is not the user's project is a 404."""
    if project_id is not None and not await service.has_project(user_id, project_id):
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)


async def _out(service: MoneyService, user_id: str, rules: tuple[Recurring, ...]) -> list[dict[str, Any]]:
    projects = {project.id: project for project in await service.projects(user_id)}
    archived = PROJECT_STATUSES[1]
    return [recurring_out(rule, projects[rule.project_id].name if rule.project_id in projects else "",
                          paused=rule.project_id in projects and projects[rule.project_id].status == archived)
            for rule in rules]


@money_recurring_router.get("/recurring")
async def list_recurring(request: Request, user: CurrentUser, project_id: str | None = None):
    service = _service(request)
    await _own_project(service, user.id, project_id)
    return await _out(service, user.id, await service.recurring.list(user.id, project_id))


@money_recurring_router.post("/recurring", status_code=201, dependencies=[RequireOrigin])
async def create_recurring(body: RecurringIn, request: Request, user: CurrentUser):
    service = _service(request)
    try:
        project = await service.open_project(user.id, body.project_id)
        rule = await service.recurring.create(
            user.id, project, amount=parse_amount(body.amount), currency=body.currency, note=body.note,
            vendor=body.vendor, cadence=body.cadence,
            anchor_day=date.fromisoformat(body.anchor_day or today_madrid()),
            ends_on=None if body.ends_on is None else date.fromisoformat(body.ends_on))
    except ValueError as exc:
        raise _refused(exc) from exc
    return (await _out(service, user.id, (rule,)))[0]


@money_recurring_router.patch("/recurring/{rule_id}", dependencies=[RequireOrigin])
async def patch_recurring(rule_id: str, body: RecurringPatchIn, request: Request, user: CurrentUser):
    service = _service(request)
    try:
        changes = body.changes()
        if await service.recurring.get(user.id, rule_id) is None:
            raise HTTPException(status_code=404, detail=RULE_NOT_FOUND_TEXT)
        if "project_id" in changes:
            await service.open_project(user.id, changes["project_id"])
        rule = await service.recurring.update(user.id, rule_id, changes)
    except ValueError as exc:
        raise _refused(exc) from exc
    if rule is None:
        raise HTTPException(status_code=404, detail=RULE_NOT_FOUND_TEXT)
    return (await _out(service, user.id, (rule,)))[0]


@money_recurring_router.delete("/recurring/{rule_id}", status_code=204, dependencies=[RequireOrigin])
async def delete_recurring(rule_id: str, request: Request, user: CurrentUser) -> Response:
    if not await _service(request).recurring.delete(user.id, rule_id):
        raise HTTPException(status_code=404, detail=RULE_NOT_FOUND_TEXT)
    return Response(status_code=204)


@money_recurring_router.get("/upcoming")
async def upcoming_charges(request: Request, user: CurrentUser, project_id: str | None = None):
    service = _service(request)
    await _own_project(service, user.id, project_id)
    charges = await service.recurring.upcoming(user.id, project_id)
    return [upcoming_out(charge) for charge in charges]
