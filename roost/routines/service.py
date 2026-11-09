"""``RoutineService``: the one door for the routine routes (and, later, the bot's routine tools).

Every method takes ``user_id`` first, and another user's bot or routine reads as "no such" (the routes turn that into
404). A refusal is ``Refused`` with a plain sentence (422); a lost race or a busy routine is ``Conflict`` (409).
Every write publishes ``routines_changed`` and leaves a quiet ``routine_note`` line in the bot's main chat
("Deleted routine · Morning news")."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from roost.bots.store import BotStore
from roost.constants import (
    REPORT_LOOKUP_MESSAGES,
    ROUTINE_INSTRUCTIONS_MAX,
    ROUTINE_NAME_MAX,
    ROUTINE_PREVIEW_COUNT,
    ROUTINE_RUNS_PAGE,
    ROUTINES_PER_BOT_MAX,
    ROUTINES_PER_USER_MAX,
)
from roost.events.hub import EventHub
from roost.routines.launcher import RoutineLauncher
from roost.routines.models import Clock, Routine, RoutineDraft, RoutinePatch, RoutineRun
from roost.routines.reports import post_routine_note
from roost.routines.runs import RoutineRunStore, SlotAlreadyRecorded, utc_now
from roost.routines.schedule import (
    ScheduleRefused, parse_schedule, readable, slot_for, upcoming,
)
from roost.routines.store import RoutineStore
from roost.routines.watch_models import WatchIn, WatchRefused, parse_watch, watch_words
from roost.routines.watch_store import WatchStore
from roost.talk.limits import LimitState
from roost.talk.store import TalkStore
from roost.timezones import local_tz

_TEXT_NAME = "A routine needs a name."
_TEXT_INSTRUCTIONS = "A routine needs instructions."
_TEXT_NOTHING = "Nothing to change."
_TEXT_BUILTIN_EDIT = "The end-of-day summary can only be switched on or off and given a new time."
_TEXT_BUILTIN_RUN = "The end-of-day summary can't be run by hand."
_TEXT_RUNNING = "It's still running."
_TEXT_CAP = "Daily limit reached."
_TEXT_OFF_DUTY = "This bot is off duty."
_TEXT_BUILTIN_WATCH = "The end-of-day summary can't watch a page."
_FIELDS = frozenset({"name", "instructions", "schedule", "enabled", "watch"})
_BUILTIN_FIELDS = frozenset({"schedule", "enabled"})


class NoSuchBot(LookupError):
    """The bot is not there, or not the user's."""


class NoSuchRoutine(LookupError):
    """The routine is not there, or not the user's."""


class Refused(ValueError):
    """A change the user can't make. ``text`` is the plain sentence to show."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


class Conflict(RuntimeError):
    """The routine is busy or a limit is reached. ``text`` is the plain sentence to show."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


@dataclass(frozen=True)
class RoutineView:
    routine: Routine
    words: str
    slot: datetime | None       # the user's next minute, without the jitter (a watching routine: its next check)
    last_state: str | None
    checked_at: datetime | None = None      # a watching routine: when Roost last read the page
    changed_at: datetime | None = None      # and when the watched part last changed


@dataclass(frozen=True)
class Preview:
    words: str
    next: tuple[str, ...]       # local ISO times


class RoutineService:
    def __init__(
        self, routines: RoutineStore, runs: RoutineRunStore, bots: BotStore, talk: TalkStore, events: EventHub,
        launcher: RoutineLauncher, turns, *, clock: Clock = utc_now, watches: WatchStore | None = None,
    ) -> None:
        self._watches = watches     # None: a new address or part keeps the old snapshot, and no check times show
        self._routines = routines
        self._runs = runs
        self._bots = bots
        self._talk = talk
        self._events = events
        self._launcher = launcher
        self._turns = turns
        self._clock = clock
        self._run_lock = asyncio.Lock()     # two Run now presses never both pass the "still running" check

    # --- reads -----------------------------------------------------------------------------------------------

    async def list(self, user_id: str, bot_id: str) -> tuple[RoutineView, ...]:
        await self._bot(user_id, bot_id)
        return tuple([await self._view(user_id, r) for r in await self._routines.list_for_bot(user_id, bot_id)])

    async def view(self, user_id: str, routine: Routine) -> RoutineView:
        return await self._view(user_id, routine)

    async def runs(self, user_id: str, routine_id: str, before_id: str | None = None) -> tuple[RoutineRun, ...]:
        await self._routine(user_id, routine_id)
        return await self._runs.list_for_routine(user_id, routine_id, ROUTINE_RUNS_PAGE, before_id=before_id)

    async def report_ids(self, user_id: str, routine_id: str) -> Mapping[str, str]:
        """Run id -> the message id of that run's Report, found among the bot's latest messages in its main chat."""
        routine = await self._routine(user_id, routine_id)
        thread = await self._talk.main_thread(user_id, routine.bot_id)
        if thread is None:
            return {}
        found: dict[str, str] = {}
        for message in await self._talk.list_latest_messages(user_id, thread.id, REPORT_LOOKUP_MESSAGES):
            run_id = _report_run_id(message.body) if message.kind == "report" else None
            if run_id is not None:
                found[run_id] = message.id
        return found

    def preview(self, schedule: Mapping) -> Preview:
        parsed = self._schedule(schedule)
        now = self._clock()
        fires = upcoming(parsed, now, ROUTINE_PREVIEW_COUNT)
        return Preview(words=readable(parsed, now=now),
                       next=tuple(f.astimezone(local_tz()).isoformat(timespec="minutes") for f in fires))

    # --- writes ----------------------------------------------------------------------------------------------

    async def create(
        self, user_id: str, bot_id: str, name: str, instructions: str, schedule: Mapping, enabled: bool = True,
        *, created_by: str = "user", tainted: bool = False, watch: Mapping | WatchIn | None = None,
    ) -> Routine:
        await self._bot(user_id, bot_id)
        clean_name, clean_text = _name(name), _instructions(instructions)
        parsed, watching = self._schedule(schedule), _watch(watch)
        if await self._routines.count_for_bot(user_id, bot_id) >= ROUTINES_PER_BOT_MAX:
            raise Refused(f"This bot already has {ROUTINES_PER_BOT_MAX} routines.")
        if await self._routines.count_for_user(user_id) >= ROUTINES_PER_USER_MAX:
            raise Refused(f"You already have {ROUTINES_PER_USER_MAX} routines.")
        routine = await self._routines.create(user_id, RoutineDraft(
            bot_id=bot_id, name=clean_name, instructions=clean_text, schedule=parsed, created_by=created_by,  # type: ignore[arg-type]
            tainted=tainted, enabled=enabled, watch=watching))
        await self._changed(user_id, routine, "created")
        return routine

    async def update(
        self, user_id: str, routine_id: str, changes: Mapping, *, tainted: bool | None = None,
    ) -> Routine:
        current = await self._routine(user_id, routine_id)
        if not changes or not set(changes) <= _FIELDS:
            raise Refused(_TEXT_NOTHING)
        if current.builtin is not None and not set(changes) <= _BUILTIN_FIELDS:
            raise Refused(_TEXT_BUILTIN_WATCH if "watch" in changes else _TEXT_BUILTIN_EDIT)
        fields = self._clean(changes)
        updated = current
        if set(fields) - {"enabled"}:
            patch = {k: v for k, v in fields.items() if k != "enabled"}
            if tainted:
                patch["tainted"] = True       # a change made in a tainted run keeps the routine tainted
            updated = await self._routines.update(user_id, routine_id, RoutinePatch(patch)) or current
            await self._new_baseline(user_id, current, updated)
        if "enabled" in fields and fields["enabled"] != updated.enabled:
            updated = await self._routines.set_enabled(user_id, routine_id, fields["enabled"]) or updated
        await self._changed(user_id, updated, _verb(fields))
        return updated

    async def delete(self, user_id: str, routine_id: str) -> None:
        routine = await self._routine(user_id, routine_id)
        await self._routines.delete(user_id, routine_id)
        await self._events.publish(user_id, {"type": "routines_changed", "bot_id": routine.bot_id})
        thread, _created = await self._talk.ensure_main_thread(user_id, routine.bot_id)
        await post_routine_note(self._talk, self._events, user_id, thread.id, routine.bot_id, "deleted", routine.name)

    async def run_now(self, user_id: str, routine_id: str) -> RoutineRun:
        """Start a run at once. It counts against the daily cap like any run, and never overlaps an open one."""
        routine = await self._routine(user_id, routine_id)
        if routine.builtin is not None:
            raise Refused(_TEXT_BUILTIN_RUN)
        async with self._run_lock:
            bot = await self._bot(user_id, routine.bot_id)
            if bot.off_duty:
                raise Conflict(_TEXT_OFF_DUTY)
            if await self._runs.open_for_routine(user_id, routine_id):
                raise Conflict(_TEXT_RUNNING)
            now = self._clock().replace(microsecond=0)
            limit: LimitState = await self._turns.limit_state(user_id, bot)
            if limit.at_cap:
                await self._runs.record(user_id, routine, now, "held")
                raise Conflict(_TEXT_CAP)
            try:
                return await self._launcher.launch(user_id, routine, now, late=False, now=now)
            except SlotAlreadyRecorded:
                raise Conflict(_TEXT_RUNNING) from None

    # --- pieces ----------------------------------------------------------------------------------------------

    async def _bot(self, user_id: str, bot_id: str):
        bot = await self._bots.get(user_id, bot_id)
        if bot is None:
            raise NoSuchBot(bot_id)
        return bot

    async def _routine(self, user_id: str, routine_id: str) -> Routine:
        routine = await self._routines.get(user_id, routine_id)
        if routine is None:
            raise NoSuchRoutine(routine_id)
        return routine

    def _schedule(self, raw: Mapping):
        try:
            return parse_schedule(raw, after_utc=self._clock())
        except ScheduleRefused as exc:
            raise Refused(exc.text) from None

    def _clean(self, changes: Mapping) -> dict:
        fields = dict(changes)
        if "name" in fields:
            fields["name"] = _name(fields["name"])
        if "instructions" in fields:
            fields["instructions"] = _instructions(fields["instructions"])
        if "schedule" in fields:
            fields["schedule"] = self._schedule(fields["schedule"])
        if "watch" in fields:
            fields["watch"] = _watch(fields["watch"])
        return fields

    async def _new_baseline(self, user_id: str, before: Routine, after: Routine) -> None:
        """A watch on a new address or part compares from a new first look, never with the old page."""
        old, new = before.watch, after.watch
        if self._watches is None or old is None:
            return
        if new is None or (old.url, old.part) != (new.url, new.part):
            await self._watches.reset(user_id, before.id)

    async def _view(self, user_id: str, routine: Routine) -> RoutineView:
        latest = await self._runs.list_for_routine(user_id, routine.id, 1)
        slot = routine.next_run_at if routine.watch is not None else (
            slot_for(routine.next_run_at, routine.schedule) if routine.next_run_at is not None else None)
        snap = await self._watches.get(user_id, routine.id) if self._watches and routine.watch else None
        return RoutineView(routine=routine, words=_words(routine, self._clock()), slot=slot,
                           last_state=latest[0].state if latest else None,
                           checked_at=snap.checked_at if snap else None, changed_at=snap.changed_at if snap else None)

    async def _changed(self, user_id: str, routine: Routine, verb: str) -> None:
        await self._events.publish(user_id, {"type": "routines_changed", "bot_id": routine.bot_id})
        thread, _created = await self._talk.ensure_main_thread(user_id, routine.bot_id)
        await post_routine_note(self._talk, self._events, user_id, thread.id, routine.bot_id, verb, routine.name,
                                routine_id=routine.id)


def _watch(raw: Mapping | WatchIn | None):
    try:
        return parse_watch(raw)
    except WatchRefused as refused:
        raise Refused(refused.text) from None


def _words(routine: Routine, now: datetime) -> str:
    """The schedule in words; a watching routine says how it runs instead."""
    return watch_words(routine.watch) if routine.watch is not None else readable(routine.schedule, now=now)


def _verb(fields: Mapping) -> str:
    """The activity line's verb: a lone switch is paused or resumed, anything else is updated."""
    if set(fields) != {"enabled"}:
        return "updated"
    return "resumed" if fields["enabled"] else "paused"


def _name(raw: str) -> str:
    text = raw.strip()
    if not text:
        raise Refused(_TEXT_NAME)
    if len(text) > ROUTINE_NAME_MAX:
        raise Refused(f"A routine's name can be up to {ROUTINE_NAME_MAX} characters.")
    return text


def _instructions(raw: str) -> str:
    text = raw.strip()
    if not text:
        raise Refused(_TEXT_INSTRUCTIONS)
    if len(text) > ROUTINE_INSTRUCTIONS_MAX:
        raise Refused(f"A routine's instructions can be up to {ROUTINE_INSTRUCTIONS_MAX} characters.")
    return text


def _report_run_id(body: str) -> str | None:
    try:
        run_id = json.loads(body).get("run_id")
    except (ValueError, AttributeError):
        return None
    return run_id if isinstance(run_id, str) else None
