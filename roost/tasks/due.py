# SPDX-License-Identifier: MIT
# Harvested from LazyClaw lazyclaw/tasks/store.py lines 123-142 and 189-211 @ 21e1002, adapted for Roost

"""A task's due date (M1 D6): reading "tomorrow at 9" on the install's time zone, the
harvested ISO validators, and the schedule a due plus its reminders makes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from roost.timezones import local_tz
from roost.tasks import nl_time
from roost.tasks.models import TaskPatch
from roost.tasks.reminders import resolve_pre_reminders


def _validate_iso_dt(value: str | None, field_name: str) -> str | None:
    """Validate that ``value`` is a parseable ISO-8601 datetime string.

    Used at write time so malformed ``reminder_at`` / ``pre_reminders``
    entries can't reach the heartbeat daemon and silently stop firing.
    Returns the trimmed value on success, raises ``ValueError`` on bad
    input. None / empty pass through.
    """
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 string, got {type(value).__name__}")
    trimmed = value.strip()
    try:
        datetime.fromisoformat(trimmed)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"{field_name}={trimmed!r} is not a parseable ISO-8601 datetime"
        ) from exc
    return trimmed


def validate_recur_until(value: str | None) -> str | None:
    """Validate a recurrence-end value; empty clears, invalid raises.

    Accepts a plain date (``YYYY-MM-DD`` — the series runs through the END of
    that day in the user's tz) or a full ISO datetime. Loud rejection at the
    write boundary on purpose: an unparseable value stored silently would
    either be skipped by the respawn (series never ends, discovered weeks
    later) or blow up inside its broad except and masquerade as a respawn
    failure — the exact swallowed-``recurring`` history documented on the
    route's ``_validate_recurring``.
    """
    if not value:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    try:
        datetime.fromisoformat(trimmed)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"recur_until={trimmed!r} is not a date (YYYY-MM-DD) or ISO datetime"
        ) from exc
    return trimmed


_UNREADABLE_DUE = "I could not read a date in “{text}”. Try “tomorrow at 9” or 2026-10-20."


@dataclass(frozen=True)
class Due:
    due_date: str | None      # "YYYY-MM-DD", or a local ISO datetime with offset
    reminder_at: str | None   # UTC ISO; set only when the due names a time


@dataclass(frozen=True)
class Schedule:
    due_date: str | None
    reminder_at: str | None
    pre_reminders: tuple[str, ...]


def _moment(local: datetime, tz: ZoneInfo) -> Due:
    local = local.astimezone(tz)
    return Due(local.isoformat(timespec="seconds"), local.astimezone(timezone.utc).isoformat())


def _from_iso(value: str, tz: ZoneInfo) -> Due | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if len(value) == len("YYYY-MM-DD"):
        return Due(parsed.date().isoformat(), None)
    return _moment(parsed if parsed.tzinfo else parsed.replace(tzinfo=tz), tz)


def due_from_parsed(parsed: nl_time.ParsedTime, text: str, tz: ZoneInfo | None = None) -> Due:
    """The due ``nl_time`` read in ``text`` (``parsed.due_date`` set): a day, or a local moment (``tz``, default
    the install's zone) when the words name a time of day. The one rule for a typed due and the quick-add line."""
    if parsed.reminder_at is None or not nl_time.has_clock_time(text):
        return Due(parsed.due_date, None)
    return _moment(datetime.fromisoformat(parsed.reminder_at), tz or local_tz())


def _read_due(value: str, tz: ZoneInfo) -> Due:
    iso = _from_iso(value, tz)
    if iso is not None:
        return iso
    parsed = nl_time.parse(value, tz=tz)
    if parsed.due_date is None:
        raise ValueError(_UNREADABLE_DUE.format(text=value))
    return due_from_parsed(parsed, value, tz)


def parse_due(text: str | None, *, tz: ZoneInfo | None = None) -> Due:
    """Read "tomorrow at 9", "next Monday", "2026-10-20" or an ISO time on
    local time (``tz``, default the install's zone). A phrase with no time of day stays a date. Raises
    ``ValueError`` with a plain sentence when nothing can be read, including a
    day past the calendar's end ("in 99999999 days")."""
    value = (text or "").strip()
    if not value:
        return Due(None, None)
    try:
        return _read_due(value, tz or local_tz())
    except OverflowError as exc:   # datetime arithmetic past year 9999 (or before year 1)
        raise ValueError(_UNREADABLE_DUE.format(text=value)) from exc


_UNREADABLE_TIME = "I could not read a time in “{text}”. Try “tomorrow at 8:30”."


def build_schedule(due: str | None, reminder: str | None, pre_reminders: Sequence[str] | None) -> Schedule:
    """A timed due is also the reminder unless ``reminder`` names another time."""
    parsed = parse_due(due)
    reminder_at = parse_due(reminder).reminder_at if reminder else parsed.reminder_at
    if reminder and reminder_at is None:
        raise ValueError(_UNREADABLE_TIME.format(text=reminder))
    return Schedule(parsed.due_date, reminder_at, resolve_pre_reminders(pre_reminders, reminder_at))


_ADVANCE_ALONE = "Set a reminder time together with its advance reminders."


def _reminder_changes(text: str | None, entries: Sequence[str] | None = None) -> dict[str, Any]:
    """A reminder set on its own (redesign P3's drawer): words or ISO on local time, which must name
    a time, with its advance reminders (``None``: the default; ``[]``: none, Remind me's quick picks).
    Empty or ``None`` clears both."""
    if text is None or not text.strip():
        return {"reminder_at": None, "pre_reminders": ()}
    reminder_at = parse_due(text).reminder_at
    if reminder_at is None:
        raise ValueError(_UNREADABLE_TIME.format(text=text))
    return {"reminder_at": reminder_at, "pre_reminders": resolve_pre_reminders(entries, reminder_at)}


def patch_from_fields(fields: Mapping[str, Any]) -> TaskPatch:
    """A ``TaskPatch`` from the fields a caller set (``None`` clears). A new
    ``due_date`` (words or ISO) also resets the reminder and its advance
    reminders to the defaults; a ``reminder_at`` set in the same patch wins."""
    changes = {name: value for name, value in fields.items()
               if name not in ("due_date", "reminder_at", "pre_reminders")}
    if "pre_reminders" in fields and "reminder_at" not in fields:
        raise ValueError(_ADVANCE_ALONE)
    if "title" in changes:
        title = (changes["title"] or "").strip()
        if not title:
            raise ValueError("A task needs a title.")
        changes["title"] = title
    if "due_date" in fields:
        schedule = build_schedule(fields["due_date"], None, None)
        changes.update(due_date=schedule.due_date, reminder_at=schedule.reminder_at,
                       pre_reminders=schedule.pre_reminders)
    if "reminder_at" in fields:
        changes.update(_reminder_changes(fields["reminder_at"], fields.get("pre_reminders")))
    return TaskPatch(changes)
