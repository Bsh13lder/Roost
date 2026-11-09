"""Day totals and the range summary for ``GET /api/money/range`` (Board redesign G9), pure.

Every figure is added here and nowhere else; the web only shows them. Void rows and money in are listed
by the route but never counted. Nothing is ever added across currencies: a day, and the range, each carry a
total per currency. ``bar_percent`` is the one comparison: a day's main-currency total against the biggest
main-currency day of the range."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Mapping, Sequence

from roost.money.models import Expense
from roost.projects.numbers import per_currency, spending

_HUNDRED = Decimal(100)


@dataclass(frozen=True)
class DayTotal:
    day: str                          # YYYY-MM-DD, a local day
    count: int                        # counted rows only (posted spending)
    totals: Mapping[str, Decimal]     # per currency, alphabetical
    bar_percent: int                  # 0..100: the main currency's total against the biggest day's


@dataclass(frozen=True)
class RangeSummary:
    count: int
    totals: Mapping[str, Decimal]


def _percent(part: Decimal, whole: Decimal) -> int:
    if whole <= 0:
        return 0
    return int((part * _HUNDRED / whole).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def day_totals(expenses: Sequence[Expense], main_currency: str) -> tuple[DayTotal, ...]:
    """One entry per day that has any row (void ones included), newest first."""
    days = sorted({e.spent_at for e in expenses}, reverse=True)
    counted = {day: spending(tuple(e for e in expenses if e.spent_at == day)) for day in days}
    main = {day: sum((e.amount for e in rows if e.currency == main_currency), Decimal("0.00"))
            for day, rows in counted.items()}
    biggest = max(main.values(), default=Decimal(0))
    return tuple(DayTotal(day=day, count=len(counted[day]), totals=per_currency(counted[day]),
                          bar_percent=_percent(main[day], biggest)) for day in days)


def range_summary(expenses: Sequence[Expense]) -> RangeSummary:
    counted = spending(expenses)
    return RangeSummary(count=len(counted), totals=per_currency(counted))
