"""Money reports, pure (Task 14, design §7): the monthly trend and the CSV export.

- ``trend`` sums each month per currency (a currency is never added to another) and leaves voids out, as every
  sum does. A month with nothing is listed with no totals, so a chart keeps its months.
- ``csv_text`` writes one row per expense, amounts as exact decimal text. A spreadsheet runs a cell that starts
  with ``= + - @`` (or a tab or carriage return) as a formula, so such a text cell is written with a leading
  ``'`` (the formula guard)."""

from __future__ import annotations

import csv
import io
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence

from roost.money.amounts import amount_text
from roost.money.models import Expense
from roost.money.months import month_bounds
from roost.projects.numbers import per_currency, spending

CSV_HEADERS = ("Date", "Project", "Amount", "Currency", "Note", "Vendor", "Status", "Starred", "Kind")
_FORMULA_STARTS = ("=", "+", "-", "@")
_RAW_STARTS = ("\t", "\r")


@dataclass(frozen=True)
class MonthTotals:
    month: str                              # YYYY-MM
    totals: Mapping[str, Decimal]           # per currency code, alphabetical


def months_ending(last: str, count: int) -> tuple[str, ...]:
    """``count`` months up to and including ``last`` (YYYY-MM), oldest first."""
    month_bounds(last)                      # ValueError for a bad month
    year, number = int(last[:4]), int(last[5:7])
    found = []
    for _ in range(count):
        found.append(f"{year:04d}-{number:02d}")
        year, number = (year - 1, 12) if number == 1 else (year, number - 1)
    return tuple(reversed(found))


def trend(expenses: Sequence[Expense], months: Sequence[str]) -> tuple[MonthTotals, ...]:
    """Each month's posted spending per currency. Expenses outside ``months`` are ignored."""
    posted = spending(expenses)                 # money in is not spending
    return tuple(MonthTotals(month, per_currency(tuple(e for e in posted if e.spent_at[:7] == month)))
                 for month in months)


def trend_out(rows: Sequence[MonthTotals]) -> dict[str, list[dict[str, object]]]:
    return {"months": [{"month": row.month, "totals": {code: amount_text(total) for code, total in row.totals.items()}}
                       for row in rows]}


def guard_cell(value: str | None) -> str:
    """A text cell safe to open in a spreadsheet: a formula-looking start gets a leading apostrophe."""
    text = value or ""
    folded = unicodedata.normalize("NFKC", text)      # full-width ＝ ＋ － ＠ fold to the plain signs
    if folded.startswith(_RAW_STARTS) or folded.lstrip().startswith(_FORMULA_STARTS):
        return f"'{text}"
    return text


def csv_text(expenses: Sequence[Expense], project_names: Mapping[str, str]) -> str:
    """The CSV, header first, rows as given (the caller orders and caps them)."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(CSV_HEADERS)
    for e in expenses:
        writer.writerow((
            e.spent_at, guard_cell(project_names.get(e.project_id, "")), amount_text(e.amount), e.currency,
            guard_cell(e.description), guard_cell(e.vendor), e.status, "yes" if e.is_favorite else "no", e.kind))
    return out.getvalue()


def range_name(first_month: str, last_month: str) -> str:
    """The download's file name, from two validated months."""
    month_bounds(first_month), month_bounds(last_month)
    return f"roost-expenses-{first_month}.csv" if first_month == last_month else \
        f"roost-expenses-{first_month}-to-{last_month}.csv"
