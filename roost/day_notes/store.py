"""``DayNoteStore`` — the user's day notes, sealed (Board redesign G7).

``text`` is ``enc:v2`` under the AAD ``day_notes:text``. The day is plaintext (a date, not content).
Every statement names ``user_id`` in its ``WHERE``, so another user's id finds nothing."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.day_notes.models import DayNote, DayNoteDraft
from roost.db.connection import db_session

_COLUMNS = "id, user_id, day, author_kind, bot_id, text, created_at, tainted"


def _aad(user_id: str) -> bytes:
    return user_aad(user_id, "day_notes:text")


def _row_to_note(row: aiosqlite.Row, dek: bytes) -> DayNote:
    return DayNote(
        id=row["id"], user_id=row["user_id"], day=date.fromisoformat(row["day"]), author_kind=row["author_kind"],
        bot_id=row["bot_id"], text=decrypt_field(row["text"], dek, _aad(row["user_id"])) or "",
        created_at=row["created_at"], tainted=bool(row["tainted"]),
    )


class DayNoteStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def add(self, user_id: str, draft: DayNoteDraft, *, bot_id: str | None, tainted: bool,
                  max_per_day: int | None = None) -> DayNote | None:
        """Insert the note. With ``max_per_day`` the count and the insert are one statement, so
        concurrent adds never pass the cap; ``None`` back: the day is full (nothing written)."""
        note = DayNote(id=str(uuid4()), user_id=user_id, day=draft.day, author_kind="bot" if bot_id else "user",
                       bot_id=bot_id, text=draft.text, created_at=datetime.now(timezone.utc).isoformat(),
                       tainted=tainted)
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"INSERT INTO day_notes ({_COLUMNS}) SELECT ?,?,?,?,?,?,?,? "
                "WHERE ? IS NULL OR (SELECT COUNT(*) FROM day_notes WHERE user_id = ? AND day = ?) < ?",
                (note.id, user_id, note.day.isoformat(), note.author_kind, bot_id,
                 encrypt_field(note.text, dek, _aad(user_id)), note.created_at, int(tainted),
                 max_per_day, user_id, note.day.isoformat(), max_per_day),
            )
            await db.commit()
        return replace(note) if cursor.rowcount > 0 else None

    async def get(self, user_id: str, note_id: str) -> DayNote | None:
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            row = await (await db.execute(
                f"SELECT {_COLUMNS} FROM day_notes WHERE id = ? AND user_id = ?", (note_id, user_id))).fetchone()
        return _row_to_note(row, dek) if row else None

    async def list_range(self, user_id: str, first: date, last: date, limit: int) -> tuple[DayNote, ...]:
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {_COLUMNS} FROM day_notes WHERE user_id = ? AND day >= ? AND day <= ? "
                "ORDER BY day, created_at, id LIMIT ?",
                (user_id, first.isoformat(), last.isoformat(), limit))).fetchall()
        return tuple(_row_to_note(row, dek) for row in rows)

    async def count_on(self, user_id: str, day: date) -> int:
        async with db_session(self._config) as db:
            row = await (await db.execute(
                "SELECT COUNT(*) FROM day_notes WHERE user_id = ? AND day = ?", (user_id, day.isoformat()))).fetchone()
        return int(row[0])

    async def delete(self, user_id: str, note_id: str) -> bool:
        async with db_session(self._config) as db:
            cursor = await db.execute("DELETE FROM day_notes WHERE id = ? AND user_id = ?", (note_id, user_id))
            await db.commit()
        return cursor.rowcount > 0
