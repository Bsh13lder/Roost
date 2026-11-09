"""A due or reminder in words, for the quick line's live preview (Amendment T): "Wed 21 Oct 09:00".

Always local time (Roost's one zone). A date-only due has no clock; another year than ``now``'s says its
year. English day and month names, fixed here so the text does not follow the server's locale."""

from __future__ import annotations

from datetime import datetime

from roost.timezones import local_tz

_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_DATE_ONLY_LENGTH = len("YYYY-MM-DD")


def preview(stamp: str | None, *, now: datetime) -> str | None:
    """``stamp`` (a date, or an ISO moment) as "Wed 21 Oct 09:00"; ``None`` for nothing or an unreadable one."""
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    timed = len(stamp) > _DATE_ONLY_LENGTH
    local = moment.astimezone(local_tz()) if moment.tzinfo else moment.replace(tzinfo=local_tz())
    words = [_DAYS[local.weekday()], str(local.day), _MONTHS[local.month - 1]]
    if local.year != now.astimezone(local_tz()).year:
        words.append(str(local.year))
    if timed:
        words.append(local.strftime("%H:%M"))
    return " ".join(words)
