"""``MacTools``: ``mac_find`` and ``mac_read`` for every bot (Your Mac, approval plan Task 9; Task 10 adds the
writes in ``roost/mac/write_tools.py``).

The folder the bot names is resolved among ITS grants (its own and the all-bots ones) by case-folded label;
an unknown or another bot's folder names the bot's own. A search by name is metadata and keeps the run clean;
a search by words and every read taint the run like a web page, unless the file's hash is exactly what this
bot wrote in a clean run (``MacMarkStore``). File text, names and snippets reach the model only as quoted,
escaped data (``roost/mac/wrap.py``). Logs carry nothing from a file: no path, name, label or text."""

from __future__ import annotations

import html
import logging
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.approvals.models import PendingCall
from roost.constants import MAC_FIND_QUERY_MAX_CHARS, MAC_LABEL_MAX_CHARS
from roost.desk import DeskUnavailable
from roost.keeper.macfs.errors import MacFsError
from roost.mac.files import MacFiles
from roost.mac.grant_service import GrantService
from roost.mac.marks import MacMarkStore
from roost.mac.models import FileRef, Grant
from roost.mac.texts import MAC_AWAY_TEXT, mac_error_text
from roost.mac.wrap import clean_name, wrap_file, wrap_hits
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome

log = logging.getLogger(__name__)

READ_NAMES = frozenset({"mac_find", "mac_read"})
_ACTIVITY = {
    "mac_find": "searching your Mac folders", "mac_read": "reading a Mac file",
    "mac_write_new": "writing a Mac file", "mac_edit": "editing a Mac file",
    "mac_rename": "renaming a Mac file", "mac_trash": "moving a Mac file to the trash",
}
_LABEL_INPUT_MAX = MAC_LABEL_MAX_CHARS * 4
_PATH_INPUT_MAX = 1024
BAD_FIND_TEXT = "Refused: mac_find needs query (words from a name) or text (words inside files)."
BAD_READ_TEXT = "Refused: mac_read needs folder and path."
NO_FOLDERS_WORD = "none"


class FindArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    query: str | None = Field(default=None, max_length=MAC_FIND_QUERY_MAX_CHARS)
    text: str | None = Field(default=None, max_length=MAC_FIND_QUERY_MAX_CHARS)
    folder: str | None = Field(default=None, max_length=_LABEL_INPUT_MAX)


class ReadArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    folder: str = Field(min_length=1, max_length=_LABEL_INPUT_MAX)
    path: str = Field(min_length=1, max_length=_PATH_INPUT_MAX)


def _escape(text: str) -> str:
    return html.escape(clean_name(text), quote=True)


def folder_list(grants: Sequence[Grant]) -> str:
    return ", ".join(_escape(g.label) for g in grants) or NO_FOLDERS_WORD


def no_such_folder(label: str, grants: Sequence[Grant]) -> str:
    return f"No folder named {_escape(label)} is shared with you. Your folders: {folder_list(grants)}."


def pick_folder(grants: Sequence[Grant], label: str) -> Grant | str:
    """The grant whose label equals ``label`` (case-folded), or the sentence that names the bot's own folders."""
    wanted = label.strip().casefold()
    found = next((g for g in grants if g.label.casefold() == wanted), None)
    return found if found is not None else no_such_folder(label, grants)


def base_name(path: str) -> str:
    return clean_name(path.rstrip("/").rsplit("/", 1)[-1])


class MacTools:
    names: frozenset[str] = READ_NAMES

    def __init__(self, grants: GrantService, files: MacFiles, marks: MacMarkStore, sessions: Any = None,
                 *, writes: Any = None) -> None:
        self._grants, self._files, self._marks, self._sessions = grants, files, marks, sessions
        self._writes = writes
        if writes is not None:
            self.names = READ_NAMES | writes.names

    def activity(self, name: str) -> str:
        return _ACTIVITY.get(name, "using a Mac folder")

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        if name in READ_NAMES:
            return await self._run_read(name, arguments, ctx)
        return await self._writes.run(name, arguments, ctx)

    async def prepare(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> PendingCall | str:
        if name in READ_NAMES:
            return await self._prepare_read(name, arguments, ctx)
        return await self._writes.prepare(name, arguments, ctx)

    async def execute(self, name: str, resolved: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        if name in READ_NAMES:
            return await self._execute_read(name, resolved, ctx)
        return await self._writes.execute(name, resolved, ctx)

    async def my_grants(self, ctx: RecordContext) -> tuple[Grant, ...]:
        return await self._grants.for_bot(ctx.user_id, ctx.bot_id) or ()

    # --- reads --------------------------------------------------------------------------------
    async def _run_read(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        grants = await self.my_grants(ctx)
        if name == "mac_read":
            args = _parse(ReadArgs, arguments)
            if args is None:
                return ToolOutcome(BAD_READ_TEXT)
            grant = pick_folder(grants, args.folder)
            return ToolOutcome(grant) if isinstance(grant, str) else await self._read(ctx, grant, args.path)
        find = _parse(FindArgs, arguments)
        if find is None or not (find.query or find.text):
            return ToolOutcome(BAD_FIND_TEXT)
        chosen: Sequence[Grant] | str = grants
        if find.folder:
            one = pick_folder(grants, find.folder)
            chosen = one if isinstance(one, str) else [one]
        return ToolOutcome(chosen) if isinstance(chosen, str) else await self._find(ctx, chosen, find)

    async def _execute_read(self, name: str, resolved: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        """A stored read: the grants are looked up by the ids the card kept, and each must still be this bot's."""
        grants = await self.my_grants(ctx)
        if name == "mac_read":
            grant = next((g for g in grants if g.id == resolved.get("grant_id")), None)
            path = resolved.get("path")
            if grant is None or not isinstance(path, str):
                return ToolOutcome(_gone(resolved), failed=True)
            return await self._read(ctx, grant, path)
        ids = resolved.get("grant_ids")
        chosen = [g for g in grants if isinstance(ids, list) and g.id in ids]
        if not chosen:
            return ToolOutcome(_gone(resolved), failed=True)
        find = FindArgs(query=resolved.get("query"), text=resolved.get("text"))
        return await self._find(ctx, chosen, find)

    async def _read(self, ctx: RecordContext, grant: Grant, path: str) -> ToolOutcome:
        try:
            file = await self._files.read(FileRef(grant.id, ctx.bot_id, path))
        except MacFsError as exc:
            return ToolOutcome(mac_error_text(exc.code, _escape(grant.label)))
        except DeskUnavailable:
            return ToolOutcome(MAC_AWAY_TEXT)
        own_clean = await self._marks.clean_for(ctx.user_id, grant.id, path, file.sha256, ctx.bot_id)
        return ToolOutcome(wrap_file(grant.label, path, file), tainted=not own_clean)

    async def _find(self, ctx: RecordContext, grants: Sequence[Grant], args: FindArgs) -> ToolOutcome:
        parts: list[str] = []
        for grant in grants:
            try:
                found = await self._files.find(grant.id, ctx.bot_id, name=args.query or None, text=args.text or None)
            except MacFsError as exc:
                parts.append(mac_error_text(exc.code, _escape(grant.label)))
                continue
            except DeskUnavailable:
                return ToolOutcome(MAC_AWAY_TEXT)
            parts.append(wrap_hits(grant.label, found.hits, found.truncated))
        # Names are metadata and keep the run clean; the words inside files are content.
        return ToolOutcome("\n".join(parts), tainted=bool(args.text))

    async def _prepare_read(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> PendingCall | str:
        grants = await self.my_grants(ctx)
        if name == "mac_read":
            args = _parse(ReadArgs, arguments)
            if args is None:
                return BAD_READ_TEXT
            grant = pick_folder(grants, args.folder)
            if isinstance(grant, str):
                return grant
            return PendingCall(
                tool=name, arguments={"folder": grant.label, "grant_id": grant.id, "path": args.path}, topic="files",
                title=f"Read {base_name(args.path)} · {clean_name(grant.label)}", detail=clean_name(args.path),
                session_offer=grant.read_policy == "ask_session")
        find = _parse(FindArgs, arguments)
        if find is None or not (find.query or find.text):
            return BAD_FIND_TEXT
        chosen: Sequence[Grant] = grants
        if find.folder:
            one = pick_folder(grants, find.folder)
            if isinstance(one, str):
                return one
            chosen = [one]
        words = clean_name(find.query or find.text or "")
        where = clean_name(chosen[0].label) if len(chosen) == 1 else "your Mac folders"
        resolved: dict[str, Any] = {"query": find.query, "text": find.text, "grant_ids": [g.id for g in chosen]}
        if len(chosen) == 1:
            resolved = {**resolved, "folder": chosen[0].label, "grant_id": chosen[0].id}
        return PendingCall(
            tool=name, arguments=resolved, topic="files", title=f"Search {where} for “{words}”",
            session_offer=len(chosen) == 1 and chosen[0].read_policy == "ask_session")


def _gone(resolved: dict[str, Any]) -> str:
    folder = resolved.get("folder")
    return f"No folder named {_escape(folder) if isinstance(folder, str) else 'that'} is shared with you any more."


def _parse(model: type[BaseModel], arguments: dict[str, Any]):
    try:
        return model.model_validate(arguments)
    except ValidationError:
        return None
