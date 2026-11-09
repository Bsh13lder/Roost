"""The task drawer's data and the quick-add line over HTTP (redesign P3).

- ``GET /api/tasks/{id}``: one task (any status) with its money: the slice, what is spent and what is
  left, in its project's currency, and what is spent on each step (``roost.projects.numbers``; the web
  adds nothing up), plus every expense filed under it. A task in no project counts in General's currency
  (owner, 2026-10-26), and ``steps_money`` holds each step's budget, spent, left and bar.
- ``POST /api/tasks/parse-many``: a pasted list (``roost.tasks.paste``): each line read like a quick line, an
  indented line a step of the task above. It changes nothing; the web confirms "Add N tasks?" and creates them.
- ``POST /api/tasks/parse``: how the server reads a quick-add line (``roost.tasks.quick_line``). It
  changes nothing; the web adds the task from this reading. A project page passes ``project_id``.
Another user's task is a 404; another user's project reads as no such project."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Literal, Mapping

from fastapi import APIRouter, HTTPException, Request
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from roost.constants import DEFAULT_CURRENCY, MAX_RECORD_ID_LENGTH, PASTE_MAX_LENGTH, QUICK_LINE_MAX_LENGTH, MAX_STEP_TITLE_LENGTH
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.gateway.routes.projects import task_money_out
from roost.money.amounts import amount_text
from roost.money.models import Expense, Project
from roost.money.project_store import is_general
from roost.money.summary import expense_row
from roost.projects.numbers import (
    BudgetLine, budget_line, step_lines, step_other_currencies, step_spent, task_money, task_other_currencies,
)
from roost.tasks.format import task_out
from roost.tasks.models import Task
from roost.tasks.paste import split_paste
from roost.tasks.quick_line import KEEP_MAX_LENGTH, KEEP_MAX_WORDS, QuickLine, quick_line_out, read_quick_line

detail_router = APIRouter(prefix="/api/tasks", tags=["tasks"])
TASK_NOT_FOUND_TEXT = "Task not found"
QUICK_KINDS = ("date", "project", "budget", "priority", "star", "estimate", "reminder", "repeat", "assignee", "tag")


class QuickLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=QUICK_LINE_MAX_LENGTH)
    project_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)    # a project page's own
    skip: list[Literal["date", "project", "budget", "priority", "star", "estimate", "reminder", "repeat",
                       "assignee", "tag"]] = Field(default_factory=list, max_length=len(QUICK_KINDS))
    keep: list[Annotated[str, Field(max_length=KEEP_MAX_LENGTH)]] = Field(     # words of cancelled chips
        default_factory=list, max_length=KEEP_MAX_WORDS)
    default_due: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")   # a column's day, if the line names none

    @field_validator("default_due")
    @classmethod
    def _real_day(cls, value: str | None) -> str | None:
        if value is not None:
            date.fromisoformat(value)    # ValueError -> 422
        return value


class PasteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=PASTE_MAX_LENGTH)
    project_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)


PASTE_BOT_TEXT = "Line {number}: hand a task to a bot one task at a time, from its own line."
PASTE_LINE_TEXT = "Line {number}: {problem}"
EMPTY_PASTE_TEXT = "Nothing to add: paste a list with one task on each line."


def _line_problem(line: QuickLine) -> str | None:
    if line.assignee_words:
        return PASTE_BOT_TEXT
    reasons = (line.project_question, line.budget_problem, line.repeat_problem, line.assignee_question)
    found = next((reason for reason in reasons if reason), None)
    return found if found else (None if line.title else "Give the task a title.")


def _sums(sums: Mapping[str, Decimal]) -> dict[str, str]:
    return {code: amount_text(amount) for code, amount in sums.items()}


def _line_out(line: BudgetLine) -> dict[str, Any]:
    """One step's ``StepMoneyOut``: planned, spent and left as strings, with the bar's percent and tone."""
    return {"planned": None if line.budget is None else amount_text(line.budget), "spent": amount_text(line.spent),
            "left": None if line.remaining is None else amount_text(line.remaining),
            "used_percent": line.used_percent, "tone": line.tone}


def _money_currency(task: Task, projects: Mapping[str, Project]) -> str:
    """The task's project's currency, or General's for a task in no project (where its expenses go)."""
    if task.project_id is not None and task.project_id in projects:
        return projects[task.project_id].currency
    general = next((project for project in projects.values() if is_general(project)), None)
    return general.currency if general is not None else DEFAULT_CURRENCY


def _money_out(task: Task, currency: str, expenses: tuple[Expense, ...]) -> dict[str, Any]:
    """``TaskDetailMoneyOut``, in ``currency`` (``_money_currency``)."""
    spent_by_step = step_spent(task, expenses, currency)
    money = task_money(task, expenses, currency)
    line = budget_line(money.planned, money.spent)   # the one rule every budget bar uses
    return {**task_money_out(money), "used_percent": line.used_percent, "tone": line.tone, "currency": currency,
            "steps": {step_id: amount_text(amount) for step_id, amount in spent_by_step.items()},
            "steps_money": {step_id: _line_out(one) for step_id, one in step_lines(task, expenses, currency).items()},
            "other_currencies": _sums(task_other_currencies(task, expenses, currency)),
            "steps_other_currencies": {step_id: _sums(sums) for step_id, sums in
                                       step_other_currencies(task, expenses, currency).items()}}


@detail_router.get("/{task_id}")
async def get_task(task_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    task = await request.app.state.tasks.get(user.id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=TASK_NOT_FOUND_TEXT)
    money = request.app.state.money
    projects = {project.id: project for project in await money.projects(user.id)}
    expenses = await money.for_task(user.id, task.id)
    return {**task_out(task), "money": _money_out(task, _money_currency(task, projects), expenses),
            "expenses": [expense_row(expense, projects.get(expense.project_id)) for expense in expenses]}


@detail_router.post("/parse", dependencies=[RequireOrigin])
async def parse_quick_line(body: QuickLineIn, request: Request, user: CurrentUser) -> dict[str, Any]:
    line = await read_quick_line(request.app.state.projects, user.id, body.text, project_id=body.project_id,
                                 skip=frozenset(body.skip), bots=await request.app.state.bots.list(user.id),
                                 keep=body.keep, default_due=body.default_due)
    return quick_line_out(line)


@detail_router.post("/parse-many", dependencies=[RequireOrigin])
async def parse_pasted_list(body: PasteIn, request: Request, user: CurrentUser) -> dict[str, Any]:
    try:
        items = split_paste(body.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not items:
        raise HTTPException(status_code=422, detail=EMPTY_PASTE_TEXT)
    bots = await request.app.state.bots.list(user.id)
    tasks, problem = [], None
    for number, item in enumerate(items, start=1):
        line = await read_quick_line(request.app.state.projects, user.id, item.line, project_id=body.project_id,
                                     bots=bots)
        why = _line_problem(line)
        if why and problem is None:
            problem = PASTE_LINE_TEXT.format(number=number, problem=why.format(number=number))
        steps = [step[:MAX_STEP_TITLE_LENGTH] for step in item.steps]
        tasks.append({**quick_line_out(line), "steps": steps})
    return {"count": len(tasks), "tasks": tasks, "ready": problem is None, "problem": problem}
