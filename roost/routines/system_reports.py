"""Reports with no model run: reminders and the end-of-day summary.

The scheduler calls every job's ``run(user_id, now)`` on each tick and the day summary's ``fire`` when an existing
built-in routine is due. Nothing here starts on its own any more (the owner, 2026-10-21: "If I ask, I ask"): no
day summary is seeded and there is no budget alert job; a user who wants either asks a bot for an ordinary routine.
Limits that keep it cheap and safe:

- a reminder is sent at most once per fire time (the ``reminder_sends`` ledger is unique on user, task and
  fire time, so a repeat never posts and a changed ``reminder_at`` fires again);
- a tick sends at most ``REMINDERS_PER_TICK_MAX`` reminders; the rest wait for the next tick;
- a reminder passed by more than ``REMINDER_LATE_GRACE_SECONDS`` is not replayed one by one: it becomes one
  "While Roost was off" Report per bot;
- every query names ``user_id`` and every failure is logged by ids and the exception's type name only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from roost.bots.models import Bot
from roost.bots.store import BotStore
from roost.constants import (
    MAX_TASK_TITLE_LENGTH,
    REMINDER_LATE_GRACE_SECONDS,
    REMINDER_LOOKAHEAD_DAYS,
    REMINDER_LOOKBACK_HOURS,
    REMINDERS_PER_TICK_MAX,
    REPORT_HEADLINE_MAX,
    REPORT_TEXT_MAX_CHARS,
)
from roost.config import RoostConfig
from roost.db.connection import db_session
from roost.events.hub import EventHub
from roost.money.expense_store import ExpenseStore
from roost.routines.models import Job, ReportBody, Routine
from roost.routines.reminder_words import day_words, reminder_text
from roost.routines.reports import post_report, with_headline
from roost.routines.runs import RoutineRunStore, SlotAlreadyRecorded, iso
from roost.routines.store import DAY_SUMMARY_BUILTIN, RoutineStore
from roost.routines.texts import clip
from roost.timezones import local_tz
from roost.tasks.day_summary import build_day_summary, day_summary_text
from roost.tasks.models import Task
from roost.tasks.reminders import parse_iso_datetime, parse_offset_against
from roost.tasks.store import TaskStore
from roost.work.runs import madrid_today

logger = logging.getLogger(__name__)

MISSED_HEADLINE = "While Roost was off, reminders passed"
MISSED_LEAD = "While Roost was off, these reminders passed:"


@dataclass(frozen=True)
class JobDeps:
    """What every job needs to post a Report."""

    config: RoostConfig
    bots: BotStore
    talk: object
    events: EventHub
    runs: RoutineRunStore


async def _post(deps: JobDeps, user_id: str, bot_id: str, body: ReportBody, now: datetime) -> None:
    """System Reports are always posted (the hourly cap folds model Reports only); each is bounded by its job."""
    await post_report(deps.talk, deps.events, user_id, bot_id, body, runs=deps.runs, now=now, always=True)


async def _main_bot(deps: JobDeps, user_id: str) -> Bot | None:
    return await deps.bots.get_primary(user_id)


def madrid_words(value: str | datetime) -> str:
    """"Wednesday 21 October, 10:00" for a moment, "Wednesday 21 October" for a day-only text. A text with no
    offset is read as local time (the install's zone)."""
    if isinstance(value, str) and len(value) == len("YYYY-MM-DD"):
        day, clock = date.fromisoformat(value), None
    else:
        moment = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        local = (moment if moment.tzinfo else moment.replace(tzinfo=local_tz())).astimezone(local_tz())
        day, clock = local.date(), local.time()
    text = day_words(day)
    return text if clock is None else f"{text}, {clock:%H:%M}"


# --- reminders -------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Fire:
    at: datetime
    task: Task
    recipient: str


class ReminderJob:
    name = "reminders"
    builtin = None

    def __init__(self, deps: JobDeps, tasks: TaskStore) -> None:
        self._deps = deps
        self._tasks = tasks

    async def fire(self, user_id: str, routine: Routine, slot: datetime) -> None:   # pragma: no cover - not a built-in
        return None

    async def run(self, user_id: str, now: datetime) -> None:
        window = await self._tasks.reminders_between(
            user_id, now - timedelta(hours=REMINDER_LOOKBACK_HOURS), now + timedelta(days=REMINDER_LOOKAHEAD_DAYS))
        main = await _main_bot(self._deps, user_id)
        sent = await self._sent(user_id, now - timedelta(hours=REMINDER_LOOKBACK_HOURS))
        fires = tuple(f for f in await self._due_fires(user_id, window, now, main)
                      if (f.task.id, iso(f.at)) not in sent)
        fresh: list[_Fire] = []
        late: list[_Fire] = []
        for fire in fires[:REMINDERS_PER_TICK_MAX]:
            is_late = now - fire.at > timedelta(seconds=REMINDER_LATE_GRACE_SECONDS)
            if await self._claim(user_id, fire, is_late, now):
                (late if is_late else fresh).append(fire)
        for fire in fresh:
            await self._send(user_id, fire.recipient, _reminder(fire), now, fire)
        for recipient, group in _by_recipient(late):
            await self._send(user_id, recipient, _missed(group), now, *group)

    async def _due_fires(self, user_id: str, tasks, now: datetime, main: Bot | None) -> tuple[_Fire, ...]:
        floor = now - timedelta(hours=REMINDER_LOOKBACK_HOURS)
        found: list[_Fire] = []
        for task in tasks:
            recipient = await self._recipient(user_id, task, main)
            if recipient is None:
                continue
            found.extend(_Fire(at, task, recipient) for at in _fire_times(task) if floor <= at <= now)
        return tuple(sorted(found, key=lambda f: (f.at, f.task.id)))

    async def _recipient(self, user_id: str, task: Task, main: Bot | None) -> str | None:
        """The assigned bot, else the bot that made the task, while it still exists; else the main bot."""
        for bot_id in (task.owner if task.owner != "user" else None, task.created_by_bot):
            if bot_id and await self._deps.bots.get(user_id, bot_id) is not None:
                return bot_id
        return main.id if main is not None else None

    async def _sent(self, user_id: str, since: datetime) -> frozenset[tuple[str, str]]:
        """The (task, fire time) pairs already in the ledger, so a backlog past the tick cap is not starved by
        the ones already sent."""
        async with db_session(self._deps.config) as db:
            rows = await (await db.execute(
                "SELECT task_id, fire_at FROM reminder_sends WHERE user_id = ? AND fire_at >= ?",
                (user_id, iso(since)))).fetchall()
        return frozenset((row["task_id"], row["fire_at"]) for row in rows)

    async def _claim(self, user_id: str, fire: _Fire, missed: bool, now: datetime) -> bool:
        """True for exactly one caller per (task, fire time): a new ledger row."""
        async with db_session(self._deps.config) as db:
            cursor = await db.execute(
                "INSERT OR IGNORE INTO reminder_sends (id, user_id, task_id, fire_at, missed, sent_at) "
                "VALUES (?,?,?,?,?,?)",
                (str(uuid4()), user_id, fire.task.id, iso(fire.at), int(missed), iso(now)))
            await db.commit()
            return cursor.rowcount == 1

    async def _release(self, user_id: str, fires: tuple[_Fire, ...]) -> None:
        """A Report that could not be posted gives its ledger rows back, so the next tick tries again."""
        async with db_session(self._deps.config) as db:
            for fire in fires:
                await db.execute("DELETE FROM reminder_sends WHERE user_id = ? AND task_id = ? AND fire_at = ?",
                                 (user_id, fire.task.id, iso(fire.at)))
            await db.commit()

    async def _send(self, user_id: str, bot_id: str, body: ReportBody, now: datetime, *fires: _Fire) -> None:
        try:
            await _post(self._deps, user_id, bot_id, body, now)
        except Exception as exc:
            logger.warning("Posting a reminder Report failed for bot %s user %s: %s", bot_id, user_id,
                           type(exc).__name__)
            await self._release(user_id, fires)


def _fire_times(task: Task) -> tuple[datetime, ...]:
    """The reminder and every advance reminder (an offset like -30m, or a stored UTC instant), as UTC moments."""
    base = parse_iso_datetime(task.reminder_at or "")
    if base is None:
        return ()
    times = {base}
    for entry in task.pre_reminders:
        try:
            at = parse_offset_against(entry, base) or parse_iso_datetime(entry)
        except OverflowError:
            at = None
        if at is not None:
            times.add(at.astimezone(timezone.utc))
    return tuple(sorted(times))


def _by_recipient(fires: list[_Fire]) -> tuple[tuple[str, tuple[_Fire, ...]], ...]:
    groups: dict[str, tuple[_Fire, ...]] = {}
    for fire in fires:
        groups = {**groups, fire.recipient: (*groups.get(fire.recipient, ()), fire)}
    return tuple(groups.items())


def _reminder(fire: _Fire) -> ReportBody:
    """One task's reminder as a friendly chat line, worded by which reminder it is (``reminder_words``)."""
    task = fire.task
    base = parse_iso_datetime(task.reminder_at or "") or fire.at
    text = reminder_text(task.title, fire_at=fire.at, base_at=base, due_date=task.due_date)
    return ReportBody(
        source="reminder", headline=clip(f"Reminder: {task.title}", REPORT_HEADLINE_MAX),
        text=clip(text, REPORT_TEXT_MAX_CHARS), tainted=task.tainted, task_id=task.id,
        task_title=clip(task.title, MAX_TASK_TITLE_LENGTH))


def _missed(fires: tuple[_Fire, ...]) -> ReportBody:
    lines = [MISSED_LEAD, *(f"- {f.task.title} (was {madrid_words(f.at)})" for f in fires)]
    return ReportBody(
        source="reminder", headline=MISSED_HEADLINE, text=clip("\n".join(lines), REPORT_TEXT_MAX_CHARS),
        tainted=any(f.task.tainted for f in fires))


# --- the end-of-day summary --------------------------------------------------------------------------------------


class DaySummaryJob:
    """Posts an existing day summary routine when the scheduler fires it. It seeds nothing: no user or bot gets
    one on its own."""

    name = "day_summary"
    builtin = DAY_SUMMARY_BUILTIN

    def __init__(self, deps: JobDeps, routines: RoutineStore, tasks: TaskStore, expenses: ExpenseStore) -> None:
        self._deps = deps
        self._routines = routines
        self._tasks = tasks
        self._expenses = expenses

    async def run(self, user_id: str, now: datetime) -> None:
        return None

    async def fire(self, user_id: str, routine: Routine, slot: datetime) -> None:
        """Post the local day of ``slot`` as a Report and record the slot ``done``. Overdue is judged at the slot."""
        try:
            await self._deps.runs.record(user_id, routine, slot, "done")
        except SlotAlreadyRecorded:
            return
        day = madrid_today(slot)
        summary = await build_day_summary(user_id, day, tasks=self._tasks, expenses=self._expenses, now=slot)
        title = f"Your day, {day}"
        text = "".join(day_summary_text(summary).split("\n", 1)[1:])      # the title replaces the heading line
        body = ReportBody(
            source="day_summary", headline=title, text=with_headline(title, text), routine_name=routine.name,
            routine_id=routine.id, log_thread_id=routine.thread_id,
            tainted=any(t.tainted for t in (*summary.done, *summary.failed, *summary.overdue)))
        await _post(self._deps, user_id, routine.bot_id, body, slot)


# --- the registry ----------------------------------------------------------------------------------------------


def jobs_for_parts(
    deps: JobDeps, routines: RoutineStore, tasks: TaskStore, expenses: ExpenseStore,
) -> tuple[Job, ...]:
    return (DaySummaryJob(deps, routines, tasks, expenses), ReminderJob(deps, tasks))


def jobs_for(state) -> tuple[Job, ...]:
    """The jobs over ``app.state``'s stores. One set per gateway."""
    deps = JobDeps(state.config, state.bots, state.talk, state.events, state.routine_runs)
    return jobs_for_parts(deps, state.routine_store, TaskStore(state.config), ExpenseStore(state.config))
