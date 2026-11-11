"""``RoutineWrites``: the bot creates, changes, pauses, resumes and deletes its own routines directly.

The owner (2026-10-21): "If I ask, I ask. If I don't, I don't." When the user asks a bot in their own chat to set
up, change, stop or delete a routine, the bot just does it. These tools carry the normal gate kinds, so the bot's
approval mode still decides: Ask every time parks the call on an Ask card (``prepare``), Auto-edit runs it
(``run``), Review first makes it a step of a Proposal; Yes or Accept runs the stored call (``execute``).

Only a run the user's own message started in a 1:1 chat may use them. A run that read web content is refused by the
gate outside your own chat (``refused_when_tainted``) and again here; in your own chat the runner hands these a clean
context (``roost/talk/owner_chat.py``). A routine's own run, a handoff or a room gets ``NOT_HERE_TEXT`` and the
bot uses the ``propose_*`` tools, so the user's Approve on the card writes it there. Validation is the proposal
path's: ``parse_schedule`` (local times, cron no more often than every 15 minutes), then ``RoutineService`` with
its caps. Every lookup names ``user_id``, and another bot's or user's routine is "not one of your routines"."""

from __future__ import annotations

import html
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.approvals.models import PendingCall
from roost.constants import ROUTINE_INSTRUCTIONS_MAX, ROUTINE_NAME_MAX
from roost.llm.registry import model_label
from roost.records.tool_text import ToolText
from roost.routines.direct_texts import (
    ACTIVITY, BAD_ARGS_TEXT, CARD_VERBS, CHANGED_TEXT, CREATED_TEXT, DELETED_TEXT, NOT_HERE_TEXT, NOT_YOURS_TEXT,
    NOTHING_TEXT, PAUSED_TEXT, RESUMED_TEXT, TAINTED_TEXT, WATCH_NOT_NAMED_TEXT,
)
from roost.routines.models import Routine
from roost.routines.schedule import ScheduleRefused, parse_schedule, readable, slot_for
from roost.routines.service import NoSuchBot, NoSuchRoutine, Refused, RoutineService, routine_model
from roost.routines.store import RoutineStore
from roost.routines.runs import utc_now
from roost.routines.watch_models import WatchRefused, parse_watch, watch_words
from roost.talk.link_scope import LinkScope
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome
from roost.timezones import local_tz, zone_city

__all__ = ["NOT_HERE_TEXT", "TAINTED_TEXT", "RoutineWrites"]

_TOPIC = "routines"
OwnerTexts = Callable[[str, str], Awaitable[tuple[str, ...]]]   # (user_id, thread_id) -> your own messages there


MODEL_ARG_MAX = 64


class CreateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: ToolText = Field(min_length=1, max_length=ROUTINE_NAME_MAX)
    instructions: ToolText = Field(min_length=1, max_length=ROUTINE_INSTRUCTIONS_MAX)
    schedule: dict[str, Any]
    watch: dict[str, Any] | None = None
    model: str | None = Field(default=None, max_length=MODEL_ARG_MAX)


class UpdateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    routine_id: str = Field(min_length=1, max_length=64)
    name: ToolText | None = Field(default=None, min_length=1, max_length=ROUTINE_NAME_MAX)
    instructions: ToolText | None = Field(default=None, min_length=1, max_length=ROUTINE_INSTRUCTIONS_MAX)
    schedule: dict[str, Any] | None = None
    watch: dict[str, Any] | None = None
    model: str | None = Field(default=None, max_length=MODEL_ARG_MAX)


class IdArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    routine_id: str = Field(min_length=1, max_length=64)


_ARGS: dict[str, type[BaseModel]] = {
    "create_routine": CreateArgs, "update_routine": UpdateArgs, "pause_routine": IdArgs,
    "resume_routine": IdArgs, "delete_routine": IdArgs,
}


class _Refusal(Exception):
    """A plain sentence the bot gets back instead of a change."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _where_refusal(ctx: RecordContext) -> str | None:
    """Only a clean run the user's own message started, in a chat, may write a routine directly."""
    if ctx.tainted:
        return TAINTED_TEXT
    if ctx.from_routine or not ctx.user_started or ctx.thread_id is None:
        return NOT_HERE_TEXT
    return None


def _failed(text: str) -> ToolOutcome:
    return ToolOutcome(text, failed=True)


class RoutineWrites:
    names: frozenset[str] = frozenset(_ARGS)

    def __init__(self, routines: RoutineStore, service: RoutineService, *,
                 owner_texts: OwnerTexts | None = None) -> None:
        self._routines = routines
        self._service = service
        self._owner_texts = owner_texts     # your own messages in a chat; None: no page may be watched

    def activity(self, name: str) -> str:
        return ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        pending = await self.prepare(name, arguments, ctx)
        if isinstance(pending, str):
            return _failed(pending)
        return await self.execute(name, dict(pending.arguments), ctx)

    async def prepare(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> PendingCall | str:
        """The card step for this call, or a plain refusal (no card) when this run may not write routines."""
        refusal = _where_refusal(ctx)
        if refusal is not None:
            return refusal
        try:
            args = self._parse(name, arguments)
            subject = await self._subject(name, args, ctx)
            await self._owner_named(args, ctx)
        except _Refusal as refused:
            return refused.text
        stored = args.model_dump(mode="json", exclude_none=True)
        title = f"{CARD_VERBS[name]} “{_esc(subject)}”"
        return PendingCall(tool=name, arguments=stored, topic=_TOPIC, title=title, detail=_detail(stored))

    async def execute(self, name: str, resolved: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        """Run a call: from ``run`` in a run allowed to, or a card's stored call after the user's Yes."""
        if ctx.tainted:
            return _failed(TAINTED_TEXT)
        try:
            args = self._parse(name, resolved)
            await self._owner_named(args, ctx)
            if isinstance(args, CreateArgs):
                return await self._create(args, ctx)
            routine = await self._own(ctx, args.routine_id)
            return await self._change(name, args, routine, ctx)
        except _Refusal as refused:
            return _failed(refused.text)
        except (Refused, ScheduleRefused, WatchRefused) as refused:
            return _failed(f"Refused: {_esc(refused.text)}")
        except (NoSuchRoutine, NoSuchBot):
            return _failed(NOT_YOURS_TEXT)

    # --- pieces ------------------------------------------------------------------------------------------------

    def _parse(self, name: str, arguments: dict[str, Any]) -> BaseModel:
        try:
            args = _ARGS[name].model_validate(arguments)
        except ValidationError:
            raise _Refusal(BAD_ARGS_TEXT.format(name=name)) from None
        try:
            if isinstance(args, CreateArgs):
                parse_schedule(args.schedule, name=args.name)
            elif isinstance(args, UpdateArgs) and args.schedule is not None:
                parse_schedule(args.schedule)
            if isinstance(args, (CreateArgs, UpdateArgs)) and args.watch is not None:
                parse_watch(args.watch)
        except (ScheduleRefused, WatchRefused) as refused:
            raise _Refusal(f"Refused: {_esc(refused.text)}") from None
        if isinstance(args, UpdateArgs) and all(
                v is None for v in (args.name, args.instructions, args.schedule, args.watch)):
            raise _Refusal(NOTHING_TEXT)
        return args

    async def _owner_named(self, args: BaseModel, ctx: RecordContext) -> None:
        """A page the bot sets to watch must be one your own messages in this chat name (its address, a bare
        domain or a site by name, as ``open_page``'s link scope reads them), never a link a page showed."""
        raw = getattr(args, "watch", None)
        watch = parse_watch(raw) if raw is not None else None
        if watch is None:
            return
        texts = await self._owner_texts(ctx.user_id, ctx.thread_id) if self._owner_texts and ctx.thread_id else ()
        if not LinkScope.from_texts(texts).allows(watch.url):
            raise _Refusal(WATCH_NOT_NAMED_TEXT)

    async def _subject(self, name: str, args: BaseModel, ctx: RecordContext) -> str:
        """The routine's name the card shows: the new one for a create, the current one otherwise."""
        if isinstance(args, CreateArgs):
            return args.name.strip()
        return (await self._own(ctx, args.routine_id)).name

    async def _own(self, ctx: RecordContext, routine_id: str) -> Routine:
        routine = await self._routines.get(ctx.user_id, routine_id)
        if routine is None or routine.bot_id != ctx.bot_id:
            raise _Refusal(NOT_YOURS_TEXT)
        return routine

    async def _create(self, args: CreateArgs, ctx: RecordContext) -> ToolOutcome:
        routine = await self._service.create(
            ctx.user_id, ctx.bot_id, args.name, args.instructions, args.schedule, created_by="bot", tainted=False,
            watch=args.watch, model=args.model)
        return ToolOutcome(CREATED_TEXT.format(name=_esc(routine.name), next=_next_words(routine)), created=True)

    async def _change(self, name: str, args: BaseModel, routine: Routine, ctx: RecordContext) -> ToolOutcome:
        if name == "delete_routine":
            await self._service.delete(ctx.user_id, routine.id)
            return ToolOutcome(DELETED_TEXT.format(name=_esc(routine.name)))
        if name in ("pause_routine", "resume_routine"):
            on = name == "resume_routine"
            changed = await self._service.update(ctx.user_id, routine.id, {"enabled": on})
            return ToolOutcome((RESUMED_TEXT if on else PAUSED_TEXT).format(name=_esc(changed.name)))
        assert isinstance(args, UpdateArgs)
        changes = args.model_dump(exclude_none=True, exclude={"routine_id"})
        changed = await self._service.update(ctx.user_id, routine.id, changes)
        return ToolOutcome(CHANGED_TEXT.format(name=_esc(changed.name)))


def _detail(stored: dict[str, Any]) -> str:
    """The card's detail: the instructions, and the page a watch reads."""
    text, raw = stored.get("instructions", ""), stored.get("watch")
    found = parse_watch(raw) if isinstance(raw, dict) else None
    line = (f"Only runs when the page changes: {found.url} ({found.part or 'the whole page'}), checked every "
            f"{found.every_min} min.") if found is not None else ""
    return "\n\n".join(part for part in (text, line, _model_line(stored.get("model"))) if part)


def _model_line(value: object) -> str:
    """The card's model line: "Runs on Haiku 5.5." for a routine with its own model, "" for the bot's."""
    try:
        chosen = routine_model(value)
    except Refused:
        return ""
    return f"Runs on {model_label(chosen)}." if chosen is not None else ""


def _next_words(routine: Routine) -> str:
    """The user's next minute in local time (without the jitter), or the schedule in words when it is off."""
    if routine.watch is not None:
        return f"{watch_words(routine.watch)}; it runs only when the page changes"
    if routine.next_run_at is None:
        return readable(routine.schedule, now=utc_now())
    slot = slot_for(routine.next_run_at, routine.schedule)
    return f"{slot.astimezone(local_tz()):%a %d %b %H:%M} {zone_city()} time"
