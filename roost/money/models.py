"""Money domain model (M1 D7, projects hub H1). A ``Project`` is a row of
``money_projects``, LazyClaw's project: a named budget bucket an expense
belongs to. Loose expenses go to the General project."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, Mapping

from roost.constants import (
    CURRENCY_PATTERN, DEFAULT_CURRENCY, DEFAULT_PROJECT_COLOR, MAX_CATEGORY_NAME_LENGTH, PROJECT_COLORS,
    PROJECT_STATUSES,
)
from roost.money.amounts import parse_amount


@dataclass(frozen=True)
class Project:
    id: str
    user_id: str
    name: str
    budget: Decimal | None        # the total budget; it already includes top-ups (LazyClaw's meaning)
    currency: str
    created_at: str
    updated_at: str
    created_by_bot: str | None
    tainted: bool
    color: str                    # one of PROJECT_COLORS
    start_date: str | None        # YYYY-MM-DD
    due_date: str | None          # YYYY-MM-DD
    monthly_budget: Decimal | None
    lead_bot_id: str | None       # one of the user's bots (H15); cleared when that bot is retired
    status: str                   # "active" | "archived"
    pinned: bool = False          # pinned on the Board (v22)
    pinned_at: str | None = None  # when: the pin order


# No apostrophes in these texts: the tools path escapes them for the model.
PROJECT_NAME_TEXT = f"A project needs a name of at most {MAX_CATEGORY_NAME_LENGTH} characters."
CURRENCY_TEXT = "A currency is a three-letter code like EUR."
# The palette, listed (the bots' tools and the routes reuse it, Tasks 7 and 8). It starts
# "A project colour is one of #64748b, " and names the "palette", as the tests of both tasks expect.
COLOR_TEXT = f"A project colour is one of {', '.join(PROJECT_COLORS)} (the palette)."
STATUS_TEXT = "A project is either active or archived."
DATE_TEXT = "A project date is a day written YYYY-MM-DD."
LEAD_BOT_TEXT = "The lead bot must be one of your bots."
DATES_TEXT = "The due date can't be before the start date."


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _name(value: object) -> str:
    name = _text(value)
    if not name or len(name) > MAX_CATEGORY_NAME_LENGTH:
        raise ValueError(PROJECT_NAME_TEXT)
    return name


def _currency(value: object) -> str:
    code = _text(value).upper()
    if re.fullmatch(CURRENCY_PATTERN, code) is None:
        raise ValueError(CURRENCY_TEXT)
    return code


def _color(value: object) -> str:
    color = _text(value).lower()
    if color not in PROJECT_COLORS:
        raise ValueError(COLOR_TEXT)
    return color


def _status(value: object) -> str:
    if value not in PROJECT_STATUSES:
        raise ValueError(STATUS_TEXT)
    return str(value)


def _day(value: object) -> str | None:
    """A plain ``YYYY-MM-DD`` day. ``None`` or a blank string clears it."""
    text = _text(value)
    if value is None or (isinstance(value, str) and not text):
        return None
    try:
        day = date.fromisoformat(text)
    except ValueError:
        raise ValueError(DATE_TEXT) from None
    if day.isoformat() != text:   # Python also reads "20261231" or week dates; only the plain form is kept
        raise ValueError(DATE_TEXT)
    return text


def _amount(value: object) -> Decimal | None:
    """Positive, at most 2 decimals, at most ``MAX_EXPENSE_AMOUNT``. ``None`` clears it."""
    return None if value is None else parse_amount(str(value))


def _lead_bot(value: object) -> str | None:
    if value is None:
        return None
    bot_id = _text(value)
    if not bot_id:
        raise ValueError(LEAD_BOT_TEXT)
    return bot_id


def check_dates(start_date: str | None, due_date: str | None) -> None:
    """The due date can't come before the start date. Both are tidied ``YYYY-MM-DD`` days, so
    comparing the texts compares the days. A project with only one of them has nothing to compare."""
    if start_date and due_date and due_date < start_date:
        raise ValueError(DATES_TEXT)


_CHECKS: Mapping[str, Callable[[object], object]] = MappingProxyType({
    "name": _name, "currency": _currency, "budget": _amount, "monthly_budget": _amount, "color": _color,
    "start_date": _day, "due_date": _day, "lead_bot_id": _lead_bot, "status": _status,
})


def _checked(values: Mapping[str, object]) -> dict[str, object]:
    """Each value checked and tidied (stripped, upper- or lower-cased, to cents)."""
    return {field: _CHECKS[field](value) for field, value in values.items()}


@dataclass(frozen=True)
class ProjectDraft:
    """A new project. Every field is checked and tidied while the draft is
    built, so a store never writes a bad value. ``budget`` is the total budget
    and ``monthly_budget`` the monthly limit; a project may have either, both
    or neither (P3)."""

    name: str
    currency: str = DEFAULT_CURRENCY
    budget: Decimal | None = None
    monthly_budget: Decimal | None = None
    color: str = DEFAULT_PROJECT_COLOR
    start_date: str | None = None
    due_date: str | None = None
    lead_bot_id: str | None = None

    def __post_init__(self) -> None:
        tidy = _checked({field.name: getattr(self, field.name) for field in fields(self)})
        check_dates(tidy["start_date"], tidy["due_date"])
        for name, value in tidy.items():
            object.__setattr__(self, name, value)   # once, while the frozen draft is being built


PROJECT_PATCHABLE = frozenset({"name", "color", "start_date", "due_date", "monthly_budget", "lead_bot_id", "status",
                               "currency"})


@dataclass(frozen=True)
class ProjectPatch:
    """What an update changes, checked and tidied. The total budget is not
    here: it moves only through ``set_budget`` and top-ups, which write its
    history (H4)."""

    changes: Mapping[str, object]

    def __post_init__(self) -> None:
        unknown = sorted(set(self.changes) - PROJECT_PATCHABLE)
        if unknown:
            raise ValueError(f"Projects have no field {', '.join(unknown)}.")
        tidy = _checked(self.changes)
        if "start_date" in tidy and "due_date" in tidy:
            check_dates(tidy["start_date"], tidy["due_date"])    # one of them alone is checked against the project
        object.__setattr__(self, "changes", MappingProxyType(tidy))


TOPUP_CREDIT = "credit"   # a top-up: money added to the total budget ("Top-up")
TOPUP_EDIT = "edit"       # a change: to a top-up when topup_id is set ("Top-up changed"), else "Budget set"


@dataclass(frozen=True)
class TopUp:
    """One row of a project's budget history (``money_topups``, H4)."""

    id: str
    project_id: str
    amount: Decimal               # signed for an edit: the difference
    currency: str
    source: str | None
    kind: str                     # TOPUP_CREDIT | TOPUP_EDIT
    topup_id: str | None          # the credit an edit changes; None for a credit or a "Budget set" row
    undone: bool
    created_at: str
    created_by_bot: str | None
    tainted: bool
    taken_back: bool = False      # a credit that clearing the total budget took back (H5); set by the history read


ExpenseStatus = Literal["posted", "void"]
EXPENSE_POSTED: ExpenseStatus = "posted"     # counted in the sums
EXPENSE_VOID: ExpenseStatus = "void"         # still shown, never summed (H6)
EXPENSE_STATUSES: tuple[ExpenseStatus, ...] = (EXPENSE_POSTED, EXPENSE_VOID)

ExpenseKind = Literal["expense", "income"]
KIND_EXPENSE: ExpenseKind = "expense"        # money out: counted as spent
KIND_INCOME: ExpenseKind = "income"          # money in: shown and totalled apart, never counted as spent
EXPENSE_KINDS: tuple[ExpenseKind, ...] = (KIND_EXPENSE, KIND_INCOME)


@dataclass(frozen=True)
class Expense:
    id: str
    user_id: str
    project_id: str           # money_projects.id, as in LazyClaw
    amount: Decimal
    currency: str
    description: str | None   # the note: "lunch"
    vendor: str | None
    spent_at: str             # YYYY-MM-DD, a local day
    status: ExpenseStatus
    created_at: str
    updated_at: str
    created_by_bot: str | None
    tainted: bool
    task_id: str | None = None      # the task it was spent on (a task of any status)
    step_id: str | None = None      # one of that task's steps; an id no longer on the task counts at task level
    is_favorite: bool = False       # starred
    imported_from: str | None = None   # "lazyclaw" for a row an import made (import_links); read-only
    recurring_id: str | None = None    # the repeating rule that made it (Task 12)
    occurrence: str | None = None      # YYYY-MM-DD: which occurrence of that rule it is
    kind: ExpenseKind = KIND_EXPENSE   # "income" is money in (v21)
    tags: tuple[str, ...] = ()         # sealed (v27); a bot's expense carries bot:<slug> and its topic tags


@dataclass(frozen=True)
class ExpenseDraft:
    project_id: str
    amount: Decimal
    currency: str = DEFAULT_CURRENCY
    description: str | None = None
    vendor: str | None = None
    spent_at: str = ""
    task_id: str | None = None
    step_id: str | None = None
    is_favorite: bool = False
    recurring_id: str | None = None
    occurrence: str | None = None
    kind: ExpenseKind = KIND_EXPENSE
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in EXPENSE_KINDS:
            raise ValueError("An expense is either an expense or income.")
        object.__setattr__(self, "currency", _currency(self.currency))   # "usd" is kept as "USD"


EXPENSE_PATCHABLE = frozenset({
    "project_id", "amount", "currency", "description", "vendor", "spent_at", "task_id", "step_id", "is_favorite",
    "status",
})


def _check_values(changes: Mapping[str, Any]) -> None:
    """The two plaintext values a patch could get wrong. No apostrophes in these
    messages: the tools path escapes them for the model."""
    if "status" in changes and changes["status"] not in EXPENSE_STATUSES:
        raise ValueError("The status of an expense is posted or void.")
    if "is_favorite" in changes and not isinstance(changes["is_favorite"], bool):
        raise ValueError("Starred is yes or no.")


@dataclass(frozen=True)
class ExpensePatch:
    changes: Mapping[str, Any]

    def __post_init__(self) -> None:
        unknown = sorted(set(self.changes) - EXPENSE_PATCHABLE)
        if unknown:
            raise ValueError(f"Expenses have no field {', '.join(unknown)}.")
        _check_values(self.changes)
        tidy = {**self.changes, **({"currency": _currency(self.changes["currency"])} if "currency" in self.changes else {})}
        object.__setattr__(self, "changes", MappingProxyType(tidy))


if TYPE_CHECKING:   # roost/projects/numbers.py imports this module; BudgetLine is named here for the annotation only
    from roost.money.board_summary import BoardSummary
    from roost.projects.numbers import BudgetLine


@dataclass(frozen=True)
class ProjectTotal:
    """One project's row in a month summary (H7, H8), in the project's own
    currency. ``month`` is its counted spending that month against its
    monthly limit. ``other_currencies`` is what it spent in any other
    currency, never added in. ``spent``, ``budget`` and ``remaining`` read the
    month line, as the Money tab has always shown them."""

    project: str
    project_id: str
    currency: str
    month: BudgetLine
    other_currencies: Mapping[str, Decimal]
    money_in: Mapping[str, Decimal] = MappingProxyType({})   # that month's income per currency, never in `spent`
    total: BudgetLine | None = None   # the total budget against all-time spending (the Board's side column)
    color: str = ""
    pinned: bool = False

    @property
    def spent(self) -> Decimal:
        return self.month.spent

    @property
    def budget(self) -> Decimal | None:
        return self.month.budget

    @property
    def remaining(self) -> Decimal | None:
        return self.month.remaining


@dataclass(frozen=True)
class MoneySummary:
    month: str
    currency: str
    total: Decimal
    expense_count: int
    by_project: tuple[ProjectTotal, ...]
    other_currencies: Mapping[str, Decimal]
    money_in: Mapping[str, Decimal] = MappingProxyType({})   # that month's income per currency
    board: BoardSummary | None = None                        # the Money tab's extra fields (GET /api/money/summary)
