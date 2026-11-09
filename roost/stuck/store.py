"""``StuckStore`` — the Stuck cards (stuck flow §2, R6–R9; schema v12).

``url``, ``note`` and ``request`` are user content, ``enc:v2`` under
``stuck_cards:<column>``; ids, reason, state, flags and times stay plaintext.
Every per-user query has ``user_id`` in its ``WHERE``, so another user's card
id reads as "no such card". ``open_bots`` runs once at boot, across users,
like ``WorkQueue.bots_with_queued``.

One open card per bot: the partial unique index ``idx_stuck_cards_one_open``
refuses a second open row, and ``open`` then returns the card that is already
open. State changes are guarded ``UPDATE ... RETURNING`` statements, so of two
presses on one card exactly one wins; the other gets ``None``."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, get_args
from uuid import uuid4

import aiosqlite

from roost.config import RoostConfig
from roost.constants import SECRET_FIELD_KINDS, STUCK_LIST_LIMIT, STUCK_REQUEST_MAX_CHARS
from roost.crypto.encryption import decrypt_field, encrypt, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.desk.stuck import BlockReason
from roost.stuck.models import CardDraft, CardState, StuckCard

_COLUMNS = (
    "id, user_id, bot_id, thread_id, work_item_id, reason, url, note, request, suggest_main_browser, "
    "tainted, main_opened, state, answer_item_id, created_at, closed_at, sign_in, secret_field, replied"
)
_INSERT = (
    "INSERT INTO stuck_cards (id, user_id, bot_id, thread_id, work_item_id, reason, url, note, request, "
    "suggest_main_browser, tainted, state, created_at, sign_in, secret_field) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)
_REASONS = frozenset(get_args(BlockReason))
_CLOSING_STATES = frozenset({CardState.CLEARED, CardState.GIVEN_UP, CardState.BLOCKED, CardState.REPLIED})
# v12's CHECK knows four states: a card you answered in the chat is stored as given_up with ``replied = 1`` (v38).
_STORED_AS = {CardState.REPLIED: CardState.GIVEN_UP}


def _state_of(row: aiosqlite.Row) -> CardState:
    return CardState.REPLIED if row["replied"] else CardState(row["state"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"stuck_cards:{column}")


def _field(value: object) -> str | None:
    """A stored field kind, or None for anything else (a plain card)."""
    return value if isinstance(value, str) and value in SECRET_FIELD_KINDS else None


def _row_to_card(row: aiosqlite.Row, dek: bytes) -> StuckCard:
    user_id = row["user_id"]
    return StuckCard(
        id=row["id"], user_id=user_id, bot_id=row["bot_id"], thread_id=row["thread_id"],
        work_item_id=row["work_item_id"], reason=row["reason"],
        # An address that can't be read is no address: the card can't open it anywhere.
        url=decrypt_field(row["url"], dek, _aad(user_id, "url"), fallback="") or "",
        note=decrypt_field(row["note"], dek, _aad(user_id, "note")) or "",
        request=decrypt_field(row["request"], dek, _aad(user_id, "request")) or "",
        suggest_main_browser=bool(row["suggest_main_browser"]), tainted=bool(row["tainted"]),
        main_opened=bool(row["main_opened"]), state=_state_of(row),
        answer_item_id=row["answer_item_id"], created_at=row["created_at"], closed_at=row["closed_at"],
        sign_in=bool(row["sign_in"]), secret_field=_field(row["secret_field"]),
    )


def _new_card(user_id: str, draft: CardDraft) -> StuckCard:
    block = draft.block
    if block.reason not in _REASONS:
        raise ValueError(f"Unknown Stuck reason: {block.reason!r}.")
    return StuckCard(
        id=str(uuid4()), user_id=user_id, bot_id=draft.bot_id, thread_id=draft.thread_id,
        work_item_id=draft.work_item_id, reason=block.reason, url=block.url, note=block.note,
        request=draft.request[:STUCK_REQUEST_MAX_CHARS], suggest_main_browser=block.suggest_main_browser,
        tainted=draft.tainted, main_opened=False, state=CardState.OPEN, answer_item_id=None,
        created_at=_now_iso(), closed_at=None, sign_in=draft.sign_in,
        secret_field=block.field if draft.sign_in and block.field in SECRET_FIELD_KINDS else None,
    )


def _insert_params(card: StuckCard, dek: bytes) -> tuple:
    user_id = card.user_id
    return (
        card.id, user_id, card.bot_id, card.thread_id, card.work_item_id, card.reason,
        encrypt(card.url, dek, _aad(user_id, "url")),
        encrypt_field(card.note or None, dek, _aad(user_id, "note")),
        encrypt(card.request, dek, _aad(user_id, "request")),
        int(card.suggest_main_browser), int(card.tainted), card.state.value, card.created_at, int(card.sign_in),
        card.secret_field,
    )


class StuckStore:
    def __init__(self, config: RoostConfig) -> None:
        self._config = config

    async def open(self, user_id: str, draft: CardDraft) -> StuckCard:
        """Open a card for ``draft.bot_id``. A bot has at most one open card:
        when one is open already, that card comes back and nothing is written."""
        card = _new_card(user_id, draft)
        dek = await get_user_dek(self._config, user_id)
        if await self._insert(card, dek):
            return card
        existing = await self.open_for_bot(user_id, draft.bot_id)
        if existing is None:
            raise ValueError("Can't open a Stuck card: that bot or its chat no longer exists.")
        return existing

    async def get(self, user_id: str, card_id: str) -> StuckCard | None:
        found = await self._select(user_id, "WHERE id = ? AND user_id = ?", (card_id, user_id))
        return found[0] if found else None

    async def list_open(self, user_id: str) -> tuple[StuckCard, ...]:
        """The user's open cards, newest first (Home's My turn, ``GET /api/stuck``)."""
        return await self._select(
            user_id, "WHERE user_id = ? AND state = 'open' ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (user_id, STUCK_LIST_LIMIT),
        )

    async def open_for_bot(self, user_id: str, bot_id: str) -> StuckCard | None:
        found = await self._select(
            user_id, "WHERE user_id = ? AND bot_id = ? AND state = 'open' LIMIT 1", (user_id, bot_id),
        )
        return found[0] if found else None

    async def close(self, user_id: str, card_id: str, state: CardState, *,
                    answer_item_id: str | None = None) -> StuckCard | None:
        """Close an open card as ``state``. ``None`` when the card is not the
        user's or is no longer open (a second press, another tab)."""
        target = CardState(state)
        if target not in _CLOSING_STATES:
            raise ValueError(f"A Stuck card can't be closed as {target.value!r}.")
        stored = _STORED_AS.get(target, target)
        return await self._transition(
            user_id, card_id, CardState.OPEN, "state = ?, replied = ?, answer_item_id = ?, closed_at = ?",
            (stored.value, int(target is CardState.REPLIED), answer_item_id, _now_iso()),
        )

    async def mark_blocked(self, user_id: str, card_id: str) -> StuckCard | None:
        """Rung 4: the continue run this card queued was stopped again. Only from ``cleared``."""
        return await self._transition(user_id, card_id, CardState.CLEARED, "state = ?, closed_at = ?",
                                      (CardState.BLOCKED.value, _now_iso()))

    async def mark_main_opened(self, user_id: str, card_id: str) -> StuckCard | None:
        """The user opened the card's page in their main Brave. Only while open."""
        return await self._transition(user_id, card_id, CardState.OPEN, "main_opened = 1", ())

    async def card_for_answer(self, user_id: str, item_id: str) -> StuckCard | None:
        """The card whose ``/clear`` queued the ``card_answer`` item ``item_id``."""
        found = await self._select(
            user_id, "WHERE user_id = ? AND answer_item_id = ? LIMIT 1", (user_id, item_id),
        )
        return found[0] if found else None

    async def open_bots(self) -> tuple[tuple[str, str], ...]:
        """Boot only, across users: every (user_id, bot_id) with an open card."""
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                "SELECT user_id, bot_id FROM stuck_cards WHERE state = 'open' ORDER BY created_at, rowid",
            )).fetchall()
        return tuple((row["user_id"], row["bot_id"]) for row in rows)

    async def _insert(self, card: StuckCard, dek: bytes) -> bool:
        """False when the database refuses the row: the bot already has an
        open card, or the bot or chat is gone."""
        async with db_session(self._config) as db:
            try:
                await db.execute(_INSERT, _insert_params(card, dek))
                await db.commit()
            except aiosqlite.IntegrityError:
                await db.rollback()
                return False
        return True

    async def _transition(self, user_id: str, card_id: str, from_state: CardState,
                          assignments: str, params: tuple) -> StuckCard | None:
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE stuck_cards SET {assignments} WHERE id = ? AND user_id = ? AND state = ? "
                f"RETURNING {_COLUMNS}",
                (*params, card_id, user_id, from_state.value),
            )
            rows = await cursor.fetchall()
            await db.commit()
        found = await self._cards(user_id, rows)
        return found[0] if found else None

    async def _select(self, user_id: str, where: str, params: tuple) -> tuple[StuckCard, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_COLUMNS} FROM stuck_cards {where}", params)).fetchall()
        return await self._cards(user_id, rows)

    async def _cards(self, user_id: str, rows: Sequence[aiosqlite.Row]) -> tuple[StuckCard, ...]:
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_card(row, dek) for row in rows)
