# SPDX-License-Identifier: MIT
# Adapted from LazyClaw lazyclaw/budgets/store.py @ 21e1002 (spending_report semantics), for Roost
"""Month totals by project (M1 D7, hub H7/H8).

- Each project row is in the project's own currency, against its monthly
  limit, with its other currencies listed apart and never converted.
- The top-level total stays the month's spending in the default currency
  (every posted EUR expense, whatever its project), for compatibility.
- A void expense is shown in lists but never summed.
- The wire sends every amount as a string: the web never adds them."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from roost.constants import DEFAULT_CURRENCY, PROJECT_STATUSES
from roost.money.amounts import amount_text
from roost.money.board_summary import BoardSummary
from roost.money.models import EXPENSE_POSTED, Expense, MoneySummary, Project, ProjectTotal
from roost.projects.numbers import BudgetLine, budget_line, counted, money_in, per_currency, spending, total_of

_ACTIVE = PROJECT_STATUSES[0]


def _project_total(project: Project, posted: tuple[Expense, ...]) -> ProjectTotal:
    own = tuple(e for e in posted if e.project_id == project.id)
    outgoing = spending(own)
    return ProjectTotal(
        project=project.name, project_id=project.id, currency=project.currency,
        month=budget_line(project.monthly_budget, total_of(tuple(e for e in own if counted(e, project.currency)))),
        other_currencies=per_currency(tuple(e for e in outgoing if e.currency != project.currency)),
        money_in=money_in(own), color=project.color, pinned=project.pinned,
    )


def _shown(project: Project, row: ProjectTotal) -> bool:
    """A project that spent this month (in any currency), or an active one with
    a monthly limit. An archived project's empty month is not news."""
    spent = row.spent > 0 or bool(row.other_currencies) or bool(row.money_in)
    return spent or (project.monthly_budget is not None and project.status == _ACTIVE)


def summarize(month: str, projects: tuple[Project, ...], expenses: tuple[Expense, ...]) -> MoneySummary:
    posted = tuple(e for e in expenses if e.status == EXPENSE_POSTED)
    outgoing = spending(posted)
    totals = tuple((project, _project_total(project, posted)) for project in projects)
    rows = tuple(row for project, row in totals if _shown(project, row))
    return MoneySummary(
        month=month, currency=DEFAULT_CURRENCY,
        total=total_of(tuple(e for e in outgoing if e.currency == DEFAULT_CURRENCY)),
        expense_count=len(outgoing), by_project=tuple(sorted(rows, key=lambda r: (-r.spent, r.project.casefold()))),
        other_currencies=per_currency(tuple(e for e in outgoing if e.currency != DEFAULT_CURRENCY)),
        money_in=money_in(posted),
    )


def _optional(amount: Decimal | None) -> str | None:
    return None if amount is None else amount_text(amount)


def amounts_out(amounts: Mapping[str, Decimal]) -> dict[str, str]:
    return {code: amount_text(total) for code, total in amounts.items()}


def budget_line_out(line: BudgetLine) -> dict[str, Any]:
    """``BudgetLineOut``: the amounts as strings, plus the bar's percent and tone (H8)."""
    return {"budget": _optional(line.budget), "spent": amount_text(line.spent), "remaining": _optional(line.remaining),
            "used_percent": line.used_percent, "tone": line.tone}


def project_total_out(row: ProjectTotal) -> dict[str, Any]:
    """One ``by_project`` row. ``spent``, ``budget`` and ``remaining`` repeat the
    month line for the Money tab as it is today; ``month`` adds the bar."""
    return {
        "project": row.project, "project_id": row.project_id, "currency": row.currency,
        "spent": amount_text(row.spent), "budget": _optional(row.budget), "remaining": _optional(row.remaining),
        "month": budget_line_out(row.month), "other_currencies": amounts_out(row.other_currencies),
        "money_in": amounts_out(row.money_in), "color": row.color, "pinned": row.pinned,
        "total": None if row.total is None else budget_line_out(row.total),
    }


def summary_out(summary: MoneySummary, projects: Mapping[str, Project] | None = None) -> dict[str, Any]:
    """``projects`` (by id) names the projects behind the Money tab's starred expense rows."""
    out = {
        "month": summary.month, "currency": summary.currency, "total": amount_text(summary.total),
        "expense_count": summary.expense_count, "by_project": [project_total_out(row) for row in summary.by_project],
        "other_currencies": amounts_out(summary.other_currencies), "money_in": amounts_out(summary.money_in),
    }
    if summary.board is not None:
        out.update(board_out(summary.board, projects or {}))
    return out


def expense_row(expense: Expense, project: Project | None, repeat: str | None = None) -> dict[str, Any]:
    """An expense row for the Board: ``project_color`` is its project's colour (the row's dot)."""
    if project is None:
        return {**expense_out(expense, "", repeat=repeat), "project_color": None}
    return {**expense_out(expense, project.name, project_tainted=project.tainted, repeat=repeat),
            "project_color": project.color}


def expense_out(expense: Expense, project: str, *, project_tainted: bool = False,
                repeat: str | None = None) -> dict[str, Any]:
    """``tainted`` marks the row "from web content" when the expense OR the
    project name it shows was web-made. Either one taints a run that lists
    it, so the Board must offer Keep for both. ``repeat`` is the cadence of the rule that made it (G9)."""
    return {
        "id": expense.id, "project": project, "project_id": expense.project_id, "task_id": expense.task_id,
        "step_id": expense.step_id, "amount": amount_text(expense.amount), "currency": expense.currency,
        "description": expense.description, "vendor": expense.vendor, "spent_at": expense.spent_at,
        "status": expense.status, "is_favorite": expense.is_favorite, "created_at": expense.created_at,
        "created_by_bot": expense.created_by_bot, "tainted": expense.tainted or project_tainted,
        "imported_from": expense.imported_from, "recurring_id": expense.recurring_id,
        "kind": expense.kind, "repeat": repeat, "tags": list(expense.tags),
    }


def board_out(board: BoardSummary, projects: Mapping[str, Project]) -> dict[str, Any]:
    """The Money tab's extra fields (G8). Amounts are strings; the web adds nothing."""
    previous = board.previous
    nxt = board.coming_up.next
    top = board.top_project
    return {
        "today": {"day": board.today.day, "count": board.today.count, "totals": amounts_out(board.today.totals)},
        "previous": None if previous is None else {"month": previous.month, "total": amount_text(previous.total)},
        "change_percent": board.change_percent,
        "limits": {"over_count": board.limits.over_count, "items": [
            {"project_id": i.project_id, "project": i.project, "currency": i.currency, "amount": amount_text(i.amount),
             "over": i.over, "tone": i.tone} for i in board.limits.items]},
        "top_project": None if top is None else {
            "project_id": top.project_id, "project": top.project, "color": top.color, "currency": top.currency,
            "spent": amount_text(top.spent), "share_percent": top.share_percent},
        "coming_up": {"days": board.coming_up.days, "count": board.coming_up.count,
                      "totals": amounts_out(board.coming_up.totals),
                      "next": None if nxt is None else {"note": nxt.note, "day": nxt.day,
                                                        "amount": amount_text(nxt.amount), "currency": nxt.currency}},
        "pinned_projects": [
            {"project_id": p.project_id, "project": p.project, "color": p.color, "currency": p.currency,
             "spent_month": amount_text(p.spent_month), "month": budget_line_out(p.month),
             "total": budget_line_out(p.total)} for p in board.pinned_projects],
        "pinned_expenses": [expense_row(e, projects.get(e.project_id)) for e in board.pinned_expenses],
    }
