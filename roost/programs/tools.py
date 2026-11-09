"""``ProgramTools``: ``run_program``, ``write_file``, ``read_file`` and ``list_files`` in the bot's own workspace.

Every call goes through the desk's ``exec`` (``["/bin/sh", "-c", command]`` at the keeper, inside the bot's own
container only). ``prepare`` builds the Ask card step for a tainted run; ``execute`` runs a stored step after
the user's Yes and is never capped. Output from a marked workspace taints the run (``WorkspaceMarks``).
One workspace call runs at a time per bot: the keeper kills every process in the container after each exec,
so two at once would kill each other."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ValidationError

from roost.approvals.models import PendingCall
from roost.constants import (
    APPROVAL_TITLE_MAX_CHARS, PROGRAM_CALLS_PER_RUN, PROGRAM_FILE_OP_TIMEOUT_S, PROGRAM_RUNS_REMEMBERED,
)
from roost.desk import Desk, DeskUnavailable, ExecResult
from roost.events.hub import EventHub
from roost.programs.args import ListArgs, ReadArgs, RunArgs, WriteArgs
from roost.programs.file_ops import (
    ERROR_EXIT, error_code, file_ops_command, parse_listing, parse_read, stderr_facts,
)
from roost.programs.marks import WorkspaceMarks
from roost.programs.wrap import (
    COULD_NOT_TEXT, UNAVAILABLE_TEXT, error_text, file_text, listing_text, program_text, run_line_body,
    write_line_body,
)
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome
from roost.talk.store import TalkStore, message_out

DeskSource = Callable[[str], Desk]
InternetLookup = Callable[[str, str], Awaitable[bool]]   # (user_id, bot_id): the workspace has internet (A4)
COUNTED = frozenset({"run_program", "write_file"})
CAP_TEXT = (
    f"Refused: you ran {PROGRAM_CALLS_PER_RUN} programs and file writes in this request. "
    "Say where you got to; the user can ask you to go on."
)
_ARGS: dict[str, type[BaseModel]] = {
    "run_program": RunArgs, "write_file": WriteArgs, "read_file": ReadArgs, "list_files": ListArgs,
}
_NEEDS = {
    "run_program": "a command (and an optional timeout_s from 1 to 120)",
    "write_file": "a path inside your workspace and the text",
    "read_file": "a path inside your workspace", "list_files": "a folder inside your workspace, or none",
}
_ACTIVITY = {
    "run_program": "running a program", "write_file": "writing a file", "read_file": "reading a file",
    "list_files": "looking at its files",
}


class ProgramLimits:
    """Per-run counts of unapproved programs and writes, and one lock per bot. In memory, like ``MacLimits``."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def take(self, key: str) -> bool:
        used = self._counts.get(key, 0)
        if used >= PROGRAM_CALLS_PER_RUN:
            return False
        kept = [(k, v) for k, v in self._counts.items() if k != key][-(PROGRAM_RUNS_REMEMBERED - 1):]
        self._counts = {**dict(kept), key: used + 1}
        return True

    def lock(self, bot_id: str) -> asyncio.Lock:
        if bot_id not in self._locks:
            self._locks = {**self._locks, bot_id: asyncio.Lock()}
        return self._locks[bot_id]


def _parse(name: str, arguments: dict[str, Any]) -> BaseModel | str:
    try:
        return _ARGS[name].model_validate(arguments)
    except ValidationError:
        return f"Refused: {name} needs {_NEEDS[name]}."


def _cap(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= APPROVAL_TITLE_MAX_CHARS else flat[: APPROVAL_TITLE_MAX_CHARS - 1] + "…"


class ProgramTools:
    names: frozenset[str] = frozenset(_ARGS)

    def __init__(self, desks: DeskSource, marks: WorkspaceMarks | None, talk: TalkStore | None,
                 events: EventHub | None, limits: ProgramLimits | None = None, *,
                 internet: InternetLookup | None = None) -> None:
        self._desks, self._marks, self._talk, self._events = desks, marks, talk, events
        self._limits = limits if limits is not None else ProgramLimits()
        self._internet = internet

    def activity(self, name: str) -> str:
        return _ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = _parse(name, arguments)
        if isinstance(args, str):
            return ToolOutcome(args)
        if name in COUNTED and not self._limits.take(ctx.run_id or f"bot:{ctx.bot_id}"):
            return ToolOutcome(CAP_TEXT)
        return await self._do(name, args, ctx)

    async def prepare(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> PendingCall | str:
        """The Ask card's step: the checked call, so the card shows exactly what Yes runs."""
        args = _parse(name, arguments)
        if isinstance(args, str):
            return args
        if isinstance(args, RunArgs):
            title = f"Run a program: {args.command}"
        else:
            title = f"Write {args.path} in its workspace"
        return PendingCall(tool=name, arguments=args.model_dump(), topic="programs", title=_cap(title),
                           tainted_basis=ctx.tainted)

    async def execute(self, name: str, resolved: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        """A stored step after the user's Yes: checked again, never counted against the run's cap."""
        args = _parse(name, resolved)
        if isinstance(args, str):
            return ToolOutcome(args, failed=True)
        return await self._do(name, args, ctx)

    async def _do(self, name: str, args: BaseModel, ctx: RecordContext) -> ToolOutcome:
        try:
            async with self._limits.lock(ctx.bot_id):
                if name in COUNTED and ctx.tainted and self._marks is not None:
                    await self._marks.note(ctx.user_id, ctx.bot_id)   # after any wipe that ran first (marks.py)
                if isinstance(args, RunArgs):
                    return await self._run_program(args, ctx)
                if isinstance(args, WriteArgs):
                    return await self._write(args, ctx)
                if isinstance(args, ReadArgs):
                    return await self._read(args, ctx)
                return await self._list(args, ctx)  # type: ignore[arg-type]
        except DeskUnavailable:
            return ToolOutcome(UNAVAILABLE_TEXT, failed=True)

    async def _exec(self, ctx: RecordContext, command: str, timeout_s: int) -> ExecResult:
        return await self._desks(ctx.bot_id).exec(command, timeout_s=timeout_s)

    async def _marked(self, ctx: RecordContext) -> bool:
        """Outside content may be in what the workspace gives back: the run read some, a tainted write marked the
        workspace, or (A4) the workspace has internet, so a program may have fetched a page."""
        if ctx.tainted:
            return True
        if self._internet is not None and await self._internet(ctx.user_id, ctx.bot_id):
            return True
        return self._marks is not None and await self._marks.marked(ctx.user_id, ctx.bot_id)

    async def _run_program(self, args: RunArgs, ctx: RecordContext) -> ToolOutcome:
        result = await self._exec(ctx, args.command, args.timeout_s)
        tainted = await self._marked(ctx)
        await self._post(ctx, run_line_body(args.command, result, tainted=ctx.tainted), tainted)
        return ToolOutcome(program_text(args.command, result), tainted=tainted)

    async def _write(self, args: WriteArgs, ctx: RecordContext) -> ToolOutcome:
        result = await self._exec(ctx, file_ops_command("write", args.path, args.text), PROGRAM_FILE_OP_TIMEOUT_S)
        failed = _failure(result)
        if failed is not None:
            return ToolOutcome(failed, failed=True)
        await self._post(ctx, write_line_body(args.path, result, tainted=ctx.tainted), ctx.tainted)
        written = stderr_facts(result.stderr).get("bytes")
        size = f" ({written} bytes)" if isinstance(written, int) else ""
        return ToolOutcome(f"Wrote {args.path} in your workspace{size}.")

    async def _read(self, args: ReadArgs, ctx: RecordContext) -> ToolOutcome:
        result = await self._exec(ctx, file_ops_command("read", args.path), PROGRAM_FILE_OP_TIMEOUT_S)
        failed = _failure(result)
        if failed is not None:
            return ToolOutcome(failed, failed=True)
        return ToolOutcome(file_text(args.path, parse_read(result.stdout, result.stderr)),
                           tainted=await self._marked(ctx))

    async def _list(self, args: ListArgs, ctx: RecordContext) -> ToolOutcome:
        result = await self._exec(ctx, file_ops_command("list", args.path), PROGRAM_FILE_OP_TIMEOUT_S)
        failed = _failure(result)
        if failed is not None:
            return ToolOutcome(failed, failed=True)
        return ToolOutcome(listing_text(args.path, parse_listing(result.stdout)), tainted=await self._marked(ctx))

    async def _post(self, ctx: RecordContext, body: str, tainted: bool) -> None:
        """The chat's quiet line (role ``activity``, never replayed to a model)."""
        if ctx.thread_id is None or self._talk is None or self._events is None:
            return
        message = await self._talk.add_message(ctx.user_id, ctx.thread_id, role="activity", body=body,
                                               tainted=tainted, kind="program_activity", author_bot_id=ctx.bot_id)
        await self._events.publish(ctx.user_id, {"type": "message", "thread_id": ctx.thread_id,
                                                 "message": message_out(message)})


def _failure(result: ExecResult) -> str | None:
    """A file call's refusal in words, or None when it worked."""
    if result.exit_code == 0 and not result.timed_out:
        return None
    if result.exit_code == ERROR_EXIT:
        return error_text(error_code(result.stderr))
    return COULD_NOT_TEXT
