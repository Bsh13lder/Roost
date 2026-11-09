"""Task views, search and sort (Task 10, design P11): pure rules over tasks.

A task's day is the first ten characters of its ``due_date``, which is a plain day or a local
ISO moment, so the day is local. ``in_view`` says whether one task belongs to a view; ``pick`` filters,
searches and sorts a list. Nothing here reads the clock: the caller passes local ``today``."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Sequence

from roost.constants import BOARD_DONE_DAYS, TASK_DONE_VIEW_LIMIT, UPCOMING_COUNT_DAYS
from roost.timezones import local_tz
from roost.tasks.models import PRIORITIES, Task
from roost.tasks.reminders import parse_iso_datetime, parse_offset_against

TaskView = Literal["today", "upcoming", "overdue", "someday", "done", "board"]
TaskSort = Literal["due", "priority", "created", "created_asc", "title", "money_left"]
DueBucket = Literal["overdue", "today", "tomorrow", "week", "later", "none"]
_WEEK_DAYS = 7      # 2 to 6 days ahead is "week"; 7 or more is "later"
_OPEN = ("todo", "in_progress")
FINISHABLE_VIEWS: tuple[TaskView, ...] = ("today", "upcoming", "someday")   # views that may also show done tasks
_DAY_LENGTH = len("YYYY-MM-DD")
_RANK = {name: rank for rank, name in enumerate(reversed(PRIORITIES))}   # urgent first


def due_day(task: Task) -> date | None:
    if not task.due_date:
        return None
    try:
        return date.fromisoformat(task.due_date[:_DAY_LENGTH])
    except ValueError:
        return None


def due_bucket(task: Task, today: date) -> DueBucket:
    """Where the task's due day sits against local ``today``, whatever its status."""
    day = due_day(task)
    if day is None:
        return "none"
    ahead = (day - today).days
    if ahead < 0:
        return "overdue"
    if ahead < 2:
        return "today" if ahead == 0 else "tomorrow"
    return "week" if ahead < _WEEK_DAYS else "later"


def _done_recently(task: Task, today: date) -> bool:
    """Closed as done within the last ``BOARD_DONE_DAYS`` local days, today included."""
    if task.status != "done" or not task.completed_at:
        return False
    try:
        closed = datetime.fromisoformat(task.completed_at).astimezone(local_tz()).date()
    except ValueError:
        return False
    return closed > today - timedelta(days=BOARD_DONE_DAYS)


def in_view(task: Task, view: TaskView, today: date, finished: bool = False) -> bool:
    """``finished`` lets today, upcoming and someday also hold done tasks whose due falls in the view."""
    if view == "board":
        return task.status in _OPEN or _done_recently(task, today)
    if view == "done":
        return task.status == "done"
    done_here = finished and view in FINISHABLE_VIEWS and task.status == "done"
    if task.status not in _OPEN and not done_here:
        return False
    day = due_day(task)
    if view == "someday":
        return day is None
    if day is None:
        return False
    return {"overdue": day < today, "today": day == today, "upcoming": day > today}[view]


def reminder_days(task: Task) -> frozenset[date]:
    """The local days the task's reminder and its advance reminders (stored instants, or offsets like -30m) fire
    on; none without a readable ``reminder_at``. A stray entry is skipped, as the reminders job skips it."""
    base = parse_iso_datetime(task.reminder_at or "")
    if base is None:
        return frozenset()
    moments = [base]
    for entry in task.pre_reminders:
        try:
            moment = parse_offset_against(entry, base) or parse_iso_datetime(entry)
        except OverflowError:
            moment = None
        if moment is not None:
            moments.append(moment)
    return frozenset(moment.astimezone(local_tz()).date() for moment in moments)


def in_range(task: Task, first: date, last: date, today: date) -> bool:
    """Whether the calendar shows the task: due within ``first``..``last`` in any status but cancelled, open and
    overdue while ``today`` is in the range (an overdue task sits on today), or open with a reminder that fires in
    the range (its bell, clean calendar 2026-10-26)."""
    if task.status == "cancelled":
        return False
    if task.status in _OPEN and any(first <= fire <= last for fire in reminder_days(task)):
        return True
    day = due_day(task)
    if day is None:
        return False
    if first <= day <= last:
        return True
    return first <= today <= last and day < today and task.status in _OPEN


def fold(text: str) -> str:
    """Lower case without accents, so "CAFE" finds "Café"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def matches(task: Task, query: str) -> bool:
    needle = fold(query.strip())
    return not needle or needle in fold(f"{task.title}\n{task.description or ''}")


def _by_due(task: Task) -> tuple:
    return (task.due_date is None, task.due_date or "", _RANK.get(task.priority, len(_RANK)), task.created_at)


def _by_priority(task: Task) -> tuple:
    return (_RANK.get(task.priority, len(_RANK)), task.due_date is None, task.due_date or "", task.created_at)


def _sorted(tasks: Sequence[Task], sort: TaskSort) -> list[Task]:
    if sort == "created":
        return sorted(tasks, key=lambda task: task.created_at, reverse=True)
    if sort == "created_asc":
        return sorted(tasks, key=lambda task: task.created_at)
    if sort == "title":
        return sorted(tasks, key=lambda task: (fold(task.title), task.created_at))
    return sorted(tasks, key=_by_priority if sort == "priority" else _by_due)


def _newest_closed(tasks: Sequence[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: task.completed_at or "", reverse=True)[:TASK_DONE_VIEW_LIMIT]


def pick(tasks: Sequence[Task], view: TaskView | None, *, today: date, query: str | None = None,
         sort: TaskSort = "due", finished: bool = False) -> tuple[Task, ...]:
    """The tasks in ``view`` (``None``: all given) that match ``query``, sorted. Done is newest first, capped.
    ``finished`` adds done tasks to today, upcoming and someday (see ``in_view``)."""
    chosen = [task for task in tasks
              if (view is None or in_view(task, view, today, finished)) and matches(task, query or "")]
    return tuple(_newest_closed(chosen) if view == "done" else _sorted(chosen, sort))


@dataclass(frozen=True)
class ViewCounts:
    overdue: int
    today: int
    upcoming_14: int
    someday: int
    done_week: int
    open: int             # every open task (to do or in progress), whatever its due


def _closed_on_or_after(task: Task, monday: date) -> bool:
    if task.status != "done" or not task.completed_at:
        return False
    try:
        return datetime.fromisoformat(task.completed_at).astimezone(local_tz()).date() >= monday
    except ValueError:
        return False


def counts(tasks: Sequence[Task], today: date) -> ViewCounts:
    """How many tasks each tab would show. Upcoming is the next ``UPCOMING_COUNT_DAYS`` days, from tomorrow;
    done is what closed since Monday of this local week."""
    monday = today - timedelta(days=today.weekday())
    horizon = today + timedelta(days=UPCOMING_COUNT_DAYS)
    return ViewCounts(
        overdue=sum(in_view(task, "overdue", today) for task in tasks),
        today=sum(in_view(task, "today", today) for task in tasks),
        upcoming_14=sum(in_view(task, "upcoming", today) and (due_day(task) or horizon) <= horizon for task in tasks),
        someday=sum(in_view(task, "someday", today) for task in tasks),
        done_week=sum(_closed_on_or_after(task, monday) for task in tasks),
        open=sum(task.status in _OPEN for task in tasks),
    )


def madrid_today(now: datetime | None = None) -> date:
    """Today's date in the install's zone."""
    return (now or datetime.now(timezone.utc)).astimezone(local_tz()).date()
