"""Projects over HTTP — the Board's Projects tab and a project's page (projects
hub P7, H2, H4, H5, H8–H10, H14, H15). Same ``ProjectService`` as the bots'
tools, so every change is published on ``money_changed`` and every open tab
refreshes.

- General (H2) is hidden from the list and can be neither changed nor deleted
  (422).
- Every amount goes out as a string, and each budget carries its bar's
  ``used_percent`` and ``tone`` (H8): the web never adds amounts.
- The total budget (P3, H5) is set, or cleared with ``null``, only by
  ``PUT /api/projects/{id}/budget`` and top-ups. PATCH never takes ``budget``,
  so every change to the total leaves its row in the history.
- A rename onto a name in use is 409. Any other broken rule is 422 with the
  rule's plain sentence. A top-up already undone stays undone: changing or
  undoing it again is 409 (``TopUpUndone``). A cleared total budget, or one
  that would go below 0, is a broken rule: 422.
- Another user's project or top-up is a 404, never the object.

``ProjectLinkIn`` is also the body of ``PUT /api/notes/{id}/project`` and
``PUT /api/documents/{id}/project`` (H12)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool, StringConstraints, model_validator

from roost.constants import (
    DEFAULT_CURRENCY, DEFAULT_PROJECT_COLOR, MAX_CATEGORY_NAME_LENGTH, MAX_RECORD_ID_LENGTH,
    PROJECT_COLORS, PROJECT_STATUSES, TOPUP_SOURCE_MAX_CHARS,
)
from roost.documents.format import document_out
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.money.amounts import JsonAmount, amount_text, parse_amount
from roost.money.currency import CurrencyCode as Currency
from roost.money.models import COLOR_TEXT, DATE_TEXT, TOPUP_CREDIT, Project, ProjectDraft, TopUp
from roost.money.project_store import NAME_TAKEN_TEXT
from roost.money.recurring import recurring_out, upcoming_out
from roost.money.summary import amounts_out, budget_line_out, expense_row
from roost.money.topup_store import TopUpUndone
from roost.notes.format import note_summary_out
from roost.projects.numbers import Progress, ProjectNumbers, TaskMoney
from roost.projects.service import STATUS_TEXT, ProjectDetail, ProjectService
from roost.tasks.format import task_out

projects_router = APIRouter(tags=["projects"])

PROJECT_NOT_FOUND_TEXT = "Project not found"
TOPUP_NOT_FOUND_TEXT = "Top-up not found"
# ProjectStore's refusal of a name one of the user's other projects has (Task 2): the one 409 of PATCH.
NAME_IN_USE_TEXT = NAME_TAKEN_TEXT
NOTHING_TO_CHANGE_TEXT = "Send at least one change."
NOT_CLEARABLE_TEXT = "A project's name, colour, status and currency can't be cleared."
_NOT_CLEARABLE = frozenset({"name", "color", "status", "currency"})


def _day(value: str | None) -> str | None:
    """A plain ``YYYY-MM-DD`` day, as ``ProjectDraft`` keeps it (Task 2's ``DATE_TEXT``)."""
    if value is None:
        return None
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise ValueError(DATE_TEXT) from None
    if day.isoformat() != value:   # Python also reads "20261231" or week dates; only the plain form is kept
        raise ValueError(DATE_TEXT)
    return value


def _color(value: str) -> str:
    """One of ``PROJECT_COLORS``, case ignored, as ``ProjectDraft`` tidies it."""
    color = value.strip().lower()
    if color not in PROJECT_COLORS:
        raise ValueError(COLOR_TEXT)
    return color


def _status(value: str) -> str:
    if value not in PROJECT_STATUSES:
        raise ValueError(STATUS_TEXT)
    return value


def _amount(value: str | int | float | None) -> Decimal | None:
    """``parse_amount``'s rules (more than 0, at most 2 decimals); ``None`` stays ``None``."""
    return None if value is None else parse_amount(value)


ProjectName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_CATEGORY_NAME_LENGTH),
]
Amount = JsonAmount
Day = Annotated[str | None, AfterValidator(_day)]
Color = Annotated[str, AfterValidator(_color)]
Status = Annotated[str, AfterValidator(_status)]
RecordId = Annotated[str, Field(max_length=MAX_RECORD_ID_LENGTH)]


class ProjectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: ProjectName
    currency: Currency = DEFAULT_CURRENCY
    budget: Amount | None = None              # the total budget; top-ups add to it (H4)
    monthly_budget: Amount | None = None      # the monthly limit
    color: Color = DEFAULT_PROJECT_COLOR
    start_date: Day = None
    due_date: Day = None
    lead_bot_id: RecordId | None = None

    def draft(self) -> ProjectDraft:
        """Raises ``ValueError`` (plain text) for an amount ``parse_amount`` refuses."""
        return ProjectDraft(name=self.name, currency=self.currency, budget=_amount(self.budget),
                            monthly_budget=_amount(self.monthly_budget), color=self.color,
                            start_date=self.start_date, due_date=self.due_date, lead_bot_id=self.lead_bot_id)


class ProjectPatchIn(BaseModel):
    """Only the fields sent change. ``null`` clears a date, the monthly limit
    or the lead bot (H5). The total budget moves only through
    ``PUT …/budget`` (``BudgetIn``) and top-ups."""

    model_config = ConfigDict(extra="forbid")
    name: ProjectName | None = None
    color: Color | None = None
    status: Status | None = None
    currency: Currency | None = None
    start_date: Day = None
    due_date: Day = None
    monthly_budget: Amount | None = None
    lead_bot_id: RecordId | None = None

    @model_validator(mode="after")
    def _a_change_that_clears_only_what_can_be(self) -> "ProjectPatchIn":
        if not self.model_fields_set:
            raise ValueError(NOTHING_TO_CHANGE_TEXT)
        if any(getattr(self, field) is None for field in self.model_fields_set & _NOT_CLEARABLE):
            raise ValueError(NOT_CLEARABLE_TEXT)
        return self

    def changes(self) -> dict[str, Any]:
        """Raises ``ValueError`` (plain text) for a monthly limit ``parse_amount`` refuses."""
        fields = self.model_dump(include=self.model_fields_set)
        if "monthly_budget" in fields:
            return {**fields, "monthly_budget": _amount(fields["monthly_budget"])}
        return fields


class BudgetIn(BaseModel):
    """The total budget (P3): an amount string, or ``null`` to clear it (H5).
    ``amount`` is required, so ``{}`` is a 422, never a silent clear."""

    model_config = ConfigDict(extra="forbid")
    amount: str | None


class TopupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Amount
    source: str | None = Field(default=None, max_length=TOPUP_SOURCE_MAX_CHARS)


class TopupEditIn(BaseModel):
    """The top-up's new amount. The store records the difference (H4)."""

    model_config = ConfigDict(extra="forbid")
    amount: Amount


class ProjectLinkIn(BaseModel):
    """One of the user's projects, or ``null`` to unlink (H12)."""

    model_config = ConfigDict(extra="forbid")
    project_id: RecordId | None


def progress_out(progress: Progress) -> dict[str, Any]:
    return {"done": progress.done, "failed": progress.failed, "total": progress.total, "open": progress.open,
            "overdue": progress.overdue,
            "steps_done": progress.steps_done, "steps_total": progress.steps_total,
            "planned_total": amount_text(progress.planned_total)}


def _optional_amount(amount: Decimal | None) -> str | None:
    return None if amount is None else amount_text(amount)


def task_money_out(money: TaskMoney) -> dict[str, str | None]:
    """``TaskMoneyOut``: a task's slice, what is spent on it, and what is left (negative when over)."""
    return {"planned": _optional_amount(money.planned), "spent": amount_text(money.spent),
            "left": _optional_amount(money.left)}


def project_out(project: Project, numbers: ProjectNumbers, progress: Progress) -> dict[str, Any]:
    """``ProjectOut``: a row on the Projects tab, and the head of a project's page."""
    return {
        "id": project.id, "name": project.name, "color": project.color, "currency": project.currency,
        "status": project.status, "start_date": project.start_date, "due_date": project.due_date,
        "lead_bot_id": project.lead_bot_id, "total": budget_line_out(numbers.total),
        "month": budget_line_out(numbers.month), "other_currencies": amounts_out(numbers.other_currencies),
        "starred_total": amount_text(numbers.starred_total), "money_in": amounts_out(numbers.money_in),
        "progress": progress_out(progress),
        "tainted": project.tainted, "pinned": project.pinned, "pinned_at": project.pinned_at,
    }


def topup_out(topup: TopUp) -> dict[str, Any]:
    """``TopupOut``: one history row. An "edit" with a ``topup_id`` changed that
    top-up; one with none is a budget set by hand (H4). ``can_change``: a top-up
    that is not undone and that clearing the total budget has not taken back
    (H5), the only one Change and Undo can still act on; an edit row never is."""
    return {
        "id": topup.id, "amount": amount_text(topup.amount), "currency": topup.currency, "source": topup.source,
        "kind": topup.kind, "topup_id": topup.topup_id, "undone": topup.undone, "created_at": topup.created_at,
        "can_change": topup.kind == TOPUP_CREDIT and not topup.undone and not topup.taken_back,
    }


def project_detail_out(detail: ProjectDetail) -> dict[str, Any]:
    """``ProjectDetailOut``: the page. Its ``tainted`` covers everything it shows."""
    project = detail.project
    return {
        **project_out(project, detail.numbers, detail.progress),
        "tasks": [task_out(task) for task in detail.tasks],
        "expenses": [expense_row(expense, project) for expense in detail.expenses],
        "notes": [note_summary_out(note) for note in detail.notes],
        "documents": [document_out(meta) for meta in detail.documents],
        "topups": [topup_out(topup) for topup in detail.topups],
        "lead_bot_name": detail.lead_bot_name, "tainted": detail.tainted,
        "task_money": {task_id: task_money_out(money) for task_id, money in detail.task_money.items()},
        "upcoming_charges": [upcoming_out(charge) for charge in detail.upcoming],
        "counts": dict(detail.counts), "repeating": [recurring_out(rule, project.name) for rule in detail.repeating],
    }


def _service(request: Request) -> ProjectService:
    return request.app.state.projects


def _unreadable(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _refused(exc: ValueError) -> HTTPException:
    """A rename onto a name in use is a conflict (409). Any other broken rule is 422."""
    return HTTPException(status_code=409 if str(exc) == NAME_IN_USE_TEXT else 422, detail=str(exc))


def _undone(exc: TopUpUndone) -> HTTPException:
    """H4: an undone top-up stays undone, so changing or undoing it again is a conflict."""
    return HTTPException(status_code=409, detail=str(exc))


def _found_topup(topup: TopUp | None) -> dict[str, Any]:
    if topup is None:
        raise HTTPException(status_code=404, detail=TOPUP_NOT_FOUND_TEXT)
    return topup_out(topup)


async def refuse_general(request: Request, user_id: str, project_id: str | None) -> None:
    """For the routes that link a task, a note or a document to a project (H2, H11, H12): raises
    ``ValueError`` with the General sentence when ``project_id`` is General, as the tools do. They
    call it inside the ``try`` that already turns a ``ValueError`` into a 422."""
    await _service(request).ensure_linkable(user_id, project_id)


async def _project_answer(service: ProjectService, user_id: str, project_id: str) -> dict[str, Any]:
    """``ProjectOut`` for a project just created or changed, with its numbers."""
    detail = await service.detail(user_id, project_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)
    return project_out(detail.project, detail.numbers, detail.progress)


@projects_router.get("/api/projects")
async def list_projects(request: Request, user: CurrentUser, include_archived: bool = False):
    """The Projects tab: General hidden, archived projects only when asked for."""
    rows = await _service(request).list(user.id, include_archived=include_archived)
    return [project_out(project, numbers, progress) for project, numbers, progress in rows]


@projects_router.post("/api/projects", status_code=201, dependencies=[RequireOrigin])
async def create_project(body: ProjectIn, request: Request, user: CurrentUser):
    service = _service(request)
    try:
        project = await service.create(user.id, body.draft())
    except ValueError as exc:
        raise _unreadable(exc) from exc
    return await _project_answer(service, user.id, project.id)


@projects_router.get("/api/projects/{project_id}")
async def get_project(project_id: str, request: Request, user: CurrentUser):
    detail = await _service(request).detail(user.id, project_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)
    return project_detail_out(detail)


@projects_router.patch("/api/projects/{project_id}", dependencies=[RequireOrigin])
async def update_project(project_id: str, body: ProjectPatchIn, request: Request, user: CurrentUser):
    service = _service(request)
    try:
        project = await service.update(user.id, project_id, body.changes())
    except ValueError as exc:
        raise _refused(exc) from exc
    if project is None:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)
    return await _project_answer(service, user.id, project.id)


@projects_router.post("/api/projects/{project_id}/keep", dependencies=[RequireOrigin])
async def keep_project(project_id: str, request: Request, user: CurrentUser):
    """Keep: the user vouches for a project a bot made from web content (no tool
    can), so the "from web content" mark goes and later runs are no longer
    treated as having read outside content because of it."""
    service = _service(request)
    kept = await service.keep(user.id, project_id)
    if kept is None:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)
    return await _project_answer(service, user.id, kept.id)


class PinIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pinned: StrictBool


@projects_router.put("/api/projects/{project_id}/pin", dependencies=[RequireOrigin])
async def pin_project(project_id: str, body: PinIn, request: Request, user: CurrentUser):
    """Pin a project to the Board, or unpin it. General can't be pinned (422)."""
    service = _service(request)
    try:
        project = await service.set_pinned(user.id, project_id, body.pinned)
    except ValueError as exc:   # General
        raise _unreadable(exc) from exc
    if project is None:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)
    return await _project_answer(service, user.id, project.id)


@projects_router.delete("/api/projects/{project_id}", status_code=204, dependencies=[RequireOrigin])
async def delete_project(project_id: str, request: Request, user: CurrentUser) -> None:
    """H9: the expenses move to General; the tasks, notes and documents stay, unlinked."""
    try:
        deleted = await _service(request).delete(user.id, project_id)
    except ValueError as exc:   # General (H2)
        raise _unreadable(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)


@projects_router.put("/api/projects/{project_id}/budget", dependencies=[RequireOrigin])
async def set_project_budget(project_id: str, body: BudgetIn, request: Request, user: CurrentUser):
    """Set the total budget, or clear it with ``null`` (P3, H5). The history
    gets a "Budget set" row, and ``money_changed`` carries ``budget_set``."""
    service = _service(request)
    try:
        project = await service.set_budget(user.id, project_id, _amount(body.amount))
    except ValueError as exc:   # the amount, or General (H2)
        raise _unreadable(exc) from exc
    if project is None:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)
    return await _project_answer(service, user.id, project.id)


@projects_router.get("/api/projects/{project_id}/topups")
async def list_topups(project_id: str, request: Request, user: CurrentUser):
    """The top-up history, newest first, undone rows included."""
    topups = await _service(request).topups(user.id, project_id)
    if topups is None:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)
    return [topup_out(topup) for topup in topups]


@projects_router.post("/api/projects/{project_id}/topups", status_code=201, dependencies=[RequireOrigin])
async def add_topup(project_id: str, body: TopupIn, request: Request, user: CurrentUser):
    try:
        topup = await _service(request).add_topup(user.id, project_id, parse_amount(body.amount), body.source)
    except ValueError as exc:   # the amount, or a source too long once trimmed
        raise _unreadable(exc) from exc
    if topup is None:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)
    return topup_out(topup)


@projects_router.patch("/api/topups/{topup_id}", dependencies=[RequireOrigin])
async def edit_topup(topup_id: str, body: TopupEditIn, request: Request, user: CurrentUser):
    """``amount`` is the top-up's new amount; the store records the difference (H4)."""
    try:
        topup = await _service(request).edit_topup(user.id, topup_id, parse_amount(body.amount))
    except TopUpUndone as exc:   # a ValueError too, so it is caught first
        raise _undone(exc) from exc
    except ValueError as exc:    # the amount, or a total budget that is cleared or would go below 0
        raise _unreadable(exc) from exc
    return _found_topup(topup)


@projects_router.post("/api/topups/{topup_id}/undo", dependencies=[RequireOrigin])
async def undo_topup(topup_id: str, request: Request, user: CurrentUser):
    """The top-up and its edits leave the budget together (H4)."""
    try:
        topup = await _service(request).undo_topup(user.id, topup_id)
    except TopUpUndone as exc:   # a ValueError too, so it is caught first
        raise _undone(exc) from exc
    except ValueError as exc:    # a total budget that is cleared or would go below 0
        raise _unreadable(exc) from exc
    return _found_topup(topup)
