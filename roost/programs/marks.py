"""``WorkspaceMarks``: whether outside content may be in a bot's workspace (design §5).

The workspace has no network, so outside content gets in only through a program or a file write the user
approved in a tainted run. Every such call already leaves an ``audit`` row (decision ``do``, ``tainted = 1``),
so the mark is read from there and needs no table of its own.

Wipe workspace clears it: a finished wipe leaves a ``workspace_wipe`` row, and only marking rows after the
newest one count. The gate writes its row when it decides, which can be before a wipe that then runs first,
so a tainted write also leaves a ``workspace_mark`` row as it runs, under the bot's workspace lock."""

from __future__ import annotations

from datetime import datetime, timezone

from roost.config import Config
from roost.constants import WORKSPACE_MARK_ACTION, WORKSPACE_WIPE_ACTION
from roost.db.connection import db_session

MARKING_TOOLS = ("run_program", "write_file", WORKSPACE_MARK_ACTION)

_MARKED_SQL = (
    "SELECT 1 FROM audit WHERE user_id = ? AND bot_id = ? AND action IN (?, ?, ?) AND decision = 'do' "
    "AND tainted = 1 AND id > COALESCE((SELECT MAX(id) FROM audit WHERE user_id = ? AND bot_id = ? "
    "AND action = ? AND decision = 'do'), 0) LIMIT 1"
)


class WorkspaceMarks:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def marked(self, user_id: str, bot_id: str) -> bool:
        async with db_session(self._config) as db:
            cursor = await db.execute(
                _MARKED_SQL, (user_id, bot_id, *MARKING_TOOLS, user_id, bot_id, WORKSPACE_WIPE_ACTION))
            return await cursor.fetchone() is not None

    async def clear(self, user_id: str, bot_id: str) -> None:
        """The owner wiped the workspace: earlier marks stop counting."""
        await self._insert(user_id, bot_id, WORKSPACE_WIPE_ACTION, "owner_wipe", tainted=False)

    async def note(self, user_id: str, bot_id: str) -> None:
        """A tainted program or file write is running now: the workspace is marked from here on."""
        await self._insert(user_id, bot_id, WORKSPACE_MARK_ACTION, "tainted_write", tainted=True)

    async def _insert(self, user_id: str, bot_id: str, action: str, reason: str, *, tainted: bool) -> None:
        async with db_session(self._config) as db:
            await db.execute(
                "INSERT INTO audit (user_id, bot_id, action, decision, detail, created_at, reason, tainted) "
                "VALUES (?, ?, ?, 'do', NULL, ?, ?, ?)",
                (user_id, bot_id, action, datetime.now(timezone.utc).isoformat(), reason, int(tainted)),
            )
            await db.commit()
