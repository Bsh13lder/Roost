# SPDX-License-Identifier: MIT
# Harvested from LazyClaw lazyclaw/tasks/store.py lines 553-699 and 214-253, lazyclaw/heartbeat/cron.py lines 53-90 @ 21e1002, adapted for Roost

"""Cron recurrence for tasks (M1 D6): the next occurrence's date/time and
whether a series has ended, both on the install's one time zone
(``roost.timezones.local_tz``), so there is no per-user lookup."""

from __future__ import annotations

import logging
from datetime import datetime, time, timezone, tzinfo

from croniter import croniter

from roost.timezones import local_tz
from roost.tasks.repeat_rule import is_rule, next_day, parse_rule, rule_json

logger = logging.getLogger(__name__)

# How many cron occurrences the respawn may skip while hunting for one that is
# still in the FUTURE (see ``_next_occurrence_fields``). One step always suffices
# in practice — a year's worth of headroom exists only so a pathological cron /
# stubbed backend can't spin the event loop forever.
_RESPAWN_MAX_ADVANCES = 366


def _parse_as_user_local(
    value: str | None, tz: tzinfo,
) -> tuple[datetime, bool] | None:
    """Read a stored timestamp as an instant in the user's zone.

    Returns ``(local_instant, was_tz_aware)``, or None when empty/unparseable.

    A NAIVE value is the local wall-clock the mobile app both writes and renders
    (``reschedule_dates.dart`` for reminders, ``composeDueDate`` for a timed
    due), so it is *localised* — never read as UTC. An aware value is converted.
    ``was_tz_aware`` lets the caller re-emit the respawn in the SAME shape it
    read, so a naive-timed ``due_date`` doesn't silently flip format on the
    phone (``due_date`` is not run through ``_normalize_reminder_to_utc``).
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz), False
    return dt.astimezone(tz), True


def _with_time_of_day(day_local: datetime, src_local: datetime) -> datetime:
    """``day_local``'s calendar day at ``src_local``'s wall-clock time-of-day."""
    return day_local.replace(
        hour=src_local.hour,
        minute=src_local.minute,
        second=src_local.second,
        microsecond=0,
    )


def next_occurrence_fields(
    recurring: str,
    *,
    orig_due: str | None,
    orig_reminder: str | None,
    now: datetime | None = None,
    tz: tzinfo | None = None,
) -> tuple[str | None, str | None]:
    """Compute ``(due_date, reminder_at)`` for a recurring task's next occurrence.

    The cron expression fixes the calendar DAY; the completed occurrence fixes
    the wall-clock TIME-OF-DAY (a user who set "18:30" means 18:30 every cycle,
    whatever hour the cron grid nominally names). Two bugs are closed here:

    * The respawn used to always emit a DATE-ONLY ``due_date``, dropping the
      time-of-day the user set. That is not cosmetic: the phone's
      ``reminderBaseTime`` anchors every advance-reminder offset on a timed due
      when one exists and otherwise falls back to "09:00 on that date", so a
      18:30 task respawned date-only slid every offset by 9.5 hours. A timed
      original now respawns timed (same local wall-clock, new date) and a
      date-only original stays date-only.

    * ``get_next_run`` returns the next cron instant, but projecting the
      original's time-of-day onto it can land in the PAST — complete a
      "cron 09:00 / reminder 08:00" task at 08:50 and the respawn's reminder was
      *today 08:00*, 50 minutes ago. The user saw a duplicate task that nagged on
      the very next heartbeat tick. We therefore walk the cron forward until the
      occurrence's anchor instant is strictly in the future.

    The anchor is the reminder when there is one, else the timed due, else the
    cron instant itself (which ``get_next_run`` already guarantees is future) —
    so a task with no reminder is never pushed a cycle out for nothing.

    ``now`` is injectable for tests; production always passes None. Raises
    ``RuntimeError`` if the walk hits ``_RESPAWN_MAX_ADVANCES`` — the caller
    records that as a visible respawn failure rather than persisting a wrong
    occurrence.
    """
    now = now or datetime.now(timezone.utc)
    tz = tz or local_tz()

    # Only a T-bearing due carries a time-of-day; a bare YYYY-MM-DD must stay
    # date-only so the phone doesn't grow a spurious clock chip.
    due_src = (
        _parse_as_user_local(orig_due, tz)
        if orig_due and "T" in orig_due else None
    )
    due_at = due_src[0] if due_src else None
    rem_src = _parse_as_user_local(orig_reminder, tz)
    if orig_reminder and rem_src is None:
        logger.warning(
            "Recurring respawn: could not parse original reminder_at=%r "
            "— leaving the next occurrence's reminder unset", orig_reminder,
        )
    rem_at = rem_src[0] if rem_src else None

    cursor: datetime | None = None
    for _ in range(_RESPAWN_MAX_ADVANCES):
        # First hit = "next fire from the injected (or real) now"; afterwards
        # = "next fire after the occurrence we just rejected".
        next_due = _next_candidate(recurring, cursor, now=now, orig_due=orig_due, tz=tz)
        if next_due is None:
            return None, None
        next_local = next_due.astimezone(tz)

        due_local = _with_time_of_day(next_local, due_at) if due_at else None
        rem_local = _with_time_of_day(next_local, rem_at) if rem_at else None

        anchor = rem_local if rem_local is not None else (due_local or next_local)
        if anchor > now:
            # Roost stores a timed due as local with its own offset
            # (unlike LazyClaw's UTC-or-naive split) — one shape, always aware.
            due_out = next_local.date().isoformat() if due_local is None else due_local.isoformat()
            # The reminder is always emitted UTC-aware — that is the canonical
            # backend shape ``create_task``'s ``_normalize_reminder_to_utc``
            # would coerce it to anyway.
            rem_out = (
                rem_local.astimezone(timezone.utc).isoformat()
                if rem_local is not None else None
            )
            return due_out, rem_out
        cursor = next_due

    logger.error(
        "[tasks] recurring respawn hit the %d-advance cap for cron %r "
        "— refusing to persist a past occurrence",
        _RESPAWN_MAX_ADVANCES, recurring,
    )
    raise RuntimeError(
        f"recurring respawn exhausted {_RESPAWN_MAX_ADVANCES} advance steps "
        f"without finding a future occurrence for cron {recurring!r}"
    )


def _next_candidate(recurring: str, cursor: datetime | None, *, now: datetime, orig_due: str | None,
                    tz: tzinfo) -> datetime:
    """The next calendar day (UTC instant) after ``cursor`` (``None``: the first look). A cron answers by
    its grid; a rule counts from the old due, or from today when it repeats from completion."""
    if not is_rule(recurring):
        return get_next_run(recurring, after=now if cursor is None else cursor, tz=tz)
    rule = parse_rule(recurring)
    if cursor is not None:
        reference = cursor.astimezone(tz).date()
    elif rule.from_completion or not orig_due:
        reference = now.astimezone(tz).date()
    else:
        reference = datetime.fromisoformat(orig_due[:10]).date()
    day = next_day(rule, reference)
    return datetime.combine(day, time(0, 0), tzinfo=tz).astimezone(timezone.utc)


def series_ended(
    recur_until: str | None,
    next_date: str | None,
    next_reminder: str | None,
    tz: tzinfo | None = None,
) -> bool:
    """True when the NEXT occurrence lands beyond the series end.

    A date-only ``recur_until`` means end-of-day IN THE USER'S TZ — comparing
    against naive/UTC midnight would drop the final day's evening dose for a
    Madrid user (the same off-by-one class as the 2026-07-25 naive drift).
    """
    if not recur_until:
        return False
    tz = tz or local_tz()
    try:
        parsed_until = datetime.fromisoformat(recur_until.strip())
    except (ValueError, TypeError):
        return False  # write-boundary validation makes this unreachable
    if len(recur_until.strip()) == 10:
        until_end = datetime.combine(parsed_until.date(), time(23, 59, 59), tzinfo=tz)
    else:
        until_end = (
            parsed_until if parsed_until.tzinfo else parsed_until.replace(tzinfo=tz)
        )

    anchor: datetime | None = None
    raw_anchor = next_reminder or next_date
    if raw_anchor:
        try:
            anchor = datetime.fromisoformat(raw_anchor)
        except (ValueError, TypeError):
            return False
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=tz)
    if anchor is None:
        return False
    return anchor.astimezone(timezone.utc) > until_end.astimezone(timezone.utc)


def get_next_run(
    expression: str,
    after: datetime | None = None,
    tz: tzinfo | None = None,
) -> datetime:
    """Get the next run time after the given datetime.

    The cron expression is evaluated on ``tz`` (default the install's zone). The returned
    datetime is always tz-aware in UTC — callers store ISO strings and the
    daemon's "is now past next_run?" comparison stays a UTC↔UTC compare.

    ``after`` (when provided) is converted to local time before being
    handed to croniter so a UTC ``last_run`` doesn't shift the cron grid.
    """
    if not croniter.is_valid(expression):
        raise ValueError(f"Invalid cron expression: '{expression}'")
    tz = tz or local_tz()

    if after is None:
        base = datetime.now(tz)
    else:
        if after.tzinfo is None:
            after = after.replace(tzinfo=timezone.utc)
        base = after.astimezone(tz)

    cron = croniter(expression, base)
    next_dt = cron.get_next(datetime)

    if next_dt.tzinfo is None:
        # croniter ≥1.4 preserves tz; older builds don't — assume the
        # base's tz so we don't silently drift.
        next_dt = next_dt.replace(tzinfo=tz)

    # Always return UTC so the rest of the daemon can keep comparing
    # against datetime.now(timezone.utc).
    return next_dt.astimezone(timezone.utc)


def validate_cron(expression: str | None) -> str | None:
    """A cron, or a richer repeat rule (``repeat_rule``, canonical JSON); ``ValueError`` otherwise."""
    if expression is None or not expression.strip():
        return None
    cleaned = expression.strip()
    if is_rule(cleaned):
        return rule_json(parse_rule(cleaned))
    if not croniter.is_valid(cleaned):
        raise ValueError(f"{cleaned!r} is not a cron expression like '0 9 * * 1' (Mondays 09:00).")
    return cleaned
