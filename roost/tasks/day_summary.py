"""The end-of-day summary's content (projects hub, H13). For one local day it
holds the tasks closed that day (done and failed), the open tasks already
overdue, and that day's counted expenses per currency. No tool or route uses
it yet; the scheduler (part 2) will send it."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Mapping, Sequence

from roost.money.amounts import amount_text
from roost.money.expense_store import ExpenseStore
from roost.money.models import Expense
from roost.projects.numbers import counted, per_currency
from roost.timezones import local_tz
from roost.tasks.format import task_line
from roost.tasks.models import Task
from roost.tasks.store import TaskStore

logger = logging.getLogger(__name__)

_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATE_ONLY_LENGTH = len("YYYY-MM-DD")
_MONTH_LENGTH = len("YYYY-MM")
_DONE = "done"
_FAILED = "failed"
_HEADING = "Your day, {day}"
_NOTHING = "Nothing was done or failed, nothing is overdue and nothing was spent."
_SPENT = "Spent: "


@dataclass(frozen=True)
class DaySummary:
    day: str                              # YYYY-MM-DD, a local day
    done: tuple[Task, ...]
    failed: tuple[Task, ...]
    overdue: tuple[Task, ...]
    spent: Mapping[str, Decimal]          # counted expenses that day, per currency


def _parse_day(day: str) -> date:
    refusal = f"“{day}” is not a day like 2026-10-14."
    if not _DAY.fullmatch(day):
        raise ValueError(refusal)
    try:
        return date.fromisoformat(day)
    except ValueError as exc:
        raise ValueError(refusal) from exc


def madrid_day_bounds_utc(day: str) -> tuple[str, str]:
    """``[midnight, next midnight)`` of a local day as UTC ISO text, the shape
    ``tasks.completed_at`` is written in. A clock-change day is 23 or 25 hours."""
    first = _parse_day(day)
    start = datetime.combine(first, time.min, tzinfo=local_tz())
    end = datetime.combine(first + timedelta(days=1), time.min, tzinfo=local_tz())
    return start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()


def _moment(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("The summary's time needs a time zone.")
    return now


def _is_overdue(task: Task, today: date, now: datetime) -> bool:
    """A date-only due is overdue from the next local day; a timed one from
    its time (a time with no offset is read as local time). A due that reads
    as neither is logged and left out."""
    due = task.due_date
    if not due:
        return False
    try:
        if len(due) == _DATE_ONLY_LENGTH:
            return date.fromisoformat(due) < today
        moment = datetime.fromisoformat(due)
    except ValueError:
        logger.warning("Task %s has an unreadable due date; it is left out of the overdue list", task.id)
        return False
    return (moment if moment.tzinfo else moment.replace(tzinfo=local_tz())) < now


def _spent_on(expenses: Sequence[Expense], day: str) -> Mapping[str, Decimal]:
    """The day's counted expenses (posted, each in its own currency), summed
    per currency and never converted, codes in alphabetical order."""
    return per_currency(tuple(e for e in expenses if e.spent_at == day and counted(e, e.currency)))


async def build_day_summary(user_id: str, day: str, *, tasks: TaskStore, expenses: ExpenseStore,
                            now: datetime | None = None) -> DaySummary:
    """``day`` is a local day (YYYY-MM-DD). Overdue is judged at ``now``
    (default: the real clock), which must carry a time zone."""
    start, end = madrid_day_bounds_utc(day)
    moment = _moment(now)
    today = moment.astimezone(local_tz()).date()
    closed = await tasks.closed_between(user_id, start, end)
    open_tasks = await tasks.list(user_id, status="open")
    month = await expenses.list_month(user_id, day[:_MONTH_LENGTH])
    return DaySummary(
        day=day, done=tuple(task for task in closed if task.status == _DONE),
        failed=tuple(task for task in closed if task.status == _FAILED),
        overdue=tuple(task for task in open_tasks if _is_overdue(task, today, moment)),
        spent=_spent_on(month, day),
    )


def _section(title: str, tasks: tuple[Task, ...]) -> tuple[str, ...]:
    if not tasks:
        return ()
    return (f"{title} ({len(tasks)}):", *(task_line(task) for task in tasks))


def _spent_lines(spent: Mapping[str, Decimal]) -> tuple[str, ...]:
    if not spent:
        return ()
    return (_SPENT + ", ".join(f"{amount_text(total)} {code}" for code, total in spent.items()),)


def day_summary_text(summary: DaySummary) -> str:
    """Plain lines: a heading, then Done, Failed and Overdue (one ``task_line``
    each, which escapes the titles) and the money spent. Empty parts are left out."""
    body = (*_section("Done", summary.done), *_section("Failed", summary.failed),
            *_section("Overdue", summary.overdue), *_spent_lines(summary.spent))
    return "\n".join((_HEADING.format(day=summary.day), *(body or (_NOTHING,))))
