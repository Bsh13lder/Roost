"""``CommentStore`` — comments on the user's tasks, encrypted (redesign P3).

- The body is ``enc:v2`` under ``task_comments:body``; ids, the author, the
  step, the taint bit and the times stay plaintext.
- Every query names the user. A comment is only ever read, added or changed
  while its task is live (not deleted) and the user's, checked in the same
  session as the write.
- Deleting is soft. ``edit`` and ``delete`` only touch the user's own comments
  (``author = 'user'``): the service says why, this is the floor under it."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.tasks.comments import COMMENT_BY_USER, TaskComment

_COLUMNS = ("id", "user_id", "task_id", "step_id", "author", "body", "tainted", "created_at", "edited_at")
_SELECT = ", ".join(f"c.{column}" for column in _COLUMNS)
_FROM_LIVE = ("FROM task_comments c JOIN tasks t ON t.id = c.task_id AND t.user_id = c.user_id "
              "WHERE c.user_id = ? AND c.deleted_at IS NULL AND t.deleted_at IS NULL")
_LIVE_TASK = "SELECT 1 FROM tasks WHERE id = ? AND user_id = ? AND deleted_at IS NULL"
_OWN = "WHERE id = ? AND user_id = ? AND author = ? AND deleted_at IS NULL"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str) -> bytes:
    return user_aad(user_id, "task_comments:body")


def _row_to_comment(row: aiosqlite.Row, dek: bytes) -> TaskComment:
    return TaskComment(
        id=row["id"], user_id=row["user_id"], task_id=row["task_id"], step_id=row["step_id"],
        author=row["author"], body=decrypt_field(row["body"], dek, _aad(row["user_id"])) or "",
        tainted=bool(row["tainted"]), created_at=row["created_at"], edited_at=row["edited_at"],
    )


class CommentStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def add(self, user_id: str, task_id: str, *, step_id: str | None, author: str, body: str,
                  tainted: bool) -> TaskComment | None:
        """The new comment; ``None`` (nothing written) when the task isn't a live task of the user's."""
        comment = TaskComment(id=str(uuid4()), user_id=user_id, task_id=task_id, step_id=step_id, author=author,
                              body=body, tainted=tainted, created_at=_now_iso(), edited_at=None)
        dek = await get_user_dek(self._config, user_id)
        values = (comment.id, user_id, task_id, step_id, author, encrypt_field(body, dek, _aad(user_id)),
                  int(tainted), comment.created_at, None)
        async with db_session(self._config) as db:
            if await (await db.execute(_LIVE_TASK, (task_id, user_id))).fetchone() is None:
                return None
            await db.execute(f"INSERT INTO task_comments ({', '.join(_COLUMNS)}) "
                             f"VALUES ({','.join('?' * len(_COLUMNS))})", values)
            await db.commit()
        return comment

    async def list(self, user_id: str, task_id: str, *, limit: int) -> tuple[TaskComment, ...]:
        """The task's newest ``limit`` comments, oldest first."""
        newest = await self._select(user_id, f"{_FROM_LIVE} AND c.task_id = ? "
                                              "ORDER BY c.created_at DESC, c.rowid DESC LIMIT ?",
                                    (user_id, task_id, limit))
        return tuple(reversed(newest))

    async def counts(self, user_id: str, task_ids: Sequence[str]) -> dict[str, int]:
        """How many live comments each of these tasks has; a task with none is left out. Nothing is decrypted."""
        if not task_ids:
            return {}
        marks = ",".join("?" * len(task_ids))
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT c.task_id, COUNT(*) {_FROM_LIVE} AND c.task_id IN ({marks}) GROUP BY c.task_id",
                (user_id, *task_ids))).fetchall()
        return {row[0]: row[1] for row in rows}

    async def get(self, user_id: str, comment_id: str) -> TaskComment | None:
        found = await self._select(user_id, f"{_FROM_LIVE} AND c.id = ?", (user_id, comment_id))
        return found[0] if found else None

    async def edit(self, user_id: str, comment_id: str, body: str) -> TaskComment | None:
        """The edited comment; ``None`` when it is gone, a bot's, or not the user's."""
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            cursor = await db.execute(f"UPDATE task_comments SET body = ?, edited_at = ? {_OWN}",
                                      (encrypt_field(body, dek, _aad(user_id)), _now_iso(), comment_id, user_id,
                                       COMMENT_BY_USER))
            await db.commit()
        return await self.get(user_id, comment_id) if cursor.rowcount else None

    async def delete(self, user_id: str, comment_id: str) -> bool:
        async with db_session(self._config) as db:
            cursor = await db.execute(f"UPDATE task_comments SET deleted_at = ? {_OWN}",
                                      (_now_iso(), comment_id, user_id, COMMENT_BY_USER))
            await db.commit()
        return cursor.rowcount > 0

    async def unlink_step(self, user_id: str, task_id: str, step_id: str) -> int:
        """A deleted step's comments stay on its task (redesign P3). Returns how many moved."""
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE task_comments SET step_id = NULL WHERE user_id = ? AND task_id = ? AND step_id = ?",
                (user_id, task_id, step_id))
            await db.commit()
        return cursor.rowcount

    async def _select(self, user_id: str, where: str, params: tuple) -> tuple[TaskComment, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_SELECT} {where}", params)).fetchall()
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_comment(row, dek) for row in rows)
