"""``QuestionStore``: the question book (schema v25 ``bot_questions``).

``question``, ``default_choice``, ``why`` and ``answer`` are user content, ``enc:v2`` under
``bot_questions:<column>``; ids, state, flags and times stay plaintext. Every query names ``user_id``. A state
change is a guarded ``UPDATE``, so of two presses on one question exactly one wins."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

import aiosqlite

from roost.config import RoostConfig
from roost.crypto.encryption import decrypt_field, encrypt, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.routines.models import Clock
from roost.routines.runs import iso, parse_iso, utc_now

_COLUMNS = ("id, user_id, bot_id, routine_id, thread_id, question, default_choice, why, answer, tainted, state, "
            "created_at, answered_at")
_LIST_LIMIT = 200


@dataclass(frozen=True)
class Question:
    id: str
    user_id: str
    bot_id: str
    routine_id: str | None
    thread_id: str
    question: str
    default_choice: str
    why: str | None
    answer: str | None
    tainted: bool
    state: str                    # open | answered | dismissed
    created_at: datetime
    answered_at: datetime | None


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"bot_questions:{column}")


def _plain(row: aiosqlite.Row, column: str, dek: bytes) -> str | None:
    return decrypt_field(row[column], dek, _aad(row["user_id"], column), fallback="") if row[column] else None


def _to_question(row: aiosqlite.Row, dek: bytes) -> Question:
    return Question(
        id=row["id"], user_id=row["user_id"], bot_id=row["bot_id"], routine_id=row["routine_id"],
        thread_id=row["thread_id"], question=_plain(row, "question", dek) or "",
        default_choice=_plain(row, "default_choice", dek) or "", why=_plain(row, "why", dek) or None,
        answer=_plain(row, "answer", dek), tainted=bool(row["tainted"]), state=row["state"],
        created_at=parse_iso(row["created_at"]), answered_at=parse_iso(row["answered_at"]))


class QuestionStore:
    def __init__(self, config: RoostConfig, *, clock: Clock = utc_now) -> None:
        self._config = config
        self._clock = clock

    async def note(
        self, user_id: str, bot_id: str, thread_id: str, question: str, default_choice: str, why: str | None,
        *, routine_id: str | None, tainted: bool,
    ) -> Question:
        dek = await get_user_dek(self._config, user_id)
        question_id = str(uuid4())
        async with db_session(self._config) as db:
            await db.execute(
                f"INSERT INTO bot_questions ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,NULL,?,'open',?,NULL)",
                (question_id, user_id, bot_id, routine_id, thread_id, encrypt(question, dek, _aad(user_id, "question")),
                 encrypt(default_choice, dek, _aad(user_id, "default_choice")),
                 encrypt_field(why, dek, _aad(user_id, "why")), int(tainted), iso(self._clock())))
            await db.commit()
        found = await self.get(user_id, question_id)
        assert found is not None
        return found

    async def get(self, user_id: str, question_id: str) -> Question | None:
        found = await self._select(user_id, "WHERE id = ? AND user_id = ?", (question_id, user_id))
        return found[0] if found else None

    async def list(self, user_id: str, *, state: str = "open", bot_id: str | None = None) -> tuple[Question, ...]:
        where, params = "WHERE user_id = ? AND state = ?", [user_id, state]
        if bot_id is not None:
            where, params = where + " AND bot_id = ?", [*params, bot_id]
        return await self._select(user_id, f"{where} ORDER BY created_at DESC, rowid DESC LIMIT ?",
                                  (*params, _LIST_LIMIT))

    async def count_open(self, user_id: str, bot_id: str) -> int:
        async with db_session(self._config) as db:
            row = await (await db.execute(
                "SELECT COUNT(*) FROM bot_questions WHERE user_id = ? AND bot_id = ? AND state = 'open'",
                (user_id, bot_id))).fetchone()
        return int(row[0])

    async def answer(self, user_id: str, question_id: str, text: str) -> Question | None:
        """Seal ``text`` and close an open question as answered. ``None`` when not the user's or already closed."""
        dek = await get_user_dek(self._config, user_id)
        return await self._close(user_id, question_id, "answered", "answer = ?, ",
                                 (encrypt(text, dek, _aad(user_id, "answer")),))

    async def dismiss(self, user_id: str, question_id: str) -> Question | None:
        return await self._close(user_id, question_id, "dismissed", "", ())

    async def answered_for_routine(self, user_id: str, routine_id: str, limit: int) -> tuple[Question, ...]:
        return await self._select(
            user_id, "WHERE user_id = ? AND routine_id = ? AND state = 'answered' "
            "ORDER BY answered_at DESC, rowid DESC LIMIT ?", (user_id, routine_id, limit))

    async def _close(self, user_id: str, question_id: str, state: str, extra: str, extra_params: tuple) -> Question | None:
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE bot_questions SET {extra}state = ?, answered_at = ? "
                "WHERE id = ? AND user_id = ? AND state = 'open'",
                (*extra_params, state, iso(self._clock()), question_id, user_id))
            await db.commit()
            changed = cursor.rowcount == 1
        return await self.get(user_id, question_id) if changed else None

    async def _select(self, user_id: str, where: str, params: tuple) -> tuple[Question, ...]:
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_COLUMNS} FROM bot_questions {where}", params)).fetchall()
        return tuple(_to_question(row, dek) for row in rows)
