"""Repeat words (design 2026-10-20 §3), pure: "every Monday and Thursday at 9", "monthly on the 1st",
"todos los días", "cada año" become a local 5-field cron, and a cron reads back in words.

A repeat with no time runs at 09:00 (or at the due hint's time of day). ``weekly``, ``monthly`` and
``yearly`` with no day take the due hint's weekday / day of month / day (Monday, the 1st, 1 January
without one). What a 5-field cron can't say ("every 2 weeks", "every other day") is a ``problem``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from roost.constants import REPEAT_DEFAULT_HOUR, REPEAT_RULE_MAX_EVERY
from roost.tasks.day_words import find_clock, month_number
from roost.tasks.due import Due
from roost.tasks.repeat_rule import RepeatRule, is_rule, parse_rule, readable_rule, rule_json

REPEAT_PROBLEM_TEXT = ("Repeats can be daily, weekdays, weekly, monthly or yearly, every other day or week, "
                       "or every N days, weeks or months.")
WHEN_DONE_PROBLEM_TEXT = "“When done” works with every day, week, month or one weekday, or every N days, weeks or months."

_FOLD = str.maketrans("áéíóúüñ", "aeiouun")
_FLAGS = re.IGNORECASE
_DAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_ES_DAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}
# Short forms (user rulings 2026-10-20). Always after "every" / "cada" here, so "mar" can only be Tuesday.
_SHORT_DAYS = {"mon": 0, "tues": 1, "tue": 1, "wed": 2, "thurs": 3, "thur": 3, "thu": 3, "fri": 4, "sat": 5,
               "sun": 6, "lun": 0, "mar": 1, "mie": 2, "jue": 3, "vie": 4, "sab": 5, "dom": 6}
_DAYS = {**{name: index for index, name in enumerate(_DAY_NAMES)}, **_ES_DAYS, **_SHORT_DAYS}
_NAMES = "|".join(sorted(_DAYS, key=len, reverse=True))
_LIST = rf"(?:{_NAMES})s?(?:(?:\s*,\s*|\s+and\s+|\s+y\s+|\s*,?\s*)(?:{_NAMES})s?)*"
_SUFFIX = r"(?:st|nd|rd|th)?"
_MONTH_WORD = r"[a-z]{3,}"

_PROBLEM = re.compile(r"\b(?:every|cada)\s+(?:other|otro|otra|\d+)\s+[a-z]+\b", _FLAGS)
_WEEKDAYS = re.compile(r"\b(?:every\s+weekday|weekdays|entre\s+semana|laborables|todos\s+los\s+dias\s+laborables)\b",
                       _FLAGS)
_WEEKDAY_LIST = re.compile(rf"\b(?:every|cada|todos\s+los)\s+({_LIST})\b", _FLAGS)
_MONTHLY_ON = re.compile(
    rf"\b(?:(?:monthly|every\s+month|mensual(?:mente)?|cada\s+mes)\s+(?:on\s+)?(?:the\s+|el\s+(?:dia\s+)?)"
    rf"(\d{{1,2}}){_SUFFIX}|(?:on\s+the\s+|el\s+(?:dia\s+)?)(\d{{1,2}}){_SUFFIX}\s+(?:of\s+every\s+month|"
    rf"de\s+cada\s+mes))\b", _FLAGS)
_YEARLY_ON = re.compile(
    rf"\b(?:yearly|every\s+year|annual(?:ly)?|anual|cada\s+ano)\s+(?:on\s+|el\s+)?(?:(\d{{1,2}}){_SUFFIX}\s+"
    rf"(?:of\s+|de\s+)?({_MONTH_WORD})|({_MONTH_WORD})\s+(\d{{1,2}}){_SUFFIX})\b", _FLAGS)
_DAILY = re.compile(r"\b(?:every\s+day|daily|cada\s+dia|todos\s+los\s+dias|diari[oa])\b", _FLAGS)
_WEEKLY = re.compile(r"\b(?:every\s+week|weekly|cada\s+semana|semanal(?:mente)?)\b", _FLAGS)
_MONTHLY = re.compile(r"\b(?:every\s+month|monthly|cada\s+mes|mensual(?:mente)?)\b", _FLAGS)
_YEARLY = re.compile(r"\b(?:every\s+year|yearly|annual(?:ly)?|cada\s+ano|anual(?:mente)?)\b", _FLAGS)
_CRON = re.compile(r"^(\d{1,2}) (\d{1,2}) (\*|\d{1,2}) (\*|\d{1,2}) (\*|[0-6](?:,[0-6])*|1-5)$")
_FOLLOWING_CLOCK = re.compile(r"^\s+")
_UNIT_OF = {"day": "day", "days": "day", "dia": "day", "dias": "day", "week": "week", "weeks": "week",
            "semana": "week", "semanas": "week", "month": "month", "months": "month", "mes": "month",
            "meses": "month", "year": "year", "years": "year", "ano": "year", "anos": "year"}
_UNITS = "|".join(sorted(_UNIT_OF, key=len, reverse=True))
_MONTHS_PER_YEAR = 12
_INTERVAL = re.compile(
    rf"\b(?:every|cada)(!)?\s+(?:(other|otro|otra)\s+|(\d{{1,4}})\s+)?(?:({_UNITS})|({_NAMES}))\b"
    rf"(?!\s*(?:,|and\b|y\b)\s*(?:{_NAMES}))", _FLAGS)
_WHEN_DONE = re.compile(
    r"^\s*,?\s*(?:when\s+(?:it'?s\s+)?(?:done|completed)|once\s+done|after\s+completion|al\s+completar|"
    r"cuando\s+termine)\b", _FLAGS)
_BANG = re.compile(r"\b(?:every|cada)!", _FLAGS)


@dataclass(frozen=True)
class RepeatReading:
    cron: str | None
    words: str
    problem: str | None
    start: int
    end: int
    rule: str | None = None                       # a richer repeat (repeat_rule JSON), stored in `recurring`
    clock: tuple[int, int] | None = None          # the time of day the words named

    @property
    def value(self) -> str | None:
        """What `recurring` stores: the rule, else the cron."""
        return self.rule or self.cron


def _fold(text: str) -> str:
    return text.translate(_FOLD).lower()


def _hint_day(due_hint: Due | None) -> date | None:
    if due_hint is None or due_hint.due_date is None:
        return None
    return date.fromisoformat(due_hint.due_date[:10])


def _hint_time(due_hint: Due | None) -> tuple[int, int]:
    """The due hint's time of day when it names one, else 09:00."""
    if due_hint is not None and due_hint.due_date and len(due_hint.due_date) > len("YYYY-MM-DD"):
        moment = datetime.fromisoformat(due_hint.due_date)
        return moment.hour, moment.minute
    return REPEAT_DEFAULT_HOUR, 0


def _cron_weekday(index: int) -> int:
    return (index + 1) % 7            # Python's Monday=0 is cron's 1; Sunday 6 is cron's 0


def _clock_after(text: str, end: int) -> tuple[tuple[int, int], int] | None:
    """A time of day right after the repeat words ("... at 9", "... 7am", "... 09:00") and where it ends."""
    gap = _FOLLOWING_CLOCK.match(text[end:])
    if gap is None:
        return None
    clock = find_clock(text[end + gap.end():])
    if clock is None or clock.start != 0:
        return None
    return (clock.time.hour, clock.time.minute), end + gap.end() + clock.end


def _weekday_indexes(listed: str) -> list[int]:
    found = {_DAYS[name] for name in re.findall(_NAMES, _fold(listed), _FLAGS)}
    return sorted(found)


def _cron(minute_hour: tuple[int, int], day: str, month: str, weekday: str) -> str:
    hour, minute = minute_hour
    return f"{minute} {hour} {day} {month} {weekday}"


def _read(text: str, hint: Due | None) -> tuple[str | None, int, int, str | None] | None:
    """(cron minus its time, start, end, problem) for the first repeat the words name, in the order the
    design lists them: a problem first, then the specific forms, then the plain ones."""
    folded = _fold(text)
    if (m := _PROBLEM.search(folded)):
        return None, m.start(), m.end(), REPEAT_PROBLEM_TEXT
    day = _hint_day(hint)
    if (m := _WEEKDAYS.search(folded)):
        return "* * 1-5", m.start(), m.end(), None
    if (m := _WEEKDAY_LIST.search(folded)):
        days = ",".join(str(_cron_weekday(i)) for i in sorted(_weekday_indexes(m.group(1)), key=_cron_weekday))
        return f"* * {days}", m.start(), m.end(), None
    if (m := _MONTHLY_ON.search(folded)):
        number = int(m.group(1) or m.group(2))
        return (f"{number} * *", m.start(), m.end(), None) if 1 <= number <= 31 else (
            None, m.start(), m.end(), REPEAT_PROBLEM_TEXT)
    if (m := _YEARLY_ON.search(folded)):
        number = month_number(m.group(2) or m.group(3))
        if number is not None:
            return f"{int(m.group(1) or m.group(4))} {number} *", m.start(), m.end(), None
    for pattern, rest in ((_DAILY, "* * *"),
                          (_WEEKLY, f"* * {_cron_weekday(day.weekday()) if day else 1}"),
                          (_MONTHLY, f"{day.day if day else 1} * *"),
                          (_YEARLY, f"{day.day if day else 1} {day.month if day else 1} *")):
        if (m := pattern.search(folded)):
            return rest, m.start(), m.end(), None
    return None


def find_repeat(text: str, *, due_hint: Due | None) -> RepeatReading | None:
    """The repeat the words name, as a cron and the span of words it came from; ``None`` when they name
    none. A repeat a cron can't say has ``cron=None`` and a ``problem``. ``due_hint`` is the due the line
    already names: it gives the time of day, and the weekday, day of month or day of a bare
    weekly / monthly / yearly."""
    if (interval := _read_interval(text, due_hint)) is not None:
        return interval
    found = _read(text, due_hint)
    if found is None:
        return _bang_problem(text)
    rest, start, end, problem = found
    if rest is None:
        return RepeatReading(None, text[start:end], problem, start, end)
    clock = _clock_after(text, end)
    when, stop = clock if clock else (_hint_time(due_hint), end)
    if (done := _WHEN_DONE.match(_fold(text[stop:]))) is not None:      # a cron can't repeat from completion
        return RepeatReading(None, text[start:stop + done.end()], WHEN_DONE_PROBLEM_TEXT, start, stop + done.end())
    day, month, weekday = rest.split()
    return RepeatReading(_cron(when, day, month, weekday), text[start:stop], None, start, stop, clock=when if clock else None)


def _bang_problem(text: str) -> RepeatReading | None:
    found = _BANG.search(_fold(text))
    if found is None:
        return None
    return RepeatReading(None, text[found.start():found.end()], WHEN_DONE_PROBLEM_TEXT, found.start(), found.end())


def _interval_rule(match: re.Match[str], from_completion: bool) -> RepeatRule | None:
    """The rule the matched words name, or ``None`` when its number is out of range."""
    bang, other, number, unit, name = match.groups()
    every = 2 if other else int(number) if number else 1
    if name is not None:
        kind, weekday = "week", _DAYS[name]
    else:
        kind, weekday = _UNIT_OF[unit], None
        if kind == "year":
            kind, every = "month", every * _MONTHS_PER_YEAR
    if not 1 <= every <= REPEAT_RULE_MAX_EVERY:
        return None
    return RepeatRule(every=every, unit=kind, weekday=weekday, from_completion=from_completion)


def _read_interval(text: str, due_hint: Due | None) -> RepeatReading | None:
    """"every other X", "every N days / weeks / months", and any of those or a lone day / week / month /
    weekday with ``every!`` or "when done" (repeat from completion). The rest is the plain reader's."""
    folded = _fold(text)
    match = _INTERVAL.search(folded)
    if match is None:
        return None
    bang, other, number, unit, name = match.groups()
    clock = _clock_after(text, match.end())
    when, stop = clock if clock else (None, match.end())
    done = _WHEN_DONE.match(folded[stop:])
    flagged = bool(bang) or done is not None
    if not (other or number or flagged) or (name is not None and (number or not (other or flagged))):
        return None
    end = stop + (done.end() if done else 0)
    rule = _interval_rule(match, flagged)
    if rule is None:
        return RepeatReading(None, text[match.start():end], REPEAT_PROBLEM_TEXT, match.start(), end)
    cron = None
    if rule.weekday is not None:
        hour, minute = when or _hint_time(due_hint)
        cron = _cron((hour, minute), "*", "*", str(_cron_weekday(rule.weekday)))
    return RepeatReading(cron, text[match.start():end], None, match.start(), end, rule=rule_json(rule), clock=when)


# --- reading a cron back -------------------------------------------------------------------------------

def _ordinal(number: int) -> str:
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def _day_list(numbers: list[str]) -> str:
    names = [_DAY_NAMES[(int(n) - 1) % 7].capitalize() for n in numbers]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def readable(cron: str) -> str:
    """The cron in words ("every Monday 09:00"), the same words ``find_repeat`` reads back. A cron the
    line and the drawer never make is returned as it is."""
    if is_rule(cron):
        try:
            return readable_rule(parse_rule(cron))
        except ValueError:
            return cron
    match = _CRON.match(cron.strip())
    if match is None:
        return cron
    minute, hour, day, month, weekday = match.groups()
    clock = f"{int(hour):02d}:{int(minute):02d}"
    if day == "*" and month == "*":
        if weekday == "*":
            return f"every day {clock}"
        if weekday == "1-5":
            return f"every weekday {clock}"
        return f"every {_day_list(weekday.split(','))} {clock}"
    if weekday != "*":
        return cron
    if month == "*":
        return f"every month on the {_ordinal(int(day))} {clock}"
    if day == "*":
        return cron
    return f"every year on {int(day)} {_month_name(int(month))} {clock}"


def _month_name(number: int) -> str:
    return date(2000, number, 1).strftime("%B") if 1 <= number <= 12 else str(number)
