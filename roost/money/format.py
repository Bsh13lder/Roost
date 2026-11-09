"""Tool-result text for money. User and page text is escaped here, by its
producer (tool results reach the model raw)."""

from __future__ import annotations

import html
from decimal import Decimal

from roost.money.amounts import amount_text
from roost.money.models import EXPENSE_VOID, KIND_INCOME, Expense, MoneySummary, ProjectTotal


def escape(text: str) -> str:
    return html.escape(text, quote=True)


def money(amount: Decimal, currency: str) -> str:
    return f"{amount_text(amount)} {currency}"


def _marks(expense: Expense) -> str:
    void = " [void]" if expense.status == EXPENSE_VOID else ""
    starred = " [starred]" if expense.is_favorite else ""
    web = " [from web content]" if expense.tainted else ""
    income = " [money in]" if expense.kind == KIND_INCOME else ""
    return f"{income}{void}{starred}{web}"


def expense_line(expense: Expense, project: str) -> str:
    note = f" · {escape(expense.description)}" if expense.description else ""
    amount = money(expense.amount, expense.currency)
    return f"{expense.spent_at} · {escape(project)} · {amount}{note}{_marks(expense)} id={expense.id}"


def _limit(row: ProjectTotal) -> str:
    if row.budget is None or row.remaining is None:
        return ""
    left = (f"{money(row.remaining, row.currency)} left" if row.remaining >= 0
            else f"over by {money(-row.remaining, row.currency)}")
    return f" of a {money(row.budget, row.currency)} monthly limit, {left}"


def _row_line(row: ProjectTotal) -> str:
    also = "".join(f", also {money(total, code)}" for code, total in row.other_currencies.items())
    return f"- {escape(row.project)}: {money(row.spent, row.currency)}{_limit(row)}{also}"


def summary_text(summary: MoneySummary) -> str:
    head = f"{summary.month} — Total: {money(summary.total, summary.currency)} ({summary.expense_count} expenses)"
    rows = tuple(_row_line(row) for row in summary.by_project)
    others = tuple(f"Also {money(total, code)} (not in the total)"
                   for code, total in summary.other_currencies.items())
    money_in = ", ".join(money(total, code) for code, total in summary.money_in.items())
    received = (f"Money in: {money_in} (not in the total)",) if money_in else ()
    return "\n".join((head, *rows, *others, *received))
