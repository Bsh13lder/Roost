"""A routine's upcoming run times in a window, for the calendars (the Board's Tasks Calendar and a bot's Plan).

Pure functions only: callers pass the window (UTC instants) and the clock. Paused routines are left out, and so are
watching ones (they run only when their page changes, so no time is known ahead); times are the schedule's slots
(no jitter), named in the local day and wall clock."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from roost.routines.models import Routine
from roost.routines.schedule import slots_between
from roost.timezones import local_tz

_UTC = timezone.utc
_JUST_BEFORE = timedelta(seconds=1)   # slots_between is (after, until]: step back so a fire on the edge counts


@dataclass(frozen=True)
class Occurrence:
    routine_id: str
    routine_name: str
    bot_id: str
    bot_name: str
    thread_id: str        # the routine's run-log thread
    at: datetime          # UTC

    @property
    def day(self) -> str:
        return self.at.astimezone(local_tz()).date().isoformat()

    @property
    def time(self) -> str:
        return self.at.astimezone(local_tz()).strftime("%H:%M")


@dataclass(frozen=True)
class OccurrencePage:
    occurrences: tuple[Occurrence, ...]
    truncated: bool       # more fell in the window than the cap allowed


def madrid_span(first: date, last: date) -> tuple[datetime, datetime]:
    """local midnight at the start of ``first`` to local midnight after ``last``, as UTC."""
    def midnight(day: date) -> datetime:
        return datetime(day.year, day.month, day.day, tzinfo=local_tz()).astimezone(_UTC)
    return midnight(first), midnight(last + timedelta(days=1))


def _of_one(routine: Routine, bot_name: str, start: datetime, end: datetime, limit: int) -> list[Occurrence]:
    slots = slots_between(routine.schedule, start - _JUST_BEFORE, end - _JUST_BEFORE, limit)
    return [Occurrence(routine_id=routine.id, routine_name=routine.name, bot_id=routine.bot_id, bot_name=bot_name,
                       thread_id=routine.thread_id, at=slot) for slot in slots]


def occurrences_between(
    routines: Iterable[Routine], bot_names: Mapping[str, str], start: datetime, end: datetime, *, cap: int
) -> OccurrencePage:
    """Every enabled routine's slots in [start, end), oldest first, at most ``cap`` of them."""
    if end <= start:
        return OccurrencePage(occurrences=(), truncated=False)
    found: list[Occurrence] = []
    for routine in routines:
        if routine.enabled and routine.watch is None:
            found.extend(_of_one(routine, bot_names.get(routine.bot_id, ""), start, end, cap + 1))
    ordered = sorted(found, key=lambda one: (one.at, one.routine_name, one.routine_id))
    return OccurrencePage(occurrences=tuple(ordered[:cap]), truncated=len(ordered) > cap)
