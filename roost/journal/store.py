"""``JournalStore`` — one sealed Markdown day per bot (``bot_journals``, schema v30).

``content`` is ``enc:v2`` under ``bot_journals:content``; the day, the taint bit and the revision are plaintext.
Every statement names ``user_id`` in its ``WHERE``, and a day is only ever made for one of the user's own bots,
so another user's ids find and write nothing. Each append is a compare-and-swap on ``revision``."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.journal.models import JournalDay

_COLUMNS = "id, user_id, bot_id, day, content, tainted, revision, created_at, updated_at"


def _aad(user_id: str) -> bytes:
    return user_aad(user_id, "bot_journals:content")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_day(row: aiosqlite.Row, dek: bytes) -> JournalDay:
    return JournalDay(
        id=row["id"], user_id=row["user_id"], bot_id=row["bot_id"], day=date.fromisoformat(row["day"]),
        content=decrypt_field(row["content"], dek, _aad(row["user_id"])) or "", tainted=bool(row["tainted"]),
        revision=row["revision"], created_at=row["created_at"], updated_at=row["updated_at"],
    )


class JournalStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def get(self, user_id: str, bot_id: str, day: date) -> JournalDay | None:
        found = await self._select(user_id, "WHERE user_id = ? AND bot_id = ? AND day = ?",
                                   (user_id, bot_id, day.isoformat()))
        return found[0] if found else None

    async def insert(self, user_id: str, bot_id: str, day: date, content: str, *, tainted: bool) -> JournalDay | None:
        """Make the day. ``None``: it already exists (a racing append made it first) or the bot is not the
        user's; nothing is written."""
        now = _now_iso()
        made = JournalDay(id=str(uuid4()), user_id=user_id, bot_id=bot_id, day=day, content=content,
                          tainted=tainted, revision=1, created_at=now, updated_at=now)
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"INSERT OR IGNORE INTO bot_journals ({_COLUMNS}) SELECT ?,?,?,?,?,?,?,?,? "
                "WHERE EXISTS (SELECT 1 FROM bots WHERE id = ? AND user_id = ?)",
                (made.id, user_id, bot_id, day.isoformat(), encrypt_field(content, dek, _aad(user_id)), int(tainted),
                 1, now, now, bot_id, user_id))
            await db.commit()
        return made if cursor.rowcount > 0 else None

    async def swap(self, current: JournalDay, content: str, *, tainted: bool) -> JournalDay | None:
        """Write ``content`` over ``current`` if nobody wrote in between; ``None`` when someone did."""
        now = _now_iso()
        dek = await get_user_dek(self._config, current.user_id)
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE bot_journals SET content = ?, tainted = ?, revision = revision + 1, updated_at = ? "
                "WHERE id = ? AND user_id = ? AND revision = ?",
                (encrypt_field(content, dek, _aad(current.user_id)), int(tainted), now, current.id,
                 current.user_id, current.revision))
            await db.commit()
        if cursor.rowcount == 0:
            return None
        return JournalDay(id=current.id, user_id=current.user_id, bot_id=current.bot_id, day=current.day,
                          content=content, tainted=tainted, revision=current.revision + 1,
                          created_at=current.created_at, updated_at=now)

    async def recent(self, user_id: str, bot_id: str, limit: int) -> tuple[JournalDay, ...]:
        """The bot's newest days first."""
        return await self._select(user_id, "WHERE user_id = ? AND bot_id = ? ORDER BY day DESC LIMIT ?",
                                  (user_id, bot_id, limit))

    async def newest(self, user_id: str, limit: int, *, bot_id: str | None = None) -> tuple[JournalDay, ...]:
        """Every bot's days (or one bot's), newest first: what a search reads."""
        if bot_id is not None:
            return await self.recent(user_id, bot_id, limit)
        return await self._select(user_id, "WHERE user_id = ? ORDER BY day DESC, bot_id LIMIT ?", (user_id, limit))

    async def since(self, user_id: str, first: date, limit: int) -> tuple[JournalDay, ...]:
        """Every bot's days from ``first`` on: what the vault export writes."""
        return await self._select(user_id, "WHERE user_id = ? AND day >= ? ORDER BY day, bot_id LIMIT ?",
                                  (user_id, first.isoformat(), limit))

    async def _select(self, user_id: str, where: str, params: tuple) -> tuple[JournalDay, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_COLUMNS} FROM bot_journals {where}", params)).fetchall()
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_day(row, dek) for row in rows)
