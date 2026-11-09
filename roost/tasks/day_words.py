"""The safe date grammar, English and Spanish (design 2026-10-20 §2, P2).

Pure: text and a clock in, a day (and maybe a time) with the span of words it came from out. A number is
a date only beside a month name, in ``d/m``, in ISO, or after "the" / "el día"; a lone number, a number
with a unit or a ``d.m`` is never one. Words match case-insensitively, accents optional, whole words
only. ``direction="forward"`` reads a due (a past day with no year rolls to next year); ``"past"`` reads
an expense's day (the latest past one)."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Callable, Literal

from roost.constants import PM_GUESS_HOURS
from roost.timezones import local_tz

Direction = Literal["forward", "past"]

TONIGHT_HOUR = 20
NOON_HOUR = 12
_MONTH_SEARCH_LIMIT = 14
_FOLD = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
_DAYS_FULL = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
    "lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6,
}
# "mar" is left out on purpose: Tuesday in Spanish, March in English. See ``_MAR_*`` below.
_DAYS_SHORT = {"mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3, "fri": 4,
               "sat": 5, "sun": 6, "lun": 0, "mie": 2, "jue": 3, "vie": 4, "sab": 5, "dom": 6}
_DAYS_ALL = {**_DAYS_FULL, **_DAYS_SHORT}


def _alt(names: dict[str, int]) -> str:
    return "|".join(sorted(names, key=len, reverse=True))


_FULL, _ALL = _alt(_DAYS_FULL), _alt(_DAYS_ALL)
_WORD = r"[a-z]{3,}"
_NOT_AFTER_NUMBER = r"(?<![\d/.:\-])"
_SUFFIX = r"(?:st|nd|rd|th)?"
_FLAGS = re.IGNORECASE


@dataclass(frozen=True)
class DayReading:
    day: date
    time: time | None
    start: int
    end: int
    words: str


@dataclass(frozen=True)
class ClockReading:
    time: time
    start: int
    end: int
    anchored: bool


@dataclass(frozen=True)
class _Hit:
    day: date
    start: int
    end: int
    time: time | None = None
    evening: bool = False


def guess_hour(hour: int, suffix: str | None) -> int:
    """The 24-hour clock hour for a spoken ``hour``: ``am`` / ``pm`` (or ``mañana`` / ``tarde`` /
    ``noche``) decide; with no suffix 1-7 is the afternoon, 8-12 as written, 13+ as 24-hour."""
    word = (suffix or "").lower().translate(_FOLD)
    if word in ("pm", "tarde", "noche"):
        if hour == NOON_HOUR:
            return 0 if word == "noche" else NOON_HOUR
        return hour + 12 if hour < NOON_HOUR else hour
    if word in ("am", "manana"):
        return 0 if hour == NOON_HOUR else hour
    return hour + 12 if hour in PM_GUESS_HOURS else hour


def _fold(text: str) -> str:
    return text.translate(_FOLD).lower()


def month_number(word: str) -> int | None:
    """The month a name or its 3+ letter start names; ``None`` when it names none or two."""
    word = word.lower().translate(_FOLD)
    if len(word) < 3:
        return None
    found = {number for name, number in _MONTHS.items() if name.startswith(word)}
    return found.pop() if len(found) == 1 else None


def _valid(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _add_months(day: date, count: int) -> date:
    index = day.year * 12 + day.month - 1 + count
    year, month = divmod(index, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def _pick_year(month: int, day: int, today: date, direction: Direction) -> date | None:
    """A day with no year: forward = today or later, past = today or earlier."""
    step = 1 if direction == "forward" else -1
    for year in (today.year, today.year + step):
        found = _valid(year, month, day)
        if found is not None and (found >= today if direction == "forward" else found <= today):
            return found
    if month == 2 and day == 29:       # leap days: look further
        for year in range(today.year + step, today.year + 9 * step, step):
            found = _valid(year, month, day)
            if found is not None:
                return found
    return None


# --- clock -------------------------------------------------------------------------------------------

_AT = r"(?:at|a\s+las?)\s+"
_PART = r"(?:\s+(?:de|por)\s+la\s+(manana|tarde|noche))?"
_CLOCKS = (
    re.compile(rf"(?<![\d:.])(?:({_AT}))?(\d{{1,2}}):(\d{{2}})(?!\d)(?:\s?(am|pm))?{_PART}", _FLAGS),
    re.compile(rf"(?<![\d:.])(?:({_AT}))?(\d{{1,2}})()\s?(am|pm)\b{_PART}", _FLAGS),
    re.compile(rf"(?<![\d:.])({_AT})(\d{{1,2}})()()(?![\d:])(?!\.\d){_PART}", _FLAGS),
    re.compile(r"()\b(?:at\s+noon|al\s+mediodia)\b()()()()", _FLAGS),
)


def _clock_of(match: re.Match[str], index: int) -> ClockReading | None:
    if index == 3:
        return ClockReading(time(NOON_HOUR, 0), match.start(), match.end(), True)
    anchor, hours, minutes, meridian, part = match.groups()
    hour, minute = int(hours), int(minutes or 0)
    if hour > 23 or minute > 59:
        return None
    suffix = meridian or part
    if (suffix or anchor) and not (len(hours) == 2 and hours.startswith("0")):   # "05:00" is 24-hour
        hour = guess_hour(hour, suffix)
    return ClockReading(time(hour % 24, minute), match.start(), match.end(), bool(anchor))


def find_clock(text: str) -> ClockReading | None:
    """The first time of day in ``text`` ("at 5", "9:30", "9pm", "a las 9 de la noche", "at noon")."""
    folded = _fold(text)
    best: ClockReading | None = None
    for index, pattern in enumerate(_CLOCKS):
        for match in pattern.finditer(folded):
            reading = _clock_of(match, index)
            if reading is not None:
                if best is None or reading.start < best.start:
                    best = reading
                break
    return best


# --- day rules ---------------------------------------------------------------------------------------

Rule = Callable[[str, date, Direction], "_Hit | None"]


def _hit(match: re.Match[str], day: date, **extra: object) -> _Hit:
    return _Hit(day, match.start(), match.end(), **extra)  # type: ignore[arg-type]


_AFTER_TOMORROW = re.compile(r"\b(?:day\s+after\s+tomorrow|pasado\s+manana)\b", _FLAGS)
_TOMORROW = re.compile(r"\b(?:tomorrow|tmrw|tmr|tom|(?<!la )manana|mnn)\b", _FLAGS)
_TODAY = re.compile(r"\b(?:today|tod|hoy)\b", _FLAGS)
_TONIGHT = re.compile(r"\b(?:tonight|esta\s+noche)\b", _FLAGS)
_BEFORE_YESTERDAY = re.compile(r"\b(?:day\s+before\s+yesterday|anteayer|antes\s+de\s+ayer)\b", _FLAGS)
_YESTERDAY = re.compile(r"\b(?:yesterday|ayer)\b", _FLAGS)


def _named_forward(text: str, today: date, _: Direction) -> _Hit | None:
    for pattern, days, evening in ((_AFTER_TOMORROW, 2, False), (_TOMORROW, 1, False),
                                   (_TODAY, 0, False), (_TONIGHT, 0, True)):
        match = pattern.search(text)
        if match:
            return _hit(match, today + timedelta(days=days), evening=evening,
                        time=time(TONIGHT_HOUR, 0) if evening else None)
    return None


def _named_past(text: str, today: date, _: Direction) -> _Hit | None:
    for pattern, days in ((_BEFORE_YESTERDAY, -2), (_YESTERDAY, -1), (_TODAY, 0)):
        match = pattern.search(text)
        if match:
            return _hit(match, today + timedelta(days=days))
    return None


_RELATIVE = re.compile(
    rf"\b(?:in|within|dentro\s+de|en)\s+(\d{{1,6}})\s*(minutes?|mins?|hours?|hrs?|days?|weeks?|months?|"
    rf"minutos?|horas?|dias?|semanas?|mes(?:es)?)\b", _FLAGS)
_AGO = re.compile(r"\b(?:(\d{1,6})\s+(days?|weeks?)\s+ago|hace\s+(\d{1,6})\s+(dias?|semanas?))\b", _FLAGS)


def _relative_forward(text: str, today: date, _: Direction, now: datetime | None = None) -> _Hit | None:
    match = _RELATIVE.search(text)
    if not match:
        return None
    count, unit = int(match.group(1)), match.group(2).lower()
    if unit.startswith(("min", "h")):
        delta = timedelta(minutes=count) if unit.startswith("min") else timedelta(hours=count)
        moment = (now or datetime.combine(today, time(0, 0))) + delta
        return _hit(match, moment.date(), time=time(moment.hour, moment.minute))
    if unit.startswith(("mes", "month")):
        return _hit(match, _add_months(today, count))
    days = count * (7 if unit.startswith(("w", "s")) else 1)
    return _hit(match, today + timedelta(days=days))


def _ago(text: str, today: date, _: Direction) -> _Hit | None:
    match = _AGO.search(text)
    if not match:
        return None
    count = int(match.group(1) or match.group(3))
    unit = (match.group(2) or match.group(4)).lower()
    return _hit(match, today - timedelta(days=count * (7 if unit.startswith(("w", "s")) else 1)))


_WEEKDAY_ANCHORED = re.compile(
    rf"\b(?:el\s+)?(?:next|this|on|by|before|el|este|proximo|antes\s+del?)\s+({_ALL})\b(?:\s+que\s+viene)?", _FLAGS)
_WEEKDAY_BARE = re.compile(rf"\b({_ALL})\b(?:\s+que\s+viene)?", _FLAGS)
# "mar": Tuesday only in a line that is otherwise Spanish, or when a time follows it ("mar 9:00", "mar 5pm",
# "mar at 9"); anywhere else it stays text (and "mar 5" is the 5th of March).
_MAR = re.compile(r"\b(?:(?:el|este|proximo)\s+)?mar\b", _FLAGS)
_MAR_THEN_TIME = re.compile(r"\bmar\b(?=\s+(?:(?:at|a\s+las?)\s+\d|\d{1,2}:\d{2}|\d{1,2}\s?(?:am|pm)\b))", _FLAGS)
_SPANISH_CLUES = re.compile(
    r"\b(?:manana|mnn|hoy|ayer|el|la|los|las|del|de|para|con|que|este|proximo|semana|pasado|dentro|cada|todos|"
    r"antes|por|y|lunes|martes|miercoles|jueves|viernes|sabado|domingo|lun|mie|jue|vie|sab|dom)\b", _FLAGS)
_WEEKDAY_PAST = re.compile(rf"\b((?:last|el\s+pasado|el|on)\s+)?({_ALL})\b(\s+pasado)?", _FLAGS)


def _mar_match(text: str) -> re.Match[str] | None:
    """"mar" read as Tuesday (see ``_MAR``), or ``None``."""
    if (then_time := _MAR_THEN_TIME.search(text)) is not None:
        return then_time
    found = _MAR.search(text)
    if found is None:
        return None
    prefixed = found.group(0).lower() != "mar"            # "el mar", "este mar": already Spanish
    return found if prefixed or _SPANISH_CLUES.search(text[:found.start()] + " " + text[found.end():]) else None


def _weekday_forward(text: str, today: date, _: Direction) -> _Hit | None:
    match = _WEEKDAY_ANCHORED.search(text) or _WEEKDAY_BARE.search(text)
    tuesday = _mar_match(text)
    if tuesday is not None and (match is None or tuesday.start() < match.start()):
        return _hit(tuesday, today + timedelta(days=(1 - today.weekday()) % 7 or 7))
    if not match:
        return None
    ahead = (_DAYS_ALL[match.group(1).lower()] - today.weekday()) % 7 or 7
    return _hit(match, today + timedelta(days=ahead))


def _weekday_past(text: str, today: date, _: Direction) -> _Hit | None:
    for match in _WEEKDAY_PAST.finditer(text):
        prefix, name, suffix = match.groups()
        if name.lower() in _DAYS_SHORT and not prefix:
            continue
        back = (today.weekday() - _DAYS_ALL[name.lower()]) % 7
        strict = bool(suffix) or (prefix or "").startswith(("last", "el pasado"))
        return _hit(match, today - timedelta(days=back or (7 if strict else 0)))
    return None


_END_MONTH = re.compile(r"\b(?:end\s+of\s+(?:the\s+)?month|(?:a\s+)?fin\s+de\s+mes)\b", _FLAGS)
_END_WEEK = re.compile(r"\bend\s+of\s+(?:the\s+)?week\b", _FLAGS)
_WEEKEND = re.compile(r"\b(?:this\s+weekend|este\s+finde|este\s+fin\s+de\s+semana)\b", _FLAGS)
_NEXT_MONTH = re.compile(r"\b(?:next\s+month|el\s+mes\s+que\s+viene|el\s+proximo\s+mes)\b", _FLAGS)
_NEXT_WEEK = re.compile(r"\b(?:(?:next|nxt)\s+(?:week|wk)|la\s+semana\s+que\s+viene|la\s+proxima\s+semana)\b", _FLAGS)


def _periods(text: str, today: date, _: Direction) -> _Hit | None:
    last = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    candidates = (
        (_END_MONTH, last),
        (_END_WEEK, today + timedelta(days=(4 - today.weekday()) % 7)),
        (_WEEKEND, today + timedelta(days=0 if today.weekday() >= 5 else 5 - today.weekday())),
        (_NEXT_MONTH, last + timedelta(days=1)),
        (_NEXT_WEEK, today + timedelta(days=7 - today.weekday())),
    )
    for pattern, day in candidates:
        match = pattern.search(text)
        if match:
            return _hit(match, day)
    return None


_DAY_MONTH = re.compile(
    rf"{_NOT_AFTER_NUMBER}\b(\d{{1,2}}){_SUFFIX}\s+(?:of\s+|de\s+)?({_WORD})\b(?:\s+(?:de\s+)?(\d{{4}})\b)?",
    _FLAGS)
_MONTH_DAY = re.compile(
    rf"\b({_WORD})\s+(\d{{1,2}}){_SUFFIX}(?![\d:.]|/)\b(?:,?\s+(\d{{4}})\b)?", _FLAGS)
_DMY = re.compile(r"(?<![\d/.:\-])(\d{1,2})/(\d{1,2})(?:/(\d{4}))?(?![\d/])")
_ISO = re.compile(r"(?<![\d\-])(\d{4})-(\d{2})-(\d{2})(?![\d\-])")


def _dated(day: int, month: int, year: str | None, today: date, direction: Direction) -> date | None:
    if year:
        return _valid(int(year), month, day)
    return _pick_year(month, day, today, direction)


def _day_month(text: str, today: date, direction: Direction) -> _Hit | None:
    for pattern, first_is_day in ((_DAY_MONTH, True), (_MONTH_DAY, False)):
        for match in pattern.finditer(text):
            number = month_number(match.group(2 if first_is_day else 1))
            digits = int(match.group(1 if first_is_day else 2))
            found = number and _dated(digits, number, match.group(3), today, direction)
            if found:
                return _hit(match, found)
    return None


def _numeric(text: str, today: date, direction: Direction) -> _Hit | None:
    for match in _ISO.finditer(text):
        found = _valid(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if found:
            return _hit(match, found)
    for match in _DMY.finditer(text):
        found = _dated(int(match.group(1)), int(match.group(2)), match.group(3), today, direction)
        if found:
            return _hit(match, found)
    return None


_MONEY_AFTER = r"(?!\s*(?:[€$£%]|eur\b|euros?\b|usd\b|gbp\b|de\s+[a-z]|[:./,]\d|/))"
_THE_DAY = re.compile(rf"\b(?:on\s+)?(?:the|el\s+dia|el)\s+(\d{{1,2}})(?:st|nd|rd|th)\b|\b(?:el\s+dia|el)\s+(\d{{1,2}}){_MONEY_AFTER}\b",
                      _FLAGS)


def _day_of_month(text: str, today: date, direction: Direction) -> _Hit | None:
    match = _THE_DAY.search(text)
    if not match:
        return None
    number = int(match.group(1) or match.group(2))
    step = 1 if direction == "forward" else -1
    for offset in range(_MONTH_SEARCH_LIMIT):
        month = _add_months(today.replace(day=1), offset * step)
        found = _valid(month.year, month.month, number)
        if found and (found >= today if direction == "forward" else found <= today):
            return _hit(match, found)
    return None


_FORWARD: tuple[Rule, ...] = (_named_forward, _relative_forward, _periods, _day_month, _numeric,
                              _weekday_forward, _day_of_month)
_PAST: tuple[Rule, ...] = (_named_past, _ago, _day_month, _numeric, _weekday_past, _day_of_month)


def _local(now: datetime) -> datetime:
    return now.astimezone(local_tz()) if now.tzinfo else now


_REMINDER_MARK = "^"


def _lone_clock(text: str, now: datetime) -> DayReading | None:
    """A time with no day ("at 5", "13:00", "10am"): today if still ahead, else tomorrow. A bare hour needs
    "at" (``_CLOCKS`` reads one only after it), so a lone number is still never a time."""
    clock = find_clock(text)
    if clock is None or text[max(clock.start - 1, 0):clock.start] == _REMINDER_MARK:   # "^9am" is a reminder
        return None
    day = now.date()
    if datetime.combine(day, clock.time, tzinfo=now.tzinfo) <= now:
        day += timedelta(days=1)
    return DayReading(day, clock.time, clock.start, clock.end, text[clock.start:clock.end])


def find_day(text: str, *, now: datetime, direction: Direction = "forward") -> DayReading | None:
    """The first day ``text`` names, with its words' span; ``None`` when it names none."""
    local = _local(now)
    folded, today = _fold(text), local.date()
    for rule in (_PAST if direction == "past" else _FORWARD):
        hit = (rule(folded, today, direction) if rule is not _relative_forward
               else _relative_forward(folded, today, direction, local))
        if hit is None:
            continue
        clock = find_clock(text)
        moment = hit.time
        if clock is not None:
            moment = clock.time
            if hit.evening and moment.hour < NOON_HOUR:
                moment = moment.replace(hour=moment.hour + NOON_HOUR)
        return DayReading(hit.day, moment, hit.start, hit.end, text[hit.start:hit.end])
    return _lone_clock(text, local) if direction == "forward" else None
