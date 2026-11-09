"""The projects hub's numbers, in one place (design §2, H6–H8, H11).

These are pure functions over frozen records, with no database and no clock.
The caller passes the local month (``roost.money.months.current_month()``).
``spent_at`` is already a local day, so a month is a plain string range.

A **counted** expense is posted (not void) and in the project's currency.
The stores never return deleted rows, so those can't reach here. Spending in
another currency is listed apart and never converted (P4). The web adds
nothing up: every number here goes out as a string (``roost.money.summary``)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_FLOOR, Decimal
from types import MappingProxyType
from typing import Literal, Mapping, Sequence

from roost.constants import BUDGET_OVER_PERCENT, BUDGET_WARN_PERCENT
from roost.money.models import EXPENSE_POSTED, KIND_EXPENSE, KIND_INCOME, Expense, Project
from roost.money.months import month_bounds
from roost.tasks.models import Task
from roost.tasks.views import due_day, madrid_today

Tone = Literal["ok", "warn", "over"]

_ZERO = Decimal("0.00")
_HUNDRED = Decimal(100)
_DONE = "done"
_FAILED = "failed"
_CANCELLED = "cancelled"
_OPEN = ("todo", "in_progress")


@dataclass(frozen=True)
class BudgetLine:
    """One budget and its bar (H8).
    - ``remaining`` goes negative when over ("Over by …").
    - ``used_percent`` is spent ÷ budget × 100, rounded DOWN. It therefore
      reads 100 only once the budget is spent, and it may pass 100.
    - With no budget, ``remaining``, ``used_percent`` and ``tone`` are all ``None``."""

    budget: Decimal | None
    spent: Decimal
    remaining: Decimal | None
    used_percent: int | None
    tone: Tone | None


@dataclass(frozen=True)
class ProjectNumbers:
    currency: str
    total: BudgetLine                         # all-time counted spending against ``budget`` (top-ups included)
    month: BudgetLine                         # that local month's counted spending against ``monthly_budget``
    other_currencies: Mapping[str, Decimal]   # posted spending in other currencies, all time, never added in
    starred_total: Decimal                    # counted starred expenses, all time
    money_in: Mapping[str, Decimal] = MappingProxyType({})   # posted income per currency, all time; never in spending


@dataclass(frozen=True)
class TaskMoney:
    planned: Decimal | None                   # the task's ``allocated_budget``
    spent: Decimal
    left: Decimal | None                      # planned − spent; negative when over


@dataclass(frozen=True)
class Progress:
    done: int
    failed: int                               # finished too, but shown red
    total: int                                # every task except the cancelled ones
    overdue: int = 0                          # open tasks due before the local today
    open: int = 0                             # tasks to do or in progress
    steps_done: int = 0                       # steps of every task except the cancelled ones
    steps_total: int = 0
    planned_total: Decimal = _ZERO            # the open tasks' budget slices, in the project's currency


def counted(expense: Expense, currency: str) -> bool:
    """Posted, an expense (not income) and in ``currency``: the only rows a budget counts."""
    return expense.status == EXPENSE_POSTED and expense.kind == KIND_EXPENSE and expense.currency == currency


def spending(expenses: Sequence[Expense]) -> tuple[Expense, ...]:
    """The posted rows that are money out: what every "spent" sum is made of."""
    return tuple(e for e in expenses if e.status == EXPENSE_POSTED and e.kind == KIND_EXPENSE)


def money_in(expenses: Sequence[Expense]) -> Mapping[str, Decimal]:
    """Posted income per currency code (alphabetical), the one place money in is added up."""
    return per_currency(tuple(e for e in expenses if e.status == EXPENSE_POSTED and e.kind == KIND_INCOME))


def total_of(amounts: Sequence[Expense | Decimal]) -> Decimal:
    return sum((getattr(item, "amount", item) for item in amounts), _ZERO)


def per_currency(expenses: Sequence[Expense]) -> Mapping[str, Decimal]:
    """The sum per currency code, with the codes in alphabetical order, read-only."""
    codes = sorted({expense.currency for expense in expenses})
    return MappingProxyType({code: total_of(tuple(e for e in expenses if e.currency == code)) for code in codes})


def _used_percent(budget: Decimal, spent: Decimal) -> int:
    if budget <= 0:   # a budget whose top-ups were all undone: any spending uses it all up
        return 0 if spent <= 0 else BUDGET_OVER_PERCENT
    return int((spent * _HUNDRED / budget).to_integral_value(rounding=ROUND_FLOOR))


def _tone(used_percent: int) -> Tone:
    if used_percent >= BUDGET_OVER_PERCENT:
        return "over"
    return "warn" if used_percent >= BUDGET_WARN_PERCENT else "ok"


def budget_line(budget: Decimal | None, spent: Decimal) -> BudgetLine:
    if budget is None:
        return BudgetLine(budget=None, spent=spent, remaining=None, used_percent=None, tone=None)
    used = _used_percent(budget, spent)
    return BudgetLine(budget=budget, spent=spent, remaining=budget - spent, used_percent=used, tone=_tone(used))


def project_numbers(project: Project, expenses: Sequence[Expense], month: str) -> ProjectNumbers:
    """The numbers on a project's page and its row on the Projects tab.
    - ``month`` is a local month ("2026-10"); a bad one raises ``ValueError`` (``month_bounds``).
    - Expenses of other projects are ignored, so the caller may pass a wider list."""
    first, following = month_bounds(month)
    own = tuple(e for e in expenses if e.project_id == project.id)
    mine = tuple(e for e in own if counted(e, project.currency))
    this_month = tuple(e for e in mine if first <= e.spent_at < following)
    others = tuple(e for e in spending(own) if e.currency != project.currency)
    return ProjectNumbers(
        currency=project.currency,
        total=budget_line(project.budget, total_of(mine)),
        month=budget_line(project.monthly_budget, total_of(this_month)),
        other_currencies=per_currency(others),
        starred_total=total_of(tuple(e for e in mine if e.is_favorite)),
        money_in=money_in(own),
    )


def task_money(task: Task, expenses: Sequence[Expense], currency: str) -> TaskMoney:
    """Planned, spent and left for one task (H11), in ``currency`` (its project's).
    Spent is every counted expense linked to the task, whether or not its
    ``step_id`` is still one of the task's steps. An expense whose step was
    removed therefore stays on the task (LazyClaw's rule), and no row is rewritten."""
    spent = total_of(tuple(e for e in expenses if e.task_id == task.id and counted(e, currency)))
    planned = task.allocated_budget
    return TaskMoney(planned=planned, spent=spent, left=None if planned is None else planned - spent)


def _posted_elsewhere(task: Task, expenses: Sequence[Expense], currency: str) -> tuple[Expense, ...]:
    return tuple(e for e in spending(expenses) if e.task_id == task.id and e.currency != currency)


def task_other_currencies(task: Task, expenses: Sequence[Expense], currency: str) -> Mapping[str, Decimal]:
    """Posted spending on the task in currencies other than ``currency``, summed per code, never added in."""
    return per_currency(_posted_elsewhere(task, expenses, currency))


def step_other_currencies(task: Task, expenses: Sequence[Expense],
                          currency: str) -> Mapping[str, Mapping[str, Decimal]]:
    """The same per step id, for the steps that have any."""
    others = _posted_elsewhere(task, expenses, currency)
    per_step = {step.id: per_currency(tuple(e for e in others if e.step_id == step.id)) for step in task.steps}
    return MappingProxyType({step_id: sums for step_id, sums in per_step.items() if sums})


def step_spent(task: Task, expenses: Sequence[Expense], currency: str) -> Mapping[str, Decimal]:
    """What is spent on each of the task's steps (redesign P3), in ``currency``, by step id, in the
    steps' order: the counted expenses filed under that step. An expense whose step is gone counts
    on the task only (``task_money``), so the steps' sums may add up to less than the task's."""
    mine = tuple(e for e in expenses if e.task_id == task.id and counted(e, currency))
    return MappingProxyType({step.id: total_of(tuple(e for e in mine if e.step_id == step.id)) for step in task.steps})


def step_lines(task: Task, expenses: Sequence[Expense], currency: str) -> Mapping[str, BudgetLine]:
    """Each step's budget, spent and left with its bar (owner, 2026-10-26), in ``currency`` (the task's), by
    step id in the steps' order. A step budget set in another currency (the task moved since) reads as none."""
    spent = step_spent(task, expenses, currency)
    return MappingProxyType({
        step.id: budget_line(step.budget if step.budget_currency == currency else None, spent[step.id])
        for step in task.steps})


def progress(tasks: Sequence[Task], today: date | None = None) -> Progress:
    """Done / (all − cancelled). A failed task is finished but counted apart.
    ``today`` is the local day (default: now); an open task due before it is overdue."""
    day = today or madrid_today()
    kept = tuple(task for task in tasks if task.status != _CANCELLED)
    opened = tuple(task for task in kept if task.status in _OPEN)
    steps = tuple(step for task in kept for step in task.steps)
    return Progress(
        done=sum(1 for task in kept if task.status == _DONE), failed=sum(1 for task in kept if task.status == _FAILED),
        total=len(kept), open=len(opened), overdue=sum(1 for task in opened if _is_overdue(task, day)),
        steps_done=sum(1 for step in steps if step.done), steps_total=len(steps),
        planned_total=total_of(tuple(task.allocated_budget for task in opened if task.allocated_budget is not None)),
    )


def _is_overdue(task: Task, today: date) -> bool:
    due = due_day(task)
    return due is not None and due < today
