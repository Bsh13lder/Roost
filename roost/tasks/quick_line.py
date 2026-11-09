"""The quick-add line (redesign P3): ``Call plumber tomorrow 9am #Renovation €200 !high``.

The server reads the whole line, and the web draws its chips from this reading, so what is added is
exactly what was shown. In order:

- the one-word tokens (``line_tokens``): the priority (``!!``, ``!high``, or urgent / baja as the first or
  last word), ``*`` the star, ``~1h30`` the estimate, ``^9am`` / ``^1h before`` the reminder, and
  ``€200`` / ``1.200€`` the budget slice, in the money sign's currency, which must be the project's, or
  General's for a task in no project (owner, 2026-10-26, as in the drawer; bots keep H11);
- ``@Scout``: the bot to hand the task to, by name or a unique start of one (a question when none or
  several fit; the web asks you to confirm before anything is sent);
- ``/Renovation``: the project, exact or ask (``ProjectService.resolve`` with ``change=True``: its id,
  its exact name or a unique part of one; a near miss is a question, never a guess, never a new project,
  never General). A project page passes its project as the default;
- a repeat (``repeat_words``: "every Monday", "monthly on the 1st"); with no date the due is its first
  occurrence;
- the date, by the ``day_words`` grammar a typed due follows (``due_from_parsed``);
- what is left is the title.

Two of one kind: the last wins and a warning says so. ``skip`` names the kinds the user dismissed from
the chips: their words stay in the title."""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal, Mapping, Sequence

from croniter import croniter

from roost.bots.models import Bot
from roost.constants import GENERAL_PROJECT_NAME, MAX_TASK_TAG_LENGTH, MAX_TASK_TAGS, QUICK_LINE_CURRENCIES
from roost.money.amounts import amount_text, parse_amount
from roost.money.models import Project
from roost.money.project_store import is_general
from roost.projects.service import GENERAL_FIXED_TEXT, NO_PROJECT_TEXT, ProjectRefusal, ProjectService
from roost.timezones import local_tz
from roost.tasks import nl_time
from roost.tasks.day_words import find_clock
from roost.tasks.due import Due, due_from_parsed
from roost.tasks.due_preview import preview
from roost.tasks.line_tokens import TWO_KINDS_TEXT, Tokens, edge_priority, read_tokens, reminder_from
from roost.tasks.models import Priority
from roost.tasks.repeat_rule import is_rule, parse_rule
from roost.tasks.repeat_words import RepeatReading, find_repeat, readable

QuickKind = Literal["date", "project", "budget", "priority", "star", "estimate", "reminder", "repeat", "assignee",
                    "tag"]
NO_BOT_HERE_TEXT = "No bot is called “{name}”."
MANY_BOTS_TEXT = "More than one bot starts with “{name}”: type more of its name."
SLICE_CURRENCY_TEXT = "“{name}” keeps its money in {currency}: write the budget in {currency}."
TAG_TOO_LONG_TEXT = "“{tag}” is too long for a tag (at most {limit} letters): it stays in the title."
TOO_MANY_TAGS_TEXT = "A task holds at most {limit} tags: the rest are dropped."
NO_PROJECT_HERE_TEXT = "No project is called “{name}”. Make it on the Projects tab first."
INCOME_BUDGET_TEXT = "A budget is money going out: take off the + (money in is for expenses)."
PROJECT_GONE_TEXT = "This project is gone."

_SIGNS = "".join(sign for sign, _ in QUICK_LINE_CURRENCIES)
_CURRENCY_OF = dict(QUICK_LINE_CURRENCIES)
_NUMBER = r"\d+(?:[.,]\d{1,2})?"
_PRIORITY = re.compile(r"(?<!\S)!(urgent|high|medium|low)(?!\S)", re.IGNORECASE)
_AMOUNT = re.compile(rf"(?<!\S)(?:([{_SIGNS}])\s?({_NUMBER})|({_NUMBER})\s?([{_SIGNS}]))(?!\S)")
_PROJECT = re.compile(r"(?<!\S)/([^\s/]+)")          # /Renovation: the project
_TAG = re.compile(r"(?<!\S)#([^\W\d_][\w\-]*)")           # #shopping: a tag (starts with a letter)
_WORD = re.compile(r"\S+")
_ASSIGN = re.compile(r"(?<!\S)@(\S+)")
_NO_DUE = Due(None, None)
_TOKEN_KIND = {"budget": "amount"}          # a quick-line kind that line_tokens calls something else
_PROJECT_ONLY = frozenset({"priority", "budget"})    # the tokens are read first: read_words keeps to the project
_EDGE_PUNCTUATION = ".,;:!?"
_STARTING = re.compile(r"(?<!\S)(?:starting|starts?|empezando)(?:\s+(?:on|from|el))?(?=\s)", re.IGNORECASE)
_ENDING = re.compile(r"(?<!\S)(?:ending|ends?|until|hasta|terminando)(?:\s+(?:on|el))?\s+", re.IGNORECASE)
_MASK = "\ue000"          # stands in for dismissed repeat words while the date is read


@dataclass(frozen=True)
class LineWords:
    """The line with the priority, amount and project words taken out, and what they said."""

    rest: str
    priority: Priority | None = None
    amount: str | None = None           # "200", "12,50"
    currency: str | None = None         # the money sign's currency
    budget_words: str | None = None     # "€200", as typed
    project_ref: str | None = None      # "Renovation"
    project_words: str | None = None    # "#Renovation", as typed


@dataclass(frozen=True)
class QuickLine:
    title: str
    due: Due
    priority: Priority | None
    project: Project | None
    project_words: str | None
    project_question: str | None        # why the #project can't be used as typed
    budget: Decimal | None
    budget_words: str | None
    budget_problem: str | None          # why the amount can't be the slice
    budget_math: str | None = None      # "3×45": the sum the budget was worked out from
    budget_currency: str | None = None  # the budget's currency: the project's, or General's with no project
    starred: bool = False
    estimate_minutes: int | None = None
    reminder_at: str | None = None      # UTC ISO; from the ^reminder words, against the due
    reminder_words: str | None = None
    recurring: str | None = None        # a local cron
    repeat_words: str | None = None     # as typed
    repeat_problem: str | None = None   # a repeat the words can't say
    recur_until: str | None = None      # "ending <date>": the series' last day
    tags: tuple[str, ...] = ()          # #shopping
    matches: Mapping[str, tuple[str, ...]] = field(default_factory=dict)   # kind -> the words of its chip
    assignee: Bot | None = None
    assignee_words: str | None = None
    assignee_question: str | None = None
    warnings: tuple[str, ...] = ()

    @property
    def repeat_text(self) -> str | None:
        if self.recurring is None:
            return None
        ended = "" if self.recur_until is None else f", until {_day_text(self.recur_until)}"
        return f"{readable(self.recurring)}{ended}"

    @property
    def ready(self) -> bool:
        return bool(self.title) and not (self.project_question or self.budget_problem or self.repeat_problem
                                         or self.assignee_question)


@dataclass(frozen=True)
class _Assigned:
    rest: str
    bot: Bot | None = None
    words: str | None = None
    question: str | None = None
    warnings: tuple[str, ...] = ()


def _cut(text: str, match: re.Match[str]) -> str:
    return f"{text[:match.start()]} {text[match.end():]}"


def _long_name(rest: str, found: re.Match[str], names: Sequence[str]) -> tuple[str, int] | None:
    """The longest run of words from the ``#`` on (two or more) that is one of ``names``, compared
    case-insensitively with single spaces: that name and where the run ends in ``rest``."""
    wanted = {" ".join(name.split()).casefold(): name for name in names}
    reach = max((len(name.split()) for name in wanted), default=0)
    ends = [(word.group(0), word.end()) for word in itertools.islice(_WORD.finditer(rest, found.start() + 1), reach)]
    for count in range(len(ends), 1, -1):
        typed = " ".join(word for word, _ in ends[:count]).casefold()
        if typed in wanted:
            return wanted[typed], ends[count - 1][1]
    return None


def read_words(text: str, skip: frozenset[str] = frozenset(),
               project_names: Sequence[str] = ()) -> LineWords:
    """The pure part: priority, amount and project words, each the first of its kind. After ``#`` the
    longest run of words that is one of ``project_names`` is the project; failing that, its first word."""
    words = LineWords(rest=text)
    found = None if "priority" in skip else _PRIORITY.search(words.rest)
    if found:
        words = replace(words, rest=_cut(words.rest, found), priority=found.group(1).lower())
    found = None if "budget" in skip else _AMOUNT.search(words.rest)
    if found:
        words = replace(words, rest=_cut(words.rest, found), amount=found.group(2) or found.group(3),
                        currency=_CURRENCY_OF[found.group(1) or found.group(4)], budget_words=found.group(0))
    found = None if "project" in skip else _PROJECT.search(words.rest)
    if found:
        long = _long_name(words.rest, found, project_names)
        if long is None:
            return replace(words, rest=_cut(words.rest, found), project_ref=found.group(1),
                           project_words=found.group(0))
        name, end = long
        rest = f"{words.rest[:found.start()]} {words.rest[end:]}"
        return replace(words, rest=rest, project_ref=name, project_words=words.rest[found.start():end])
    return words


def read_date_words(text: str, skip: frozenset[str] = frozenset()) -> tuple[Due, str, tuple[str, ...]]:
    """The due the words name, the words left, and the words it came from (the day, and a time of day
    that went with it); a day past the calendar's ends reads as none."""
    if "date" in skip:
        return _NO_DUE, text, ()
    try:
        parsed = nl_time.parse(text, tz=local_tz())
        if parsed.due_date is None:
            return _NO_DUE, text, ()
        clock = find_clock(text)
        words = (parsed.matched,) if parsed.matched else ()
        if clock is not None and text[clock.start:clock.end].strip() not in words:
            words = (*words, text[clock.start:clock.end].strip())
        return due_from_parsed(parsed, text, local_tz()), parsed.remaining, words
    except (OverflowError, ValueError):
        return _NO_DUE, text, ()


def read_date(text: str, skip: frozenset[str] = frozenset()) -> tuple[Due, str]:
    """The due the words name and the words left; a day past the calendar's ends reads as none."""
    due, left, _ = read_date_words(text, skip)
    return due, left


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
    if is_general(found):
        return None, GENERAL_FIXED_TEXT
    return found, None


async def _home(projects: ProjectService, user_id: str, tokens: Tokens,
                project: Project | None) -> tuple[str, str] | None:
    """Where a typed budget counts: the project's name and currency, or General's for no project
    (owner, 2026-10-26). ``None`` when the line has no amount, so nothing is read."""
    if tokens.amount is None:
        return None
    if project is not None:
        return project.name, project.currency
    return GENERAL_PROJECT_NAME, await projects.general_currency(user_id)


def _budget(tokens: Tokens, home: tuple[str, str] | None) -> tuple[Decimal | None, str | None]:
    if tokens.amount_problem is not None:
        return None, tokens.amount_problem
    if tokens.amount is None or home is None:
        return None, None
    if tokens.income:
        return None, INCOME_BUDGET_TEXT
    name, currency = home
    if tokens.currency != currency:
        return None, SLICE_CURRENCY_TEXT.format(name=name, currency=currency)
    try:
        return parse_amount(tokens.amount), None
    except ValueError as exc:
        return None, str(exc)


def _bot_key(name: str) -> str:
    return " ".join(name.split()).casefold()


def _take_assignee(rest: str, bots: Sequence[Bot]) -> _Assigned | None:
    """The first ``@name``: the longest run of words that is a bot's name, else a unique start of one."""
    found = _ASSIGN.search(rest)
    if found is None:
        return None
    names = {_bot_key(bot.name): bot for bot in bots}
    reach = max((len(name.split()) for name in names), default=1)
    ends = [(word.group(0), word.end()) for word in itertools.islice(_WORD.finditer(rest, found.start()), reach)]
    for count in range(len(ends), 0, -1):
        typed = _bot_key(" ".join(word for word, _ in ends[:count]).lstrip("@").rstrip(_EDGE_PUNCTUATION))
        if typed in names:
            end = ends[count - 1][1]
            return _Assigned(f"{rest[:found.start()]} {rest[end:]}", names[typed], rest[found.start():end])
    first, end = ends[0][0].lstrip("@").rstrip(_EDGE_PUNCTUATION), ends[0][1]
    starts = [bot for key, bot in names.items() if key.startswith(first.casefold())]
    rest_without = f"{rest[:found.start()]} {rest[end:]}"
    words = rest[found.start():end]
    if len(starts) == 1:
        return _Assigned(rest_without, starts[0], words)
    text = NO_BOT_HERE_TEXT if not starts else MANY_BOTS_TEXT
    return _Assigned(rest_without, None, words, text.format(name=first))


def _read_tags(rest: str, skip: frozenset[str]) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """Every ``#tag`` leaves the line (one longer than a tag may be stays, with a warning); a tag typed twice
    (any case) counts once; past ``MAX_TASK_TAGS`` the rest are dropped, with a warning."""
    if "tag" in skip:
        return rest, (), ()
    tags: list[str] = []
    warnings: list[str] = []
    cuts: list[re.Match[str]] = []
    dropped = False
    for found in _TAG.finditer(rest):
        tag = found.group(1)
        if len(tag) > MAX_TASK_TAG_LENGTH:
            warnings.append(TAG_TOO_LONG_TEXT.format(tag=found.group(0), limit=MAX_TASK_TAG_LENGTH))
            continue
        cuts.append(found)
        if tag.casefold() in {kept.casefold() for kept in tags}:
            continue
        if len(tags) < MAX_TASK_TAGS:
            tags.append(tag)
        else:
            dropped = True
    for found in reversed(cuts):
        rest = _cut(rest, found)
    if dropped:
        warnings.append(TOO_MANY_TAGS_TEXT.format(limit=MAX_TASK_TAGS))
    return rest, tuple(tags), tuple(warnings)


def _read_assignee(rest: str, bots: Sequence[Bot], skip: frozenset[str]) -> _Assigned:
    """Every ``@name`` leaves the line; the last one is the assignee, and two warn."""
    found: list[_Assigned] = []
    while "assignee" not in skip and (taken := _take_assignee(found[-1].rest if found else rest, bots)):
        found.append(taken)
    if not found:
        return _Assigned(rest)
    last = found[-1]
    warnings = (TWO_KINDS_TEXT.format(kind="assignees", kept=last.words),) if len(found) > 1 else ()
    return replace(last, warnings=warnings)


def _read_projects(rest: str, skip: frozenset[str], names: Sequence[str]) -> tuple[LineWords, tuple[str, ...]]:
    """Every ``#project`` leaves the line; the last one is the project, and two warn."""
    keep = skip | _PROJECT_ONLY
    last = read_words(rest, keep, names)
    count = 0 if last.project_ref is None else 1
    while count and (more := read_words(last.rest, keep, names)).project_ref is not None:
        last, count = more, count + 1
    warnings = (TWO_KINDS_TEXT.format(kind="projects", kept=last.project_words),) if count > 1 else ()
    return last, warnings


def _day_text(stamp: str) -> str:
    return datetime.fromisoformat(stamp[:10]).strftime("%a %-d %b %Y")


def _take_ending(rest: str) -> tuple[str, str | None, tuple[str, ...]]:
    """"ending <date>" / "until <date>": the series' last day and the line without those words. The date
    words are read from the keyword to the line's end; what they leave behind goes back in the line."""
    found = _ENDING.search(rest)
    if found is None:
        return rest, None, ()
    tail, left, date_words = read_date_words(rest[found.end():], frozenset())
    if tail.due_date is None:
        return rest, None, ()
    return f"{rest[:found.start()]} {left}", tail.due_date, (found.group(0).strip(), *date_words)


def _without_starting(rest: str) -> tuple[str, tuple[str, ...]]:
    return _STARTING.sub(" ", rest), tuple(found.group(0).strip() for found in _STARTING.finditer(rest))


def _without(text: str, reading: RepeatReading | None) -> str:
    return text if reading is None else f"{text[:reading.start]} {text[reading.end:]}"


def _first_occurrence(reading: RepeatReading, now: datetime) -> Due:
    """The due a repeat with no date starts on: a cron's next time, else (a rule with no weekday) today,
    at the time named or, when that has passed, tomorrow."""
    start = now.astimezone(local_tz())
    if reading.cron is not None:
        following = croniter(reading.cron, start).get_next(datetime)
        local = following if following.tzinfo else following.replace(tzinfo=local_tz())
        return Due(local.isoformat(timespec="seconds"), local.astimezone(timezone.utc).isoformat())
    if reading.clock is None:
        return Due(start.date().isoformat(), None)
    local = datetime.combine(start.date(), time(*reading.clock), tzinfo=local_tz())
    local = local if local > start else local + timedelta(days=1)
    return Due(local.isoformat(timespec="seconds"), local.astimezone(timezone.utc).isoformat())


@dataclass(frozen=True)
class _RepeatRead:
    reading: RepeatReading | None
    due: Due
    left: str
    until: str | None = None
    date_words: tuple[str, ...] = ()
    extra_words: tuple[str, ...] = ()          # "starting", "ending 2027-06-30": they go with the repeat


def _read_repeat(rest: str, skip: frozenset[str], now: datetime) -> _RepeatRead:
    """The repeat, the due (the date's, else the repeat's first occurrence), the words left and the
    series' end. A bare weekly / monthly / yearly takes its day and time from the due the date names.
    "starting" and "ending" words belong to a repeat: with none they stay in the line."""
    reading = find_repeat(rest, due_hint=None)
    if reading is not None and "repeat" in skip:      # dismissed: its words stay, and the date reader skips them
        due, left, words = read_date_words(f"{rest[:reading.start]}{_MASK}{rest[reading.end:]}", skip)
        return _RepeatRead(None, due, left.replace(_MASK, reading.words), None, words)
    until, extra = None, ()
    if reading is not None:
        rest, until, ending_words = _take_ending(rest)
        rest, starting_words = _without_starting(rest)
        extra = (*starting_words, *ending_words)
        reading = find_repeat(rest, due_hint=None)
    due, left, words = read_date_words(_without(rest, reading), skip)
    done = _RepeatRead(reading, due, left, until, words, extra)
    if reading is None or (reading.cron is None and reading.rule is None) or reading.problem:
        return done
    if due.due_date is None:
        return replace(done, due=_first_occurrence(reading, now))
    if reading.cron is None:
        return done
    return replace(done, reading=find_repeat(rest, due_hint=due) or reading)


def _reminder(tokens: Tokens, due: Due, now: datetime) -> tuple[str | None, tuple[str, ...]]:
    if tokens.reminder_words is None:
        return None, ()
    try:
        return reminder_from(tokens.reminder_words, due, now=now), ()
    except ValueError as exc:
        return None, (str(exc),)


def _priority(tokens: Tokens, left: str, skip: frozenset[str]) -> tuple[Priority | None, str | None, str]:
    """The shorthand's level, else an urgent / baja word left at the edge once the date is gone. Also the
    words it came from."""
    if tokens.priority is not None or "priority" in skip:
        return tokens.priority, tokens.priority_words, left
    level, typed, rest = edge_priority(left)
    return level, typed, rest


LITERAL_QUOTES = (("'", None), ('"', '"'), ("\u201c", "\u201d"))       # a leading ' or a line in full quotes


def literal_title(text: str) -> str | None:
    """The title a literal line names (nothing is parsed), or ``None`` when the line is not literal:
    a leading ``'``, or the whole line between double quotes."""
    body = text.strip()
    for opening, closing in LITERAL_QUOTES:
        if not body.startswith(opening):
            continue
        if closing is None:
            return body[1:].strip()
        if len(body) >= 2 and body.endswith(closing):
            return body[1:-1].strip()
    return None


async def _literal_line(projects: ProjectService, user_id: str, title: str, project_id: str | None) -> QuickLine:
    project, question = await _project(projects, user_id, None, project_id)
    return QuickLine(title=" ".join(title.split()), due=_NO_DUE, priority=None, project=project, project_words=None,
                     project_question=question, budget=None, budget_words=None, budget_problem=None)


KEEP_MAX_WORDS = 16
KEEP_MAX_LENGTH = 80
_KEEP_MASK_BASE = 0xE100          # private-use characters stand in for kept words while the line is read
_KEEP_MASK_LAST = 0xF8FF


def _mask_kept(text: str, keep: Sequence[str]) -> tuple[str, dict[str, str]]:
    """Kept words (a cancelled chip's) become single private-use characters, so no reader sees them; the
    returned map puts them back, as typed, into the title. Whole words, any case; a word that is not in the
    text is ignored."""
    restore: dict[str, str] = {}
    phrases = sorted({" ".join(word.split()) for word in keep if word.strip()}, key=len, reverse=True)
    for phrase in phrases:
        if len(phrase) > KEEP_MAX_LENGTH or any(_KEEP_MASK_BASE <= ord(char) <= _KEEP_MASK_LAST for char in phrase):
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", re.IGNORECASE)

        def hide(found: re.Match[str]) -> str:
            mask = chr(_KEEP_MASK_BASE + len(restore))
            restore[mask] = found.group(0)
            return mask
        if _KEEP_MASK_BASE + len(restore) + len(pattern.findall(text)) <= _KEEP_MASK_LAST:
            text = pattern.sub(hide, text)
    return text, restore


def _restored(text: str, restore: Mapping[str, str]) -> str:
    for mask, words in restore.items():
        text = text.replace(mask, words)
    return text


def _matches(line: QuickLine, date_words: tuple[str, ...], priority_words: str | None, star_words: str | None,
             estimate_words: str | None, repeat_extra: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    """Which words each chip came from, so the web can put them back (as kept words) when it is removed."""
    found = {
        "date": date_words, "priority": (priority_words,) if line.priority and priority_words else (),
        "star": (star_words,) if line.starred and star_words else (),
        "estimate": (estimate_words,) if line.estimate_minutes and estimate_words else (),
        "reminder": (line.reminder_words,) if line.reminder_words else (),
        "repeat": (*((line.repeat_words,) if line.repeat_words else ()), *repeat_extra),
        "project": (line.project_words,) if line.project_words else (),
        "budget": (line.budget_words,) if line.budget_words else (),
        "assignee": (line.assignee_words,) if line.assignee_words else (),
        "tag": tuple(f"#{tag}" for tag in line.tags),
    }
    return {kind: words for kind, words in found.items() if words}


async def read_quick_line(projects: ProjectService, user_id: str, text: str, *, project_id: str | None = None,
                          skip: frozenset[str] = frozenset(), bots: Sequence[Bot] = (),
                          now: datetime | None = None, keep: Sequence[str] = (),
                          default_due: str | None = None) -> QuickLine:
    """``default_due`` is a day used only when the line names none (a Kanban column's day).
    ``keep`` are words the user cancelled the chips of: they stay in the title as plain text."""
    if now is None:
        return await _read_quick_line(projects, user_id, text, project_id=project_id, skip=skip, bots=bots,
                                      now=datetime.now(local_tz()), keep=keep, default_due=default_due)
    with nl_time.as_of(now):                # every day rule reads as of ``now`` (a line typed offline)
        return await _read_quick_line(projects, user_id, text, project_id=project_id, skip=skip, bots=bots,
                                      now=now, keep=keep, default_due=default_due)


async def _read_quick_line(projects: ProjectService, user_id: str, text: str, *, project_id: str | None,
                           skip: frozenset[str], bots: Sequence[Bot], now: datetime, keep: Sequence[str],
                           default_due: str | None) -> QuickLine:
    moment = now
    if (literal := literal_title(text)) is not None:
        return await _literal_line(projects, user_id, literal, project_id)
    masked, restore = _mask_kept(text, keep)
    tokens = read_tokens(masked, frozenset({_TOKEN_KIND.get(kind, kind) for kind in skip} | {"vendor"}))
    tag_rest, tags, tag_warnings = _read_tags(tokens.rest, skip)
    assigned = _read_assignee(tag_rest, bots, skip)
    words, project_warnings = _read_projects(assigned.rest, skip, await projects.names(user_id))
    read = _read_repeat(words.rest, skip, moment)
    repeat, due = read.reading, read.due
    if due.due_date is None and default_due:
        due = Due(default_due, None)
    priority, priority_words, left = _priority(tokens, read.left, skip)
    project, question = await _project(projects, user_id, words.project_ref, project_id)
    home = None if question is not None else await _home(projects, user_id, tokens, project)
    budget, problem = (None, None) if question is not None else _budget(tokens, home)
    reminder_at, reminder_warnings = _reminder(tokens, due, moment)
    line = QuickLine(
        title=" ".join(_restored(left, restore).split()), due=due, priority=priority, project=project,
        project_words=words.project_words, project_question=question, budget=budget,
        budget_words=tokens.amount_words, budget_problem=problem, budget_math=tokens.amount_math,
        budget_currency=None if budget is None or home is None else home[1], starred=tokens.star,
        estimate_minutes=tokens.estimate_minutes, reminder_at=reminder_at, reminder_words=tokens.reminder_words,
        recurring=None if repeat is None else repeat.value, recur_until=read.until,
        repeat_words=None if repeat is None else repeat.words,
        repeat_problem=None if repeat is None else repeat.problem, assignee=assigned.bot,
        assignee_words=assigned.words, assignee_question=assigned.question, tags=tags,
        warnings=(*tokens.warnings, *tag_warnings, *assigned.warnings, *project_warnings, *reminder_warnings),
    )
    seen = _matches(line, read.date_words, priority_words, tokens.star_words, tokens.estimate_words,
                    read.extra_words if repeat is not None else ())
    return replace(line, matches=seen)


def quick_line_out(line: QuickLine, *, now: datetime | None = None) -> dict[str, Any]:
    """``QuickLineOut``: what the web shows as chips, and what it sends to add the task. ``due_text`` and
    ``reminder_text`` are the resolved dates in words, on local time ("Wed 21 Oct 09:00")."""
    moment = now or datetime.now(local_tz())
    project = None if line.project is None else {
        "id": line.project.id, "name": line.project.name, "currency": line.project.currency,
        "color": line.project.color,
    }
    assignee = None if line.assignee is None else {"id": line.assignee.id, "name": line.assignee.name}
    return {
        "title": line.title, "due_date": line.due.due_date, "due_text": preview(line.due.due_date, now=moment),
        "reminder_text": preview(line.reminder_at, now=moment), "priority": line.priority, "project": project,
        "project_words": line.project_words, "project_question": line.project_question,
        "budget": None if line.budget is None else amount_text(line.budget), "budget_words": line.budget_words,
        "budget_problem": line.budget_problem, "budget_math": line.budget_math,
        "budget_currency": line.budget_currency, "ready": line.ready, "starred": line.starred,
        "estimate_minutes": line.estimate_minutes, "reminder_at": line.reminder_at,
        "reminder_words": line.reminder_words, "recurring": line.recurring, "recur_until": line.recur_until, "repeat_text": line.repeat_text,
        "repeat_words": line.repeat_words, "repeat_problem": line.repeat_problem, "assignee": assignee,
        "assignee_words": line.assignee_words, "assignee_question": line.assignee_question,
        "tags": list(line.tags), "matches": {kind: list(words) for kind, words in line.matches.items()},
        "warnings": list(line.warnings),
    }
