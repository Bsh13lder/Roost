"""Routine schedules in local wall-clock time (the install's zone, ``roost.timezones``): day/time lists and cron, DST rules, jitter, missed slots.

Pure functions only: nothing here reads the clock. Callers pass the instant they mean.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal

from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import (
    ROUTINE_CARD_PREVIEW_COUNT,
    ROUTINE_CRON_CHECK_FIRES,
    ROUTINE_JITTER_SECONDS,
    ROUTINE_MAX_TIMES,
    ROUTINE_MIN_INTERVAL_MINUTES,
)
from roost.timezones import local_tz

_UTC = timezone.utc
_DAYS_AHEAD = 8                      # a times schedule repeats weekly, so 8 days always holds a fire
_GAP_SEARCH_MINUTES = 180
_CRON_SEARCH_LIMIT = 8               # skipped repeats while looking for the next real fire
_ANCHOR = datetime(2026, 1, 1, tzinfo=_UTC)   # parse_schedule checks cron spacing from a fixed instant
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_ALL_DAYS = (1, 2, 3, 4, 5, 6, 7)

_TEXT_NAME = "A routine needs a name."
_TEXT_PICK = "Pick at least one day and one time."
_TEXT_TIMES = "Times look like 10:07."
_TEXT_TOO_MANY = f"Up to {ROUTINE_MAX_TIMES} times a day."
_TEXT_TOO_OFTEN = f"That schedule runs more often than every {ROUTINE_MIN_INTERVAL_MINUTES} minutes."
_TEXT_CRON = "That custom schedule isn't valid."


class ScheduleRefused(ValueError):
    """A schedule the user can't have. ``text`` is the plain sentence to show."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


class TimesSchedule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["times"] = "times"
    days: tuple[int, ...]     # 1 = Monday ... 7 = Sunday
    times: tuple[str, ...]    # "HH:MM", local wall clock


class CronSchedule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["cron"] = "cron"
    expr: str


Schedule = Annotated[TimesSchedule | CronSchedule, Field(discriminator="kind")]


# --- parsing -------------------------------------------------------------------------------------------------

def parse_schedule(raw: Mapping, *, name: str | None = None, after_utc: datetime = _ANCHOR) -> TimesSchedule | CronSchedule:
    """Validate ``raw`` into a schedule or raise ``ScheduleRefused``. ``name``, when given, must not be blank."""
    if name is not None and not name.strip():
        raise ScheduleRefused(_TEXT_NAME)
    if not isinstance(raw, Mapping):
        raise ScheduleRefused(_TEXT_CRON)
    kind = raw.get("kind")
    if kind == "times":
        schedule: TimesSchedule | CronSchedule = _parse_times(raw)
    elif kind == "cron":
        schedule = _parse_cron(raw)
    else:
        raise ScheduleRefused(_TEXT_CRON)
    _check_spacing(schedule, after_utc)
    return schedule


def _parse_times(raw: Mapping) -> TimesSchedule:
    days, times = raw.get("days"), raw.get("times")
    if not isinstance(days, (list, tuple)) or not isinstance(times, (list, tuple)) or not days or not times:
        raise ScheduleRefused(_TEXT_PICK)
    if not all(isinstance(d, int) and not isinstance(d, bool) and 1 <= d <= 7 for d in days):
        raise ScheduleRefused(_TEXT_PICK)
    if not all(isinstance(t, str) and _TIME_RE.match(t) for t in times):
        raise ScheduleRefused(_TEXT_TIMES)
    unique_times = tuple(sorted(set(times)))
    if len(unique_times) > ROUTINE_MAX_TIMES:
        raise ScheduleRefused(_TEXT_TOO_MANY)
    return TimesSchedule(days=tuple(sorted(set(days))), times=unique_times)


def _parse_cron(raw: Mapping) -> CronSchedule:
    expr = raw.get("expr")
    if not isinstance(expr, str):
        raise ScheduleRefused(_TEXT_CRON)
    expr = " ".join(expr.split())
    if len(expr.split(" ")) != 5 or not croniter.is_valid(expr):
        raise ScheduleRefused(_TEXT_CRON)
    try:
        return CronSchedule(expr=expr)
    except ValidationError as exc:  # pragma: no cover - the checks above already cover every field
        raise ScheduleRefused(_TEXT_CRON) from exc


def _check_spacing(schedule: TimesSchedule | CronSchedule, after_utc: datetime) -> None:
    fires = upcoming(schedule, after_utc, ROUTINE_CRON_CHECK_FIRES)
    floor = timedelta(minutes=ROUTINE_MIN_INTERVAL_MINUTES)
    if any(later - earlier < floor for earlier, later in zip(fires, fires[1:])):
        raise ScheduleRefused(_TEXT_TOO_OFTEN)


# --- next fire -----------------------------------------------------------------------------------------------

def _wall_to_utc(naive: datetime) -> datetime:
    """A local wall-clock time as UTC. A time skipped by spring forward moves to the first valid minute after it;
    a time that happens twice (fall back) is taken at its first occurrence."""
    zone = local_tz()
    for minute in range(_GAP_SEARCH_MINUTES):
        candidate = (naive + timedelta(minutes=minute)).replace(tzinfo=zone)   # fold=0
        as_utc = candidate.astimezone(_UTC)
        if as_utc.astimezone(zone).replace(tzinfo=None) == candidate.replace(tzinfo=None):
            return as_utc
    return naive.replace(tzinfo=zone).astimezone(_UTC)  # pragma: no cover - no gap is three hours long


def _as_utc(moment: datetime) -> datetime:
    return moment.astimezone(_UTC) if moment.tzinfo else moment.replace(tzinfo=_UTC)


def next_after(schedule: TimesSchedule | CronSchedule, after_utc: datetime) -> datetime:
    """The first fire strictly after ``after_utc`` (UTC, minute precision, no jitter)."""
    after = _as_utc(after_utc)
    if isinstance(schedule, TimesSchedule):
        return _next_times(schedule, after)
    return _next_cron(schedule, after)


def _next_times(schedule: TimesSchedule, after: datetime) -> datetime:
    start: date = after.astimezone(local_tz()).date()
    for offset in range(_DAYS_AHEAD + 1):
        day = start + timedelta(days=offset)
        if day.isoweekday() not in schedule.days:
            continue
        for hhmm in schedule.times:
            hour, minute = int(hhmm[:2]), int(hhmm[3:])
            fire = _wall_to_utc(datetime(day.year, day.month, day.day, hour, minute))
            if fire > after:
                return fire
    raise ScheduleRefused(_TEXT_PICK)  # pragma: no cover - a validated schedule always fires within a week


def _next_cron(schedule: CronSchedule, after: datetime) -> datetime:
    walker = croniter(schedule.expr, after.astimezone(local_tz()).replace(tzinfo=None))
    for _ in range(_CRON_SEARCH_LIMIT * 4):
        fire = _wall_to_utc(walker.get_next(datetime))
        if fire > after:
            return fire
    raise ScheduleRefused(_TEXT_CRON)  # pragma: no cover - a repeat hour has at most a few skipped fires


def upcoming(schedule: TimesSchedule | CronSchedule, after_utc: datetime, count: int) -> tuple[datetime, ...]:
    fires: list[datetime] = []
    cursor = _as_utc(after_utc)
    for _ in range(max(count, 0)):
        cursor = next_after(schedule, cursor)
        fires.append(cursor)
    return tuple(fires)


def slots_between(
    schedule: TimesSchedule | CronSchedule, after_utc: datetime, until_utc: datetime, limit: int
) -> tuple[datetime, ...]:
    """Every fire in (after, until], oldest first, at most ``limit`` of them."""
    until = _as_utc(until_utc)
    slots: list[datetime] = []
    cursor = _as_utc(after_utc)
    while len(slots) < limit:
        cursor = next_after(schedule, cursor)
        if cursor > until:
            break
        slots.append(cursor)
    return tuple(slots)


def jitter_seconds(routine_id: str, slot_at: datetime) -> int:
    """A stable 0..ROUTINE_JITTER_SECONDS offset for one routine slot, so routines don't all start on the minute."""
    key = f"{routine_id}|{_as_utc(slot_at).isoformat()}"
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % (ROUTINE_JITTER_SECONDS + 1)


def slot_for(next_run_at: datetime, schedule: TimesSchedule | CronSchedule) -> datetime:
    """The slot a stored ``next_run_at`` was planned for. ``next_run_at`` is the slot plus its jitter, so the slot is
    the one fire in the ``ROUTINE_JITTER_SECONDS`` just before it (fires are at least a minute apart)."""
    at = _as_utc(next_run_at)
    candidate = next_after(schedule, at - timedelta(seconds=ROUTINE_JITTER_SECONDS + 1))
    return candidate if candidate <= at else at.replace(second=0, microsecond=0)


# --- words ---------------------------------------------------------------------------------------------------

def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"


def _days_words(days: tuple[int, ...]) -> str:
    if days == _ALL_DAYS:
        return "Every day"
    if days == (1, 2, 3, 4, 5):
        return "Weekdays"
    if days == (6, 7):
        return "Weekends"
    return _join([_DAY_NAMES[d - 1] for d in days])


def _stamp(moment: datetime) -> str:
    local = moment.astimezone(local_tz())
    return f"{local.day} {_MONTH_NAMES[local.month - 1]} {local:%H:%M}"


def readable(schedule: TimesSchedule | CronSchedule, *, now: datetime | None = None) -> str:
    """Plain words for a schedule. A cron line lists its next three fires after ``now`` when given."""
    if isinstance(schedule, TimesSchedule):
        return f"{_days_words(schedule.days)} at {_join(list(schedule.times))}"
    if now is None:
        return f"Custom: {schedule.expr}"
    fires = upcoming(schedule, now, ROUTINE_CARD_PREVIEW_COUNT)
    return f"Custom: next {_join([_stamp(f) for f in fires])}"
