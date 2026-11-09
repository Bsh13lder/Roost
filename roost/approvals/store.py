"""``ApprovalStore``: the Ask cards (schema v23 ``approval_cards``), the stuck store's shape.

``steps`` and ``request`` are user content, ``enc:v2`` under ``approval_cards:steps`` and
``approval_cards:request``; ids, kind, state, flags and times stay plaintext. Every per-user query
has ``user_id`` in its ``WHERE``, so another user's card id reads as "no such card".

One open card per bot: ``open`` closes an older open card as ``expired`` first, in the same
transaction, and the partial unique index refuses a second open row. State changes are guarded
``UPDATE ... RETURNING`` statements, so of two presses on one card exactly one wins."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence
from uuid import uuid4

import aiosqlite

from roost.approvals.models import (
    ApprovalCard, ApprovalDraft, CardState, steps_from_json, steps_json,
)
from roost.config import RoostConfig
from roost.crypto.encryption import decrypt_field, encrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session

_COLUMNS = (
    "id, user_id, bot_id, thread_id, work_item_id, kind, state, steps, request, tainted, session_offer, "
    "answer_item_id, created_at, closed_at"
)
_LIST_LIMIT = 200
_CLOSING = frozenset({CardState.APPROVED, CardState.DECLINED, CardState.EDITED, CardState.FAILED,
                      CardState.EXPIRED})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"approval_cards:{column}")


def _row_to_card(row: aiosqlite.Row, dek: bytes) -> ApprovalCard:
    user_id = row["user_id"]
    return ApprovalCard(
        id=row["id"], user_id=user_id, bot_id=row["bot_id"], thread_id=row["thread_id"],
        work_item_id=row["work_item_id"], kind=row["kind"], state=CardState(row["state"]),
        steps=steps_from_json(decrypt_field(row["steps"], dek, _aad(user_id, "steps"), fallback="[]") or "[]"),
        request=decrypt_field(row["request"], dek, _aad(user_id, "request"), fallback="") or "",
        tainted=bool(row["tainted"]), session_offer=bool(row["session_offer"]),
        answer_item_id=row["answer_item_id"], created_at=row["created_at"], closed_at=row["closed_at"],
    )


class ApprovalStore:
    def __init__(self, config: RoostConfig) -> None:
        self._config = config

    async def open(self, user_id: str, draft: ApprovalDraft) -> ApprovalCard:
        """Open a card for ``draft.bot_id``; an older open card of that bot becomes ``expired`` first.
        Raises ``CardTooBig`` when the steps do not fit, ``ValueError`` when the bot or chat is gone."""
        dek = await get_user_dek(self._config, user_id)
        sealed_steps = encrypt(steps_json(draft.steps), dek, _aad(user_id, "steps"))
        now = _now_iso()
        card_id = str(uuid4())
        async with db_session(self._config) as db:
            try:
                await db.execute(
                    "UPDATE approval_cards SET state = 'expired', closed_at = ? "
                    "WHERE user_id = ? AND bot_id = ? AND state = 'open'", (now, user_id, draft.bot_id))
                await db.execute(
                    "INSERT INTO approval_cards (id, user_id, bot_id, thread_id, work_item_id, kind, state, steps, "
                    "request, tainted, session_offer, created_at) VALUES (?,?,?,?,?,?,'open',?,?,?,?,?)",
                    (card_id, user_id, draft.bot_id, draft.thread_id, draft.work_item_id, draft.kind, sealed_steps,
                     encrypt(draft.request, dek, _aad(user_id, "request")), int(draft.tainted),
                     int(draft.session_offer), now))
                await db.commit()
            except aiosqlite.IntegrityError:
                await db.rollback()
                raise ValueError("Can't open an Ask card: that bot or its chat no longer exists.") from None
        card = await self.get(user_id, card_id)
        if card is None:
            raise ValueError("Can't open an Ask card.")
        return card

    async def get(self, user_id: str, card_id: str) -> ApprovalCard | None:
        found = await self._select(user_id, "WHERE id = ? AND user_id = ?", (card_id, user_id))
        return found[0] if found else None

    async def list_open(self, user_id: str) -> tuple[ApprovalCard, ...]:
        return await self._select(
            user_id, "WHERE user_id = ? AND state = 'open' ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (user_id, _LIST_LIMIT))

    async def open_in_thread(self, user_id: str, thread_id: str, limit: int = 2) -> tuple[ApprovalCard, ...]:
        """Up to ``limit`` open cards waiting in one chat (W1 needs to know whether exactly one waits)."""
        return await self._select(
            user_id, "WHERE user_id = ? AND thread_id = ? AND state = 'open' ORDER BY created_at DESC LIMIT ?",
            (user_id, thread_id, limit))

    async def open_for_bot(self, user_id: str, bot_id: str) -> ApprovalCard | None:
        found = await self._select(
            user_id, "WHERE user_id = ? AND bot_id = ? AND state = 'open' LIMIT 1", (user_id, bot_id))
        return found[0] if found else None

    async def close(self, user_id: str, card_id: str, state: CardState,
                    answer_item_id: str | None = None) -> ApprovalCard | None:
        """Close an open card as ``state``. ``None`` when it is not the user's or another press won."""
        target = CardState(state)
        if target not in _CLOSING:
            raise ValueError(f"An Ask card can't be closed as {target.value!r}.")
        return await self._transition(
            user_id, card_id, CardState.OPEN, "state = ?, answer_item_id = ?, closed_at = ?",
            (target.value, answer_item_id, _now_iso()))

    async def mark_failed(self, user_id: str, card_id: str) -> ApprovalCard | None:
        """The approved step did not run: ``approved`` becomes ``failed``."""
        return await self._transition(user_id, card_id, CardState.APPROVED, "state = ?",
                                      (CardState.FAILED.value,))

    async def card_for_answer(self, user_id: str, item_id: str) -> ApprovalCard | None:
        found = await self._select(user_id, "WHERE user_id = ? AND answer_item_id = ? LIMIT 1", (user_id, item_id))
        return found[0] if found else None

    async def declined_for_items(self, user_id: str, thread_id: str,
                                 item_ids: Sequence[str]) -> tuple[ApprovalCard, ...]:
        """Lessons (declined signal): this thread's cards you said No to, parked on or answered by these items."""
        ids = tuple(dict.fromkeys(item_ids))
        if not ids:
            return ()
        marks = ",".join("?" * len(ids))
        return await self._select(
            user_id, f"WHERE user_id = ? AND thread_id = ? AND state = ? AND (work_item_id IN ({marks}) "
                     f"OR answer_item_id IN ({marks})) ORDER BY created_at, rowid",
            (user_id, thread_id, CardState.DECLINED.value, *ids, *ids))

    async def open_bots(self) -> tuple[tuple[str, str], ...]:
        """Boot only, across users: every (user_id, bot_id) with an open card."""
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                "SELECT user_id, bot_id FROM approval_cards WHERE state = 'open' ORDER BY created_at, rowid",
            )).fetchall()
        return tuple((row["user_id"], row["bot_id"]) for row in rows)

    async def _transition(self, user_id: str, card_id: str, from_state: CardState, assignments: str,
                          params: tuple) -> ApprovalCard | None:
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE approval_cards SET {assignments} WHERE id = ? AND user_id = ? AND state = ? "
                f"RETURNING {_COLUMNS}", (*params, card_id, user_id, from_state.value))
            rows = await cursor.fetchall()
            await db.commit()
        found = await self._cards(user_id, rows)
        return found[0] if found else None

    async def _select(self, user_id: str, where: str, params: tuple) -> tuple[ApprovalCard, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_COLUMNS} FROM approval_cards {where}", params)).fetchall()
        return await self._cards(user_id, rows)

    async def _cards(self, user_id: str, rows: Sequence[aiosqlite.Row]) -> tuple[ApprovalCard, ...]:
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_card(row, dek) for row in rows)
