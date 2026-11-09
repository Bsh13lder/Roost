"""``MacUndo``: the Undo button of a Mac activity line. It runs at once, with no card, and reverts exactly
that change.

The line carries the keeper's undo body (``kind`` and the hashes it expects), so a file changed since is
refused (409, "nothing was undone") and a second Undo finds the line spent. Another user's line, or a
message that is not an activity line with an Undo, reads as no such line (``None``)."""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, ConfigDict, ValidationError

from roost.desk import DeskUnavailable
from roost.events.hub import EventHub
from roost.keeper.macfs.errors import MacFsError
from roost.mac.activity import activity_body, post_mac_activity
from roost.mac.files import MacFiles
from roost.mac.grant_service import GrantService
from roost.mac.models import UndoKind, UndoSpec
from roost.mac.texts import MAC_AWAY_TEXT
from roost.talk.store import Message, TalkStore

log = logging.getLogger(__name__)

CHANGED_TEXT = "The file changed since; nothing was undone."
EXPIRED_TEXT = "The backup for this change has expired."
SPENT_TEXT = "That was already undone."
NOT_SHARED_TEXT = "That folder isn't shared with this bot any more, so nothing was undone."


class UndoRefused(Exception):
    """A plain-sentence reason the undo did not happen (HTTP 409); ``away`` means the keeper was unreachable (503)."""

    def __init__(self, text: str, *, away: bool = False) -> None:
        super().__init__(text)
        self.away = away


class _UndoBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grant_id: str
    kind: UndoKind
    path: str | None = None
    backup_id: str | None = None
    back_to: str | None = None
    trash_name: str | None = None
    expected_sha256: str | None = None


class MacUndo:
    def __init__(self, talk: TalkStore, events: EventHub, grants: GrantService, files: MacFiles) -> None:
        self._talk, self._events, self._grants, self._files = talk, events, grants, files

    async def undo(self, user_id: str, message_id: str) -> Message | None:
        line = await self._talk.get_message(user_id, message_id)
        data = _activity(line)
        if line is None or data is None or line.author_bot_id is None:
            return None
        raw = data.get("undo")
        if not raw:
            raise UndoRefused(SPENT_TEXT)
        try:
            body = _UndoBody.model_validate(raw)
        except ValidationError:
            return None
        bot_id = line.author_bot_id
        grants = await self._grants.for_bot(user_id, bot_id) or ()
        if not any(g.id == body.grant_id for g in grants):
            raise UndoRefused(NOT_SHARED_TEXT)
        await self._run(body, bot_id)
        spent = json.dumps({**data, "undo": None})
        await self._talk.replace_body(user_id, line.id, spent)
        said = activity_body("undo", str(data["label"]), str(data["path"]), new_path=data.get("new_path"),
                             undid=str(data["op"]))
        return await post_mac_activity(self._talk, self._events, user_id, line.thread_id, bot_id, said)

    async def _run(self, body: _UndoBody, bot_id: str) -> None:
        spec = UndoSpec(kind=body.kind, path=body.path, backup_id=body.backup_id, back_to=body.back_to,
                        trash_name=body.trash_name, expected_sha256=body.expected_sha256)
        try:
            await self._files.undo(body.grant_id, bot_id, spec)
        except MacFsError as exc:
            log.info("A Mac undo was refused: %s", exc.code)
            gone = body.kind == "content" and exc.code == "not_found"   # the keeper loads the backup first
            raise UndoRefused(EXPIRED_TEXT if gone else CHANGED_TEXT) from None
        except DeskUnavailable:
            raise UndoRefused(MAC_AWAY_TEXT, away=True) from None


def _activity(line: Message | None) -> dict | None:
    if line is None or line.kind != "mac_activity" or line.role != "activity":
        return None
    try:
        data = json.loads(line.body)
    except ValueError:
        return None
    return data if isinstance(data, dict) and "op" in data else None
