"""The Money tab's extra summary fields (Board redesign G8), pure.

Every number is added here and nowhere else: the web only formats what it is sent. Nothing adds across
currencies. ``change_percent`` and the top project use the main currency only; limits are each in their
project's own currency; Today and Coming up are listed per currency."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from types import MappingProxyType
from typing import Mapping, Sequence

from roost.constants import PROJECT_STATUSES, UPCOMING_CHARGES_DAYS
from roost.money.models import Expense, MoneySummary, Project, ProjectTotal
from roost.money.project_store import is_general
from roost.money.recurring import UpcomingCharge
from roost.projects.numbers import BudgetLine, budget_line, counted, per_currency, spending, total_of

_ACTIVE = PROJECT_STATUSES[0]
_HUNDRED = Decimal(100)
_NO_AMOUNTS: Mapping[str, Decimal] = MappingProxyType({})


@dataclass(frozen=True)
class TodayTotals:
    day: str
    count: int
    totals: Mapping[str, Decimal]


@dataclass(frozen=True)
class PreviousMonth:
    month: str
    total: Decimal


@dataclass(frozen=True)
class LimitItem:
    project_id: str
    project: str
    currency: str
    amount: Decimal            # the size of the overage or of what is left: never signed
    over: bool
    tone: str


@dataclass(frozen=True)
class Limits:
    over_count: int
    items: tuple[LimitItem, ...]


@dataclass(frozen=True)
class TopProject:
    project_id: str
    project: str
    color: str
    currency: str
    spent: Decimal
    share_percent: int


@dataclass(frozen=True)
class NextCharge:
    note: str | None
    day: str
    amount: Decimal
    currency: str


@dataclass(frozen=True)
class ComingUp:
    days: int
    count: int
    totals: Mapping[str, Decimal]
    next: NextCharge | None


@dataclass(frozen=True)
class PinnedProject:
    project_id: str
    project: str
    color: str
    currency: str
    spent_month: Decimal
    month: BudgetLine
    total: BudgetLine


@dataclass(frozen=True)
class BoardSummary:
    today: TodayTotals
    previous: PreviousMonth | None
    change_percent: int | None
    limits: Limits
    top_project: TopProject | None
    coming_up: ComingUp
    pinned_projects: tuple[PinnedProject, ...]
    pinned_expenses: tuple[Expense, ...]


def today_totals(day: str, expenses: Sequence[Expense]) -> TodayTotals:
    """The spending (void rows and money in left out) of one local day, per currency."""
    spent = tuple(e for e in spending(expenses) if e.spent_at == day)
    return TodayTotals(day=day, count=len(spent), totals=per_currency(spent))


def _percent(part: Decimal, whole: Decimal) -> int:
    return int((part * _HUNDRED / whole).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def previous_month(month: str, expenses: Sequence[Expense], currency: str,
                   this_total: Decimal) -> tuple[PreviousMonth | None, int | None]:
    """Last month's total in the main ``currency`` and how this month compares (rounded percent, signed).
    Both are ``None`` when last month spent nothing in that currency."""
    total = total_of(tuple(e for e in spending(expenses) if e.currency == currency))
    if total <= 0:
        return None, None
    return PreviousMonth(month=month, total=total), _percent(this_total - total, total)


def limits_of(projects: Sequence[Project], rows: Mapping[str, ProjectTotal]) -> Limits:
    """Active projects with a monthly limit, the worst first: over by the most, then the least left.
    Amounts compare only to order the list; no two are added."""
    items = []
    for project in projects:
        row = rows.get(project.id)
        if project.status != _ACTIVE or project.monthly_budget is None or row is None:
            continue
        remaining = row.month.remaining if row.month.remaining is not None else Decimal(0)
        items.append(LimitItem(project_id=project.id, project=project.name, currency=project.currency,
                               amount=abs(remaining), over=remaining < 0, tone=row.month.tone or "ok"))
    over = sorted((i for i in items if i.over), key=lambda i: (-i.amount, i.project.casefold()))
    left = sorted((i for i in items if not i.over), key=lambda i: (i.amount, i.project.casefold()))
    return Limits(over_count=len(over), items=(*over, *left))


def top_project(rows: Sequence[ProjectTotal], general_ids: frozenset[str], colors: Mapping[str, str],
                currency: str, month_total: Decimal) -> TopProject | None:
    """The biggest spender of the month in the main currency, General left out."""
    candidates = [r for r in rows if r.currency == currency and r.project_id not in general_ids and r.spent > 0]
    if not candidates or month_total <= 0:
        return None
    best = max(candidates, key=lambda r: (r.spent, r.project.casefold()))
    return TopProject(project_id=best.project_id, project=best.project, color=colors.get(best.project_id, ""),
                      currency=best.currency, spent=best.spent, share_percent=_percent(best.spent, month_total))


def coming_up(charges: Sequence[UpcomingCharge]) -> ComingUp:
    """The next ``UPCOMING_CHARGES_DAYS`` days' repeating charges (soonest first), per currency."""
    first = charges[0] if charges else None
    nxt = None if first is None else NextCharge(first.note, first.day, first.amount, first.currency)
    totals: Mapping[str, Decimal] = MappingProxyType({
        code: sum((c.amount for c in charges if c.currency == code), Decimal("0.00"))
        for code in sorted({c.currency for c in charges})})
    return ComingUp(days=UPCOMING_CHARGES_DAYS, count=len(charges), totals=totals, next=nxt)


def pinned_projects(projects: Sequence[Project], rows: Mapping[str, ProjectTotal],
                    totals: Mapping[str, BudgetLine], empty_month: Mapping[str, BudgetLine]) -> tuple[PinnedProject, ...]:
    """The pinned, active projects in pin order, even with no spending this month."""
    pinned = sorted((p for p in projects if p.pinned and p.status == _ACTIVE), key=lambda p: (p.pinned_at or "", p.id))
    out = []
    for project in pinned:
        row = rows.get(project.id)
        month = row.month if row is not None else empty_month[project.id]
        out.append(PinnedProject(project_id=project.id, project=project.name, color=project.color,
                                 currency=project.currency, spent_month=month.spent, month=month,
                                 total=totals[project.id]))
    return tuple(out)


def prior_month(month: str) -> str:
    """The month before ``month`` ("2026-01" gives "2025-12")."""
    year, number = (int(part) for part in month.split("-"))
    return (date(year, number, 1) - timedelta(days=1)).strftime("%Y-%m")


def needs_all_time(projects: Sequence[Project], summary: MoneySummary) -> tuple[Project, ...]:
    """The projects whose total-budget bar the Money tab draws: shown in the month, or pinned, with a budget."""
    shown = {row.project_id for row in summary.by_project}
    return tuple(p for p in projects if p.budget is not None and (p.id in shown or (p.pinned and p.status == _ACTIVE)))


def all_time_line(project: Project, expenses: Sequence[Expense]) -> BudgetLine:
    """The total budget (top-ups included) against every counted expense of the project, all time."""
    return budget_line(project.budget, total_of(tuple(e for e in expenses if counted(e, project.currency))))


def build_board(summary: MoneySummary, projects: Sequence[Project], all_time: Mapping[str, BudgetLine], *,
                day: str, today_expenses: Sequence[Expense], previous: str, previous_expenses: Sequence[Expense],
                charges: Sequence[UpcomingCharge], starred: Sequence[Expense]) -> MoneySummary:
    """``summary`` with its rows' total budget lines and the Money tab's fields. ``all_time`` is by project id."""
    def total_line(row: ProjectTotal) -> BudgetLine:
        return all_time.get(row.project_id) or budget_line(None, row.month.spent)

    with_totals = tuple(replace(row, total=total_line(row)) for row in summary.by_project)
    rows = {row.project_id: row for row in with_totals}
    empty = {p.id: budget_line(p.monthly_budget, Decimal("0.00")) for p in projects}
    totals = {p.id: all_time.get(p.id) or budget_line(None, Decimal("0.00")) for p in projects}
    before, change = previous_month(previous, previous_expenses, summary.currency, summary.total)
    general = frozenset(p.id for p in projects if is_general(p))
    board = BoardSummary(
        today=today_totals(day, today_expenses), previous=before, change_percent=change,
        limits=limits_of(projects, rows),
        top_project=top_project(with_totals, general, {p.id: p.color for p in projects}, summary.currency,
                                summary.total),
        coming_up=coming_up(charges), pinned_projects=pinned_projects(projects, rows, totals, empty),
        pinned_expenses=tuple(starred))
    return replace(summary, by_project=with_totals, board=board)
