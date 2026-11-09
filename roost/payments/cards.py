"""``CardStore``: Vault: cards (P6). Number, expiry, name, brand and last 4 are ``enc:v2`` under
``payment_cards:<column>``; ``number_key`` is a keyed HMAC of the number, so one row per card per user and the number
never sits in plaintext. The security code is never stored. Every query names ``user_id``."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.payments.checks import brand_of

PAYMENT_CARDS_MAX: Final = 10
_KEY_LABEL: Final = b"roost:payment-card-number:v1"
_SEALED: Final = ("number", "exp", "name", "brand", "last4")


class CardNotFound(LookupError):
    """No such card for this user."""


class CardsFull(RuntimeError):
    """The user already keeps ``PAYMENT_CARDS_MAX`` cards."""


@dataclass(frozen=True)
class NewCard:
    number: str   # digits only, checked (``check_number``)
    exp: str      # MM/YY, checked (``check_exp``)
    name: str


@dataclass(frozen=True)
class SavedCard:
    """What a list shows: never the number or expiry."""

    id: str
    brand: str
    last4: str
    created_at: str
    last_used_at: str | None


@dataclass(frozen=True)
class FullCard:
    """Only for the fill; never returned by a route."""

    id: str
    number: str
    exp: str
    name: str
    brand: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def number_key(dek: bytes, number: str) -> str:
    sub = hmac.new(dek, _KEY_LABEL, hashlib.sha256).digest()
    return hmac.new(sub, number.encode("utf-8"), hashlib.sha256).hexdigest()


def _seal(dek: bytes, user_id: str, column: str, value: str) -> str:
    sealed = encrypt_field(value, dek, user_aad(user_id, f"payment_cards:{column}"))
    if sealed is None:
        raise ValueError("a card value did not seal")
    return sealed


def _open(dek: bytes, row: aiosqlite.Row, column: str) -> str:
    return decrypt_field(row[column], dek, user_aad(row["user_id"], f"payment_cards:{column}")) or ""


class CardStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def save(self, user_id: str, card: NewCard) -> SavedCard:
        """Save a card, or refresh the expiry and name of the same card. ``CardsFull`` past the cap."""
        dek = await get_user_dek(self._config, user_id)
        values = {"number": card.number, "exp": card.exp, "name": card.name, "brand": brand_of(card.number),
                  "last4": card.number[-4:]}
        sealed = {column: _seal(dek, user_id, column, values[column]) for column in _SEALED}
        key, now = number_key(dek, card.number), _now_iso()
        async with db_session(self._config) as db:
            await db.execute("BEGIN IMMEDIATE")          # the room check and the insert are one step
            try:
                card_id = await self._write(db, user_id, key, sealed, now)
                await db.commit()
            except BaseException:
                await db.rollback()
                raise
        return next(c for c in await self.list(user_id) if c.id == card_id)

    async def _write(self, db: aiosqlite.Connection, user_id: str, key: str, sealed: dict[str, str], now: str) -> str:
        found = await (await db.execute("SELECT id FROM payment_cards WHERE user_id = ? AND number_key = ?",
                                        (user_id, key))).fetchone()
        if found is not None:
            await db.execute("UPDATE payment_cards SET exp = ?, name = ? WHERE id = ? AND user_id = ?",
                             (sealed["exp"], sealed["name"], found["id"], user_id))
            return str(found["id"])
        await self._require_room(db, user_id)
        card_id = str(uuid4())
        await db.execute(
            "INSERT INTO payment_cards (id, user_id, number, number_key, exp, name, brand, last4, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (card_id, user_id, sealed["number"], key, sealed["exp"], sealed["name"], sealed["brand"],
             sealed["last4"], now))
        return card_id

    async def list(self, user_id: str) -> tuple[SavedCard, ...]:
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                "SELECT id, user_id, brand, last4, created_at, last_used_at FROM payment_cards WHERE user_id = ?"
                " ORDER BY created_at", (user_id,))).fetchall()
        return tuple(SavedCard(id=r["id"], brand=_open(dek, r, "brand"), last4=_open(dek, r, "last4"),
                               created_at=r["created_at"], last_used_at=r["last_used_at"]) for r in rows)

    async def secret(self, user_id: str, card_id: str) -> FullCard:
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            row = await (await db.execute("SELECT * FROM payment_cards WHERE id = ? AND user_id = ?",
                                          (card_id, user_id))).fetchone()
        if row is None:
            raise CardNotFound(card_id)
        return FullCard(id=row["id"], number=_open(dek, row, "number"), exp=_open(dek, row, "exp"),
                        name=_open(dek, row, "name"), brand=_open(dek, row, "brand"))

    async def delete(self, user_id: str, card_id: str) -> None:
        async with db_session(self._config) as db:
            gone = await db.execute("DELETE FROM payment_cards WHERE id = ? AND user_id = ?", (card_id, user_id))
            await db.commit()
        if gone.rowcount == 0:
            raise CardNotFound(card_id)

    async def mark_used(self, user_id: str, card_id: str) -> None:
        async with db_session(self._config) as db:
            await db.execute("UPDATE payment_cards SET last_used_at = ? WHERE id = ? AND user_id = ?",
                             (_now_iso(), card_id, user_id))
            await db.commit()

    @staticmethod
    async def _require_room(db: aiosqlite.Connection, user_id: str) -> None:
        row = await (await db.execute("SELECT COUNT(*) FROM payment_cards WHERE user_id = ?", (user_id,))).fetchone()
        if row is not None and int(row[0]) >= PAYMENT_CARDS_MAX:
            raise CardsFull()
