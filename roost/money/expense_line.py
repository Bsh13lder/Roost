"""The expense quick line (Task 6): ``€12 lunch /Trip yesterday vendor:Mercadona *``.

The server reads the whole line and the web draws its chips from this reading, so what is added is exactly
what was shown. In order:

- the one-word tokens (``line_tokens``): the amount (``€12``, ``12,50€``, maths like ``€2x31``, and a leading
  ``+`` for money in), ``vendor:Name`` / ``tienda:"Name"``, and ``*`` the star. Priority, estimate and
  reminder words are not read: they stay in the note;
- ``/Trip``: the project, exact or ask (``ProjectService.resolve`` with ``change=True``), never made. A
  ``#word`` is not a project: it stays in the note. A project's page passes its project as the default;
- a repeat word (``monthly``, ``every week``): the cadence, weekly / monthly / yearly only;
- the day: a day in the past or today (``yesterday``, ``ayer``, ``15 march``, ``friday``); a future one is a
  problem, never logged;
- a bare number as the first or last word (``12 lunch``) when no money sign was typed: the amount, in the
  project's currency;
- what is left is the note.

``skip`` names the kinds the user dismissed from the chips: their words stay in the note."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from roost.constants import DEFAULT_CURRENCY, MAX_EXPENSE_NOTE_LENGTH, MAX_EXPENSE_VENDOR_LENGTH
from roost.money.amounts import amount_text
from roost.money.expression import EXPRESSION_PATTERN, TOO_LONG_TEXT, ExpressionError, evaluate, has_operator
from roost.money.amounts import number_value, too_many_digits
from roost.money.models import Project
from roost.money.months import today_madrid
from roost.money.project_store import is_general
from roost.projects.service import NO_PROJECT_TEXT, ProjectRefusal, ProjectService
from roost.timezones import local_tz
from roost.tasks.day_words import find_day
from roost.tasks.line_tokens import TWO_KINDS_TEXT, read_tokens
from roost.tasks.quick_line import NO_PROJECT_HERE_TEXT, PROJECT_GONE_TEXT, read_words
from roost.tasks.repeat_words import find_repeat

ExpenseKind = ("amount", "project", "date", "star", "vendor", "repeat")
MONEY_IN_REPEAT_TEXT = "Money in (+) can't repeat yet: take off the repeat word, or log each one on its own."
FUTURE_DAY_TEXT = "“{words}” is a future day; the latest I can log is {today}."
REPEAT_CADENCE_TEXT = "An expense repeats weekly, monthly or yearly."
NOTE_LONG_TEXT = f"A note holds at most {MAX_EXPENSE_NOTE_LENGTH} characters."
VENDOR_LONG_TEXT = f"A vendor holds at most {MAX_EXPENSE_VENDOR_LENGTH} characters."
ARCHIVED_LINE_TEXT = "“{name}” is archived; unarchive it first."

_TOKEN_SKIP = frozenset({"priority", "estimate", "reminder"})     # task-line words: left in the note
_PROJECT_SKIP = frozenset({"priority", "budget"})                  # read_words reads only the project
_ARCHIVED = "archived"
_VENDOR_WORDS = re.compile(r'(?<!\S)(?:vendor|tienda):(?:"[^"]+"|\S+)', re.IGNORECASE)
_BARE = re.compile(rf"(\+)?({EXPRESSION_PATTERN})")


@dataclass(frozen=True)
class ExpenseLine:
    note: str
    amount: Decimal | None = None
    currency: str | None = None             # the typed money sign's; None: the project's
    income: bool = False                    # a leading + : money in
    amount_words: str | None = None
    amount_math: str | None = None          # "2×31" when the amount was worked out
    amount_problem: str | None = None
    project: Project | None = None
    project_words: str | None = None
    project_question: str | None = None     # why the /project can't be used as typed
    spent_at: str = ""
    day_words: str | None = None
    day_problem: str | None = None
    vendor: str | None = None
    starred: bool = False
    cadence: str | None = None              # weekly | monthly | yearly
    repeat_words: str | None = None
    repeat_problem: str | None = None
    text_problem: str | None = None         # a note or vendor too long to save
    matches: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @property
    def income_problem(self) -> str | None:
        return MONEY_IN_REPEAT_TEXT if self.income and self.cadence else None

    @property
    def shown_currency(self) -> str:
        return self.currency or (self.project.currency if self.project else DEFAULT_CURRENCY)

    @property
    def ready(self) -> bool:
        return self.amount is not None and not (
            self.amount_problem or self.project_question or self.day_problem or self.repeat_problem
            or self.text_problem or self.income_problem)


def _cut(text: str, start: int, end: int) -> str:
    return f"{text[:start]} {text[end:]}"


def _read_projects(rest: str, skip: frozenset[str], names: Sequence[str]) -> tuple[str, str | None, str | None,
                                                                                    tuple[str, ...]]:
    """Every ``/project`` leaves the line; the last is the project. Returns rest, ref, words, warnings."""
    if "project" in skip:
        return rest, None, None, ()
    keep = skip | _PROJECT_SKIP
    last, count = read_words(rest, keep, names), 0
    while last.project_ref is not None:
        count += 1
        more = read_words(last.rest, keep, names)
        if more.project_ref is None:
            break
        last = more
    if count == 0:
        return rest, None, None, ()
    warnings = (TWO_KINDS_TEXT.format(kind="projects", kept=last.project_words),) if count > 1 else ()
    return last.rest, last.project_ref, last.project_words, warnings


async def _project(projects: ProjectService, user_id: str, ref: str | None,
                   default_id: str | None) -> tuple[Project | None, str | None]:
    wanted = ref if ref is not None else default_id
    if wanted is None:
        return None, None
    found = await projects.resolve(user_id, wanted, change=True)
    if isinstance(found, ProjectRefusal):
        if ref is None:
            return None, PROJECT_GONE_TEXT       # the page's own project, deleted meanwhile (or not the user's)
        unknown = str(found) == NO_PROJECT_TEXT.format(name=ref.strip())
        return None, NO_PROJECT_HERE_TEXT.format(name=ref.strip()) if unknown else str(found)
    if found.status == _ARCHIVED:
        return None, ARCHIVED_LINE_TEXT.format(name=found.name)
    return found, None


def cadence_of(cron: str | None, rule: str | None) -> str | None:
    """weekly / monthly / yearly for a 5-field cron that says exactly one of them; ``None`` otherwise."""
    if rule is not None or cron is None or len(cron.split()) != 5:
        return None
    _, _, day, month, weekday = cron.split()
    if day == "*" and month == "*" and weekday.isdigit():
        return "weekly"
    if day.isdigit() and month == "*" and weekday == "*":
        return "monthly"
    if day.isdigit() and month.isdigit() and weekday == "*":
        return "yearly"
    return None


def _read_repeat(rest: str, skip: frozenset[str]) -> tuple[str, str | None, str | None, str | None]:
    """The text without the repeat words, the cadence, its words and its problem."""
    reading = None if "repeat" in skip else find_repeat(rest, due_hint=None)
    if reading is None:
        return rest, None, None, None
    cadence = None if reading.problem else cadence_of(reading.cron, reading.rule)
    problem = None if cadence else REPEAT_CADENCE_TEXT
    return _cut(rest, reading.start, reading.end), cadence, reading.words.strip(), problem


def _default_day(default_day: str | None, today: str) -> tuple[str, str | None, str | None]:
    """The day a line that names none gets: ``default_day`` (the calendar's) or today. A future one is a problem,
    like a future typed day, and the day falls back to today."""
    if default_day is None:
        return today, None, None
    if default_day > today:
        return today, None, FUTURE_DAY_TEXT.format(words=_day_text(default_day), today=today)
    return default_day, None, None


def _read_day(rest: str, skip: frozenset[str], now: datetime,
              default_day: str | None = None) -> tuple[str, str, str | None, str | None]:
    """The text without the day words, the day (ISO), its words and its problem; no words: ``default_day``, else today."""
    today = today_madrid(now)
    fallback, no_words, fallback_problem = _default_day(default_day, today)
    if "date" in skip:
        return rest, fallback, no_words, fallback_problem
    clock = now.astimezone(local_tz())
    reading = find_day(rest, now=clock, direction="past") or find_day(rest, now=clock, direction="forward")
    if reading is None:
        return rest, fallback, no_words, fallback_problem
    words = rest[reading.start:reading.end].strip()
    day = reading.day.isoformat()
    problem = FUTURE_DAY_TEXT.format(words=words, today=today) if day > today else None
    return _cut(rest, reading.start, reading.end), day if problem is None else today, words, problem


def _bare_amount(rest: str) -> tuple[str, Decimal | None, bool, str | None, str | None, str | None]:
    """A number (or sum) as the first or last word of the note: rest, value, income, math, problem, words."""
    words = rest.split()
    for index in (0, -1):
        if not words:
            break
        found = _BARE.fullmatch(words[index])
        if found is None:
            continue
        digits = found.group(2)
        try:
            if has_operator(digits):
                worked = evaluate(digits)
                value, math = worked.value, worked.shown
            else:
                value, math = number_value(digits), None
                if value is None and too_many_digits(digits):
                    raise ExpressionError(TOO_LONG_TEXT)
        except ExpressionError as exc:
            return rest, None, False, None, str(exc), words[index]
        if value is None or value <= 0:
            continue
        remaining = words[1:] if index == 0 else words[:-1]
        return " ".join(remaining), value, found.group(1) is not None, math, None, words[index]
    return rest, None, False, None, None, None


def _matches(line: ExpenseLine, original: str, star: bool) -> dict[str, tuple[str, ...]]:
    vendor = _VENDOR_WORDS.search(original)
    found = {
        "amount": (line.amount_words,) if line.amount_words else (),
        "project": (line.project_words,) if line.project_words else (),
        "date": (line.day_words,) if line.day_words else (),
        "star": ("*",) if star else (),
        "vendor": (vendor.group(0),) if vendor and line.vendor else (),
        "repeat": (line.repeat_words,) if line.repeat_words else (),
    }
    return {kind: words for kind, words in found.items() if words}


async def read_expense_line(projects: ProjectService, user_id: str, text: str, *, project_id: str | None = None,
                            skip: frozenset[str] = frozenset(), now: datetime | None = None,
                            default_day: str | None = None) -> ExpenseLine:
    moment = now or datetime.now(local_tz())
    tokens = read_tokens(text, frozenset(skip) | _TOKEN_SKIP)
    rest, ref, project_words, project_warnings = _read_projects(tokens.rest, skip, await projects.names(user_id))
    rest, cadence, repeat_words, repeat_problem = _read_repeat(rest, skip)
    rest, spent_at, day_words, day_problem = _read_day(rest, skip, moment, default_day)
    amount, income, math, problem, words = tokens.amount, tokens.income, tokens.amount_math, tokens.amount_problem, \
        tokens.amount_words
    if amount is None and problem is None and "amount" not in skip:
        rest, amount, income, math, problem, words = _bare_amount(" ".join(rest.split()))
    project, question = await _project(projects, user_id, ref, project_id)
    note = " ".join(rest.split())
    too_long = NOTE_LONG_TEXT if len(note) > MAX_EXPENSE_NOTE_LENGTH else (
        VENDOR_LONG_TEXT if tokens.vendor and len(tokens.vendor) > MAX_EXPENSE_VENDOR_LENGTH else None)
    line = ExpenseLine(
        note=note, amount=amount, currency=tokens.currency if tokens.amount is not None else None, income=income,
        amount_words=words, amount_math=math, amount_problem=problem, project=project,
        project_words=project_words, project_question=question, spent_at=spent_at, day_words=day_words,
        day_problem=day_problem, vendor=tokens.vendor, starred=tokens.star, cadence=cadence,
        repeat_words=repeat_words, repeat_problem=repeat_problem, text_problem=too_long,
        warnings=(*tokens.warnings, *project_warnings),
    )
    return replace(line, matches=_matches(line, text, tokens.star))


def _day_text(day: str) -> str:
    return date.fromisoformat(day).strftime("%a %-d %b")


def expense_line_out(line: ExpenseLine) -> dict[str, Any]:
    """``ExpenseLineOut``: what the web shows as chips and sends to add the expense. Amounts are strings."""
    project = None if line.project is None else {
        "id": line.project.id, "name": line.project.name, "currency": line.project.currency,
        "color": line.project.color, "is_general": is_general(line.project),
    }
    return {
        "note": line.note, "amount": None if line.amount is None else amount_text(line.amount),
        "currency": line.shown_currency, "income": line.income, "income_problem": line.income_problem,
        "amount_words": line.amount_words, "amount_math": line.amount_math, "amount_problem": line.amount_problem,
        "project": project, "project_words": line.project_words, "project_question": line.project_question,
        "spent_at": line.spent_at, "spent_text": _day_text(line.spent_at), "day_words": line.day_words,
        "day_problem": line.day_problem, "vendor": line.vendor, "starred": line.starred, "cadence": line.cadence,
        "repeat_words": line.repeat_words, "repeat_problem": line.repeat_problem,
        "text_problem": line.text_problem, "ready": line.ready,
        "matches": {kind: list(words) for kind, words in line.matches.items()}, "warnings": list(line.warnings),
    }
