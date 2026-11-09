"""A task reminder's words in the chat (owner, 2026-10-26: "like Grok"): a friendly line, never a template dump.

Which line a reminder gets depends only on which reminder it is, so the same reminder always reads the same:

- an advance reminder (before the task's reminder time): "Heads-up: <title> is in 2 h." / "… tomorrow at 10:00.",
  counted to the task's due when it has one (owner, 2026-10-31), else to the reminder time;
- the reminder itself, with a later due: "Quick reminder: <title> is due today at 18:00.";
- the reminder itself at the due time, or with no due: "It's time: <title> (10:00).";
- a reminder after the reminder time or past the due: "Gentle nudge: <title> is still open."

Times are the install's zone's, with no place name (owner, 2026-11-09). Nothing here reads the clock or the database."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from roost.timezones import local_tz

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
_SAME = timedelta(minutes=1)        # fire times closer than this to the reminder time count as the reminder itself
_DAY_ONLY = len("YYYY-MM-DD")
_WITH_CLOCK = len("YYYY-MM-DDTHH:MM")


@dataclass(frozen=True)
class _Due:
    day: date
    clock: time | None


def day_words(day: date) -> str:
    """"Wednesday 21 October"."""
    return f"{WEEKDAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]}"


def _hhmm(clock: time) -> str:
    return f"{clock:%H:%M}"


def _span(delta: timedelta) -> str:
    """"30 min", "1 h", "1 h 30 min"."""
    minutes = max(1, round(delta.total_seconds() / 60))
    hours, rest = divmod(minutes, 60)
    if not hours:
        return f"{rest} min"
    return f"{hours} h" if not rest else f"{hours} h {rest} min"


def _day_and_clock(day: date, clock: time | None, today: date) -> str:
    """"today", "tomorrow at 09:00", "on Monday 26 October"."""
    if day == today:
        lead = "today"
    elif day == today + timedelta(days=1):
        lead = "tomorrow"
    else:
        lead = f"on {day_words(day)}"
    return lead if clock is None else f"{lead} at {_hhmm(clock)}"


def _parse_due(due_date: str | None) -> _Due | None:
    """A task's due as local wall time: "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM…". ``None`` when it does not read."""
    if not due_date or len(due_date) < _DAY_ONLY:
        return None
    try:
        day = date.fromisoformat(due_date[:_DAY_ONLY])
        has_clock = len(due_date) >= _WITH_CLOCK and due_date[_DAY_ONLY] == "T"
        clock = time.fromisoformat(due_date[_DAY_ONLY + 1:_WITH_CLOCK]) if has_clock else None
    except ValueError:
        return None
    return _Due(day, clock)


def _on_time(title: str, base: datetime, due: _Due | None) -> str:
    """The reminder itself: due later is a quick reminder, due now (or never) is "It's time", past due a nudge."""
    today, now_clock = base.date(), base.time().replace(second=0, microsecond=0)
    if due is None or (due.day == today and due.clock == now_clock):
        return f"It's time: {title} ({_hhmm(now_clock)})."
    past = due.day < today or (due.day == today and due.clock is not None and due.clock < now_clock)
    if past:
        return nudge(title)
    return f"Quick reminder: {title} is due {_day_and_clock(due.day, due.clock, today)}."


def nudge(title: str) -> str:
    return f"Gentle nudge: {title} is still open."


def _ahead(fire: datetime, base: datetime, due: _Due | None) -> str:
    """When the task is, seen from an advance reminder (owner, 2026-10-31): its due when it has one that is not
    before the reminder time ("in 3 h", "tomorrow at 12:30", "tomorrow"), else the reminder time itself."""
    if due is not None and due.clock is None and due.day >= base.date():
        return _day_and_clock(due.day, None, fire.date())
    target = base
    if due is not None and due.clock is not None:
        due_at = datetime.combine(due.day, due.clock, tzinfo=local_tz())
        target = due_at if due_at >= base else base
    if target.date() == fire.date():
        return f"in {_span(target - fire)}"
    return _day_and_clock(target.date(), target.time(), fire.date())


def reminder_text(title: str, *, fire_at: datetime, base_at: datetime, due_date: str | None) -> str:
    """The words of the reminder that fires at ``fire_at`` for a task whose reminder time is ``base_at``."""
    fire, base = fire_at.astimezone(local_tz()), base_at.astimezone(local_tz())
    if base - fire >= _SAME:
        return f"Heads-up: {title} is {_ahead(fire, base, _parse_due(due_date))}."
    if fire - base >= _SAME:
        return nudge(title)
    return _on_time(title, base, _parse_due(due_date))
