"""``MacWrites``: ``mac_write_new``, ``mac_edit``, ``mac_rename`` and ``mac_trash`` (approval plan Task 10).

``prepare`` builds the card step BEFORE anything is written: it reads the current file at the keeper (the
model never sees that text, and reading it does not taint the run), refuses a read-only folder or a stale
``base_hash`` with a plain sentence, and returns the resolved call (grant id, path, base hash, the full new
text) with its line diff. ``execute`` runs a resolved call, and only that: the grant is looked up again, the
keeper checks the file's hash (``expected_sha256``), and a changed file writes nothing. ``run`` (a call the
mode lets straight through) is ``prepare`` then ``execute``.

Every write upserts the file's mark (hash, bot, whether the run was tainted) and posts an activity line with
Undo. Logs carry nothing from a file; neither do the activity lines (names only)."""

from __future__ import annotations

import posixpath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.memory.secrets import looks_secret
from roost.approvals.models import DiffView, FloorKind, PendingCall
from roost.constants import MAC_WRITE_EXTS
from roost.desk import DeskUnavailable
from roost.keeper.macfs.errors import MacFsError
from roost.mac.activity import activity_body, post_mac_activity
from roost.mac.diff import line_diff
from roost.mac.edits import EditError, apply_edits
from roost.mac.files import MacFiles
from roost.mac.grant_service import GrantService
from roost.mac.limits import MacLimits
from roost.mac.marks import MacMarkStore
from roost.mac.models import FileRef, Grant
from roost.mac.texts import MAC_AWAY_TEXT, mac_error_text
from roost.mac.tools import base_name, pick_folder
from roost.mac.wrap import clean_name
from roost.events.hub import EventHub
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome
from roost.talk.store import TalkStore

WRITE_NAMES = frozenset({"mac_write_new", "mac_edit", "mac_rename", "mac_trash"})
_FOLDER_MAX = 160
_PATH_MAX = 1024
BAD_ARGS_TEXT = "Refused: {name} needs {needs}."
_NEEDS = {
    "mac_write_new": "folder, path and text", "mac_edit": "folder, path, base_hash and edits (or the whole text)",
    "mac_rename": "folder, path and new_path", "mac_trash": "folder and path",
}
EDIT_NEEDS_TEXT = "Refused: mac_edit needs edits (old and new text) or the whole new text."
FILE_GONE_TEXT = "The file or folder isn't there any more."


class _Edit(BaseModel):
    model_config = ConfigDict(extra="ignore")
    old: str
    new: str


class NewArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    folder: str = Field(min_length=1, max_length=_FOLDER_MAX)
    path: str = Field(min_length=1, max_length=_PATH_MAX)
    text: str


class EditArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    folder: str = Field(min_length=1, max_length=_FOLDER_MAX)
    path: str = Field(min_length=1, max_length=_PATH_MAX)
    base_hash: str = Field(min_length=1, max_length=128)
    edits: list[_Edit] | None = None
    text: str | None = None


class MoveArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    folder: str = Field(min_length=1, max_length=_FOLDER_MAX)
    path: str = Field(min_length=1, max_length=_PATH_MAX)
    new_path: str = Field(min_length=1, max_length=_PATH_MAX)


class TrashArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    folder: str = Field(min_length=1, max_length=_FOLDER_MAX)
    path: str = Field(min_length=1, max_length=_PATH_MAX)


class Resolved(BaseModel):
    """A card's stored step. Only a stored step reaches ``execute``; the model's own arguments never do."""
    model_config = ConfigDict(extra="ignore")
    folder: str
    grant_id: str
    path: str
    new_text: str | None = None
    new_path: str | None = None
    base_sha256: str | None = None
    plus: int = 0
    minus: int = 0
    tainted_basis: bool = False


_ARGS: dict[str, type[BaseModel]] = {
    "mac_write_new": NewArgs, "mac_edit": EditArgs, "mac_rename": MoveArgs, "mac_trash": TrashArgs,
}


def _added_secret_floor(diff: DiffView) -> FloorKind | None:
    """``secret`` when the lines this write ADDS look like a secret, however the edits were split."""
    added = "\n".join(line[1:] for line in diff.text.splitlines() if line.startswith("+") and not line.startswith("+++"))
    return "secret" if looks_secret(added) else None


def _bad_ext(path: str) -> bool:
    return posixpath.splitext(path)[1].casefold() not in MAC_WRITE_EXTS


class MacWrites:
    names: frozenset[str] = WRITE_NAMES

    def __init__(self, grants: GrantService, files: MacFiles, marks: MacMarkStore, talk: TalkStore,
                 events: EventHub, limits: MacLimits | None = None) -> None:
        self._grants, self._files, self._marks = grants, files, marks
        self._talk, self._events, self._limits = talk, events, limits

    # --- the three doors ----------------------------------------------------------------------
    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        pending = await self.prepare(name, arguments, ctx)
        if isinstance(pending, str):
            return ToolOutcome(pending)
        outcome = await self.execute(name, dict(pending.arguments), ctx)
        if self._limits is not None and not outcome.failed:
            self._limits.note_write(ctx.bot_id)
        return outcome

    async def prepare(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> PendingCall | str:
        try:
            args = _ARGS[name].model_validate(arguments)
        except ValidationError:
            return BAD_ARGS_TEXT.format(name=name, needs=_NEEDS[name])
        grants = await self._grants.for_bot(ctx.user_id, ctx.bot_id) or ()
        grant = pick_folder(grants, args.folder)
        if isinstance(grant, str):
            return grant
        if grant.access != "read_write":
            return mac_error_text("read_only", clean_name(grant.label))
        try:
            return await self._build(name, args, grant, ctx)
        except MacFsError as exc:
            return mac_error_text(exc.code, clean_name(grant.label))
        except EditError as exc:
            return f"Refused: {exc}"
        except DeskUnavailable:
            return MAC_AWAY_TEXT

    async def execute(self, name: str, resolved: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        try:
            step = Resolved.model_validate(resolved)
        except ValidationError:
            return ToolOutcome(FILE_GONE_TEXT, failed=True)
        grants = await self._grants.for_bot(ctx.user_id, ctx.bot_id) or ()
        grant = next((g for g in grants if g.id == step.grant_id), None)
        if grant is None:
            return ToolOutcome(mac_error_text("no_grant", clean_name(step.folder)), failed=True)
        if grant.access != "read_write":
            return ToolOutcome(mac_error_text("read_only", clean_name(grant.label)), failed=True)
        try:
            return await self._execute(name, step, grant, ctx)
        except MacFsError as exc:
            return ToolOutcome(mac_error_text(exc.code, clean_name(grant.label)), failed=True)
        except DeskUnavailable:
            return ToolOutcome(MAC_AWAY_TEXT, failed=True)

    # --- building the card step ---------------------------------------------------------------
    async def _build(self, name: str, args: Any, grant: Grant, ctx: RecordContext) -> PendingCall | str:
        ref = FileRef(grant.id, ctx.bot_id, args.path)
        label = clean_name(grant.label)
        if name == "mac_write_new":
            return await self._build_new(args, grant, ref, label)
        if name == "mac_edit":
            return await self._build_edit(args, grant, ref, label, ctx)
        sha = await self._current_sha(ref)
        if sha is None:
            return mac_error_text("not_found", label)
        base = {"folder": grant.label, "grant_id": grant.id, "path": args.path, "base_sha256": sha}
        if name == "mac_rename":
            if _bad_ext(args.new_path):
                return mac_error_text("bad_ext")
            return PendingCall(
                tool=name, arguments={**base, "new_path": args.new_path}, topic="files",
                title=f"Rename {base_name(args.path)} → {base_name(args.new_path)} · {label}",
                detail=f"{clean_name(args.path)} → {clean_name(args.new_path)}")
        return PendingCall(tool=name, arguments=base, topic="files",
                           title=f"Move {base_name(args.path)} to the trash · {label}", detail=clean_name(args.path))

    async def _current_sha(self, ref: FileRef) -> str | None:
        stats = await self._files.stat(ref.grant_id, ref.bot_id, [ref.path])
        return stats[0].sha256 if stats else None

    async def _build_new(self, args: NewArgs, grant: Grant, ref: FileRef, label: str) -> PendingCall | str:
        if _bad_ext(args.path):
            return mac_error_text("bad_ext")
        if await self._current_sha(ref) is not None:
            return mac_error_text("exists", label)
        diff = line_diff("", args.text)
        return PendingCall(
            tool="mac_write_new", topic="files", floor=_added_secret_floor(diff), title=f"Create {base_name(args.path)} · {label}",
            detail=clean_name(args.path), diff=diff,
            arguments={"folder": grant.label, "grant_id": grant.id, "path": args.path, "new_text": args.text,
                       "plus": diff.plus, "minus": diff.minus})

    async def _build_edit(self, args: EditArgs, grant: Grant, ref: FileRef, label: str,
                          ctx: RecordContext) -> PendingCall | str:
        if args.edits is None and args.text is None:
            return EDIT_NEEDS_TEXT
        current = await self._files.read(ref)                # never shown to the model; reading it taints nothing
        if args.base_hash != current.sha256:
            return mac_error_text("changed")
        new_text = args.text if args.edits is None else apply_edits(
            current.text, [{"old": e.old, "new": e.new} for e in args.edits])
        diff: DiffView = line_diff(current.text, new_text or "")
        return PendingCall(
            tool="mac_edit", topic="files", floor=_added_secret_floor(diff), title=f"Edit {base_name(args.path)} · {label}",
            detail=clean_name(args.path), diff=diff, tainted_basis=ctx.tainted,
            arguments={"folder": grant.label, "grant_id": grant.id, "path": args.path,
                       "base_sha256": current.sha256, "new_text": new_text, "plus": diff.plus,
                       "minus": diff.minus, "tainted_basis": ctx.tainted})

    # --- running a resolved step --------------------------------------------------------------
    async def _execute(self, name: str, step: Resolved, grant: Grant, ctx: RecordContext) -> ToolOutcome:
        ref = FileRef(grant.id, ctx.bot_id, step.path)
        label = clean_name(grant.label)
        if name == "mac_write_new" and step.new_text is not None:
            wrote = await self._files.create(ref, step.new_text)
            await self._mark(ctx, grant, step.path, wrote.sha256)
            undo = {"kind": "create", "path": step.path, "expected_sha256": wrote.sha256}
            await self._announce(ctx, grant, step, "create", undo)
            return ToolOutcome(f"Created {base_name(step.path)} in {label}. Its hash is {wrote.sha256}.", created=True)
        if name == "mac_edit" and step.new_text is not None and step.base_sha256:
            wrote = await self._files.write(ref, step.new_text, step.base_sha256)
            await self._mark(ctx, grant, step.path, wrote.sha256)
            undo = {"kind": "content", "path": step.path, "backup_id": wrote.backup_id,
                    "expected_sha256": wrote.sha256}
            await self._announce(ctx, grant, step, "edit", undo)
            return ToolOutcome(f"Edited {base_name(step.path)} in {label} (+{step.plus} −{step.minus}). "
                               f"Its hash is now {wrote.sha256}.")
        if name == "mac_rename" and step.new_path and step.base_sha256:
            sha = await self._files.rename(ref, step.new_path, step.base_sha256)
            await self._carry_mark(ctx, grant, step.path, step.new_path, sha)
            undo = {"kind": "rename", "path": step.new_path, "back_to": step.path, "expected_sha256": sha}
            await self._announce(ctx, grant, step, "rename", undo)
            return ToolOutcome(f"Renamed {base_name(step.path)} to {base_name(step.new_path)} in {label}.")
        if name == "mac_trash" and step.base_sha256:
            trashed = await self._files.trash(ref, step.base_sha256)
            undo = {"kind": "trash", "trash_name": trashed.trash_name, "back_to": step.path}
            await self._announce(ctx, grant, step, "trash", undo)
            return ToolOutcome(f"Moved {base_name(step.path)} in {label} to the trash. The user can undo it.")
        return ToolOutcome(FILE_GONE_TEXT, failed=True)

    async def _mark(self, ctx: RecordContext, grant: Grant, path: str, sha256: str) -> None:
        await self._marks.upsert(ctx.user_id, grant.id, path, sha256, ctx.bot_id, written_tainted=ctx.tainted)

    async def _carry_mark(self, ctx: RecordContext, grant: Grant, path: str, new_path: str, sha256: str) -> None:
        """A renamed file is the same content: its mark (clean or not) moves with it."""
        old = await self._marks.get(ctx.user_id, grant.id, path)
        if old is not None:
            await self._marks.upsert(ctx.user_id, grant.id, new_path, sha256, old.bot_id,
                                     written_tainted=old.written_tainted)

    async def _announce(self, ctx: RecordContext, grant: Grant, step: Resolved, op: str,
                        undo: dict[str, Any]) -> None:
        if ctx.thread_id is None:
            return
        body = activity_body(
            op, grant.label, step.path, new_path=step.new_path, plus=step.plus, minus=step.minus,
            tainted_basis=step.tainted_basis or (op == "edit" and ctx.tainted), undo={"grant_id": grant.id, **undo})
        await post_mac_activity(self._talk, self._events, ctx.user_id, ctx.thread_id, ctx.bot_id, body)
