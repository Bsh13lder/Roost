"""The quick line's one-word tokens (design 2026-10-20 §3), pure: priority shorthand, star, estimate,
reminder, amount and ``vendor:``. Order of reading: priority, star, estimate, reminder, amount, vendor.

A token stands alone (spaces or line ends around it). Two of one kind: the last wins, every one leaves
the line, and a warning says so. A kind named in ``skip`` is not read: its words stay in ``rest``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation

from roost.money.amounts import number_value, too_many_digits
from roost.money.expression import EXPRESSION_PATTERN, TOO_LONG_TEXT, ExpressionError, evaluate, has_operator
from roost.constants import DAY_ONLY_DUE_HOUR, QUICK_LINE_CURRENCIES, TASK_ESTIMATE_MAX_MINUTES
from roost.timezones import local_tz
from roost.tasks.day_words import find_clock
from roost.tasks.due import Due
from roost.tasks.models import Priority

TWO_KINDS_TEXT = "Two {kind}: kept {kept}."
REMINDER_NEEDS_DUE_TEXT = "“{words}” needs a due date."
ESTIMATE_RANGE_TEXT = "“{words}” is not a usable estimate: use 1 to {limit} minutes."
UNREADABLE_REMINDER_TEXT = "I could not read a time in “{words}”. Try ^9am or ^1h before."

_CURRENCY_OF = dict(QUICK_LINE_CURRENCIES)
_SIGNS = "".join(_CURRENCY_OF)
_FLAGS = re.IGNORECASE
_ALONE_BEFORE, _ALONE_AFTER = r"(?<!\S)", r"(?!\S)"
_EDGE_PUNCTUATION = ".,;:!?"
_FOLD = str.maketrans("áéíóúüñ", "aeiouun")

_PRIORITY_TOKENS = {
    "!!!": "urgent", "!urgent": "urgent", "!urgente": "urgent",
    "!!": "high", "!high": "high", "!alta": "high",
    "!": "medium", "!medium": "medium", "!media": "medium",
    "!-": "low", "!low": "low", "!baja": "low",
}
_PRIORITY_WORDS = {"urgent": "urgent", "asap": "urgent", "urgente": "urgent", "alta": "high", "baja": "low"}
_STAR_TOKENS = frozenset({"*", "!star", "!fav"})
_PRIORITY_ALTERNATION = "|".join(re.escape(token) for token in sorted(_PRIORITY_TOKENS, key=len, reverse=True))
_PRIORITY = re.compile(rf"{_ALONE_BEFORE}({_PRIORITY_ALTERNATION}){_ALONE_AFTER}", _FLAGS)
_TODOIST_LEVEL = {"1": "urgent", "2": "high", "3": "medium", "4": "low"}       # Todoist's p1-p4, "priority 1"
_PRIORITY_P = re.compile(rf"{_ALONE_BEFORE}(?:p([1-4])|priority\s+([1-4])){_ALONE_AFTER}", _FLAGS)
_STAR = re.compile(rf"{_ALONE_BEFORE}(\*|!star|!fav){_ALONE_AFTER}", _FLAGS)
_ESTIMATE = re.compile(
    rf"{_ALONE_BEFORE}~(?:(\d+)h(\d{{1,2}})(?:m|min)?|(\d+(?:[.,]\d+)?)\s?(h|hr|hrs|hours?|m|mins?|minutes?))"
    rf"{_ALONE_AFTER}", _FLAGS)
_CLOCK_VALUE = r"\d{1,2}(?::\d{2})?\s?(?:am|pm)?"
_DURATION_VALUE = r"\d+h\d{0,2}m?|\d+(?:[.,]\d+)?\s?(?:h|hr|hrs|hours?|m|mins?|minutes?)"
_BEFORE = r"(?:\s+(?:before|antes))?"
_REMINDER = re.compile(
    rf"{_ALONE_BEFORE}(?:\^(?:{_DURATION_VALUE}|{_CLOCK_VALUE}){_BEFORE}"
    rf"|(?:remind\s+me|recu[eé]rdame|av[ií]same)\s+(?:(?:at|a\s+las?)\s+)?(?:{_DURATION_VALUE}|{_CLOCK_VALUE}){_BEFORE})"
    rf"{_ALONE_AFTER}", _FLAGS)
_AMOUNT = re.compile(
    rf"{_ALONE_BEFORE}(\+)?(?:([{_SIGNS}])\s?({EXPRESSION_PATTERN})|({EXPRESSION_PATTERN})\s?([{_SIGNS}])){_ALONE_AFTER}")
_VENDOR = re.compile(rf'{_ALONE_BEFORE}(?:vendor|tienda):(?:"([^"]+)"|(\S+))', _FLAGS)
_DURATION = re.compile(
    r"^(?:(\d+)h(\d{1,2})?m?|(\d+(?:[.,]\d+)?)\s?(h|hr|hrs|hours?|m|mins?|minutes?))$", _FLAGS)
_REMIND_PREFIX = re.compile(r"^(?:\^|(?:remind\s+me|recu[eé]rdame|av[ií]same)\s+(?:(?:at|a\s+las?)\s+)?)", _FLAGS)
_REMIND_SUFFIX = re.compile(r"\s+(?:before|antes)$", _FLAGS)


@dataclass(frozen=True)
class Tokens:
    rest: str
    priority: Priority | None = None
    priority_words: str | None = None
    star: bool = False
    estimate_minutes: int | None = None
    reminder_words: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    amount_words: str | None = None
    star_words: str | None = None
    estimate_words: str | None = None
    amount_math: str | None = None          # "3×45" when the amount was worked out
    amount_problem: str | None = None       # why the typed sum can't be used
    income: bool = False                    # a leading + : money in (+€500)
    vendor: str | None = None
    warnings: tuple[str, ...] = ()


def _fold(text: str) -> str:
    return text.translate(_FOLD).lower()


def _remove(text: str, matches: list[re.Match[str]]) -> str:
    for match in reversed(matches):
        text = f"{text[:match.start()]} {text[match.end():]}"
    return " ".join(text.split())


def _two(kind: str, kept: str) -> str:
    return TWO_KINDS_TEXT.format(kind=kind, kept=kept)


def edge_priority(text: str) -> tuple[Priority | None, str | None, str]:
    """A priority word (urgent, asap, urgente, alta, baja) as the first or last word only: "Pagar luz
    urgente" is urgent, "dar de baja el seguro" keeps its "baja". A line that is only that word keeps it.
    Returns the level, the word as typed, and the text without it."""
    words = text.split()
    if len(words) < 2:
        return None, None, text
    for index in (0, -1):
        typed = words[index]
        level = _PRIORITY_WORDS.get(_fold(typed).strip(_EDGE_PUNCTUATION))
        if level is not None:
            return level, typed, " ".join(words[1:] if index == 0 else words[:-1])
    return None, None, text


def _read_priority(text: str, skip: frozenset[str]) -> tuple[str, Priority | None, str | None, tuple[str, ...]]:
    if "priority" in skip:
        return text, None, None, ()
    found = sorted((*_PRIORITY.finditer(text), *_PRIORITY_P.finditer(text)), key=lambda m: m.start())
    if found:
        last = found[-1]
        level = _PRIORITY_TOKENS[last.group(1).lower()] if last.re is _PRIORITY else _TODOIST_LEVEL[
            last.group(1) or last.group(2)]
        warnings = (_two("priorities", last.group(0).lower()),) if len(found) > 1 else ()
        return _remove(text, found), level, last.group(0), warnings
    level, typed, rest = edge_priority(text)
    return rest, level, typed, ()


def _read_star(text: str, skip: frozenset[str]) -> tuple[str, bool]:
    found = [] if "star" in skip else list(_STAR.finditer(text))
    return (_remove(text, found), True) if found else (text, False)


def _minutes(match: re.Match[str]) -> int:
    hours, minutes, number, unit = match.groups()
    if hours is not None:
        return int(hours) * 60 + int(minutes)
    value = Decimal(number.replace(",", "."))
    return int((value * (60 if unit.lower().startswith("h") else 1)).to_integral_value())


def _read_estimate(text: str, skip: frozenset[str]) -> tuple[str, int | None, tuple[str, ...]]:
    found = [] if "estimate" in skip else list(_ESTIMATE.finditer(text))
    if not found:
        return text, None, ()
    usable = [m for m in found if 1 <= _minutes(m) <= TASK_ESTIMATE_MAX_MINUTES]
    unusable = [m for m in found if m not in usable]
    warnings = tuple(ESTIMATE_RANGE_TEXT.format(words=m.group(0), limit=TASK_ESTIMATE_MAX_MINUTES) for m in unusable)
    if not usable:
        return text, None, warnings                      # the words stay in the title
    if len(usable) > 1:
        warnings = (*warnings, _two("estimates", usable[-1].group(0)))
    return _remove(text, usable), _minutes(usable[-1]), warnings


def _read_reminder(text: str, skip: frozenset[str]) -> tuple[str, str | None, tuple[str, ...]]:
    found = [] if "reminder" in skip else list(_REMINDER.finditer(text))
    if not found:
        return text, None, ()
    words = found[-1].group(0)
    warnings = (_two("reminders", words),) if len(found) > 1 else ()
    return _remove(text, found), words, warnings


@dataclass(frozen=True)
class _Hit:
    match: re.Match[str]
    value: Decimal | None
    currency: str
    math: str | None = None
    problem: str | None = None

    @property
    def income(self) -> bool:
        return self.match.group(1) is not None


def _hit(match: re.Match[str]) -> _Hit | None:
    plus, front, digits_front, digits_back, back = match.groups()
    digits, sign = (digits_front, front) if front else (digits_back, back)
    currency = _CURRENCY_OF[sign]
    if has_operator(digits):
        try:
            worked = evaluate(digits)
        except ExpressionError as exc:
            return _Hit(match, None, currency, problem=str(exc))
        return _Hit(match, worked.value, currency, math=worked.shown)
    value = number_value(digits)
    if value is None and too_many_digits(digits):
        return _Hit(match, None, currency, problem=TOO_LONG_TEXT)
    return None if value is None else _Hit(match, value, currency)


def _amounts(text: str) -> list[_Hit]:
    return [hit for hit in map(_hit, _AMOUNT.finditer(text)) if hit is not None]


def read_amount_words(text: str) -> tuple[Decimal, str, str] | None:
    """The first money amount in ``text`` as (value, currency, the words as typed), or ``None``."""
    found = [hit for hit in _amounts(text) if hit.value is not None]
    return None if not found else (found[0].value, found[0].currency, found[0].match.group(0))


def _read_amount(text: str, skip: frozenset[str]) -> tuple[str, _Hit | None]:
    found = [] if "amount" in skip else _amounts(text)
    if not found:
        return text, None
    return _remove(text, [found[0].match]), found[0]


def _read_vendor(text: str, skip: frozenset[str]) -> tuple[str, str | None]:
    found = [] if "vendor" in skip else list(_VENDOR.finditer(text))
    if not found:
        return text, None
    last = found[-1]
    return _remove(text, found), (last.group(1) or last.group(2)).strip()


def _first_words(pattern: re.Pattern[str], text: str) -> str | None:
    found = pattern.search(text)
    return None if found is None else found.group(0)


def _last_usable_estimate(text: str) -> str | None:
    usable = [m for m in _ESTIMATE.finditer(text) if 1 <= _minutes(m) <= TASK_ESTIMATE_MAX_MINUTES]
    return usable[-1].group(0) if usable else None


def read_tokens(text: str, skip: frozenset[str] = frozenset()) -> Tokens:
    """Priority, star, estimate, reminder, amount and vendor words out of ``text``."""
    rest, priority, priority_words, warnings = _read_priority(text, skip)
    rest, star = _read_star(rest, skip)
    rest, estimate, estimate_warnings = _read_estimate(rest, skip)
    rest, reminder, reminder_warnings = _read_reminder(rest, skip)
    rest, hit = _read_amount(rest, skip)
    rest, vendor = _read_vendor(rest, skip)
    return Tokens(rest=" ".join(rest.split()), priority=priority, priority_words=priority_words, star=star,
                  estimate_minutes=estimate, reminder_words=reminder,
                  amount=None if hit is None else hit.value, currency=None if hit is None else hit.currency,
                  amount_words=None if hit is None else hit.match.group(0),
                  amount_math=None if hit is None else hit.math, amount_problem=None if hit is None else hit.problem,
                  income=hit is not None and hit.income, vendor=vendor,
                  star_words=_first_words(_STAR, text) if star else None,
                  estimate_words=_last_usable_estimate(text) if estimate is not None else None,
                  warnings=(*warnings, *estimate_warnings, *reminder_warnings))


# --- turning reminder words into a moment --------------------------------------------------------------

def _duration(body: str) -> timedelta | None:
    match = _DURATION.match(body)
    if match is None:
        return None
    hours, minutes, number, unit = match.groups()
    if hours is not None:
        return timedelta(hours=int(hours), minutes=int(minutes or 0))
    value = Decimal(number.replace(",", "."))
    return timedelta(minutes=float(value * (60 if unit.lower().startswith("h") else 1)))


def _due_moment(due: Due) -> datetime | None:
    if due.due_date is None:
        return None
    if len(due.due_date) > len("YYYY-MM-DD"):
        return datetime.fromisoformat(due.due_date)
    day = datetime.fromisoformat(due.due_date).date()
    return datetime.combine(day, time(DAY_ONLY_DUE_HOUR, 0), tzinfo=local_tz())


def _utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _reminder_clock_day(due: Due, now: datetime, at: time) -> datetime:
    local = now.astimezone(local_tz())
    if due.due_date is not None:
        day = datetime.fromisoformat(due.due_date[:10]).date()
        return datetime.combine(day, at, tzinfo=local_tz())
    moment = datetime.combine(local.date(), at, tzinfo=local_tz())
    return moment if moment > local else moment + timedelta(days=1)


def reminder_from(words: str, due: Due, *, now: datetime) -> str | None:
    """The UTC ISO moment reminder ``words`` name against ``due`` (``^1h before`` is an hour before the
    due, 09:00 for a day-only due; ``^9am`` is that time on the due's day, or the next 9am with no due).
    ``ValueError`` with a plain sentence when the words need a due that is not there, or are unreadable."""
    body = _REMIND_PREFIX.sub("", _fold(words.strip()))
    body = _REMIND_SUFFIX.sub("", body).strip()
    length = _duration(body)
    if length is not None:
        base = _due_moment(due)
        if base is None:
            raise ValueError(REMINDER_NEEDS_DUE_TEXT.format(words=words.strip()))
        return _utc(base - length)
    clock = find_clock(f"at {body}" if body.isdigit() else body)
    if clock is None:
        raise ValueError(UNREADABLE_REMINDER_TEXT.format(words=words.strip()))
    return _utc(_reminder_clock_day(due, now, clock.time))
