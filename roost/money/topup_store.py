"""A project's budget history (``money_topups``, projects hub H4 and H5), for ``ProjectStore``.

Every change to a project's total budget writes one row here, in the same
transaction as the budget itself:

- ``credit``: a top-up, with an optional source ("Top-up");
- ``edit`` with a ``topup_id``: a change to that credit, holding the
  difference ("Top-up changed");
- ``edit`` with no ``topup_id``: the budget itself was set or cleared
  ("Budget set").

So while a budget is set, it equals the sum of the live rows. Undoing a credit
sets ``deleted_at`` on it and on its edits. Amounts and sources are ``enc:v2``
(AAD ``money_topups:amount`` / ``money_topups:source``). These functions run
on the caller's open ``db_session``: ``ProjectStore`` owns the transaction."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

import aiosqlite

from roost.crypto.encryption import decrypt_field, encrypt, encrypt_field, user_aad
from roost.money.amounts import CENT, amount_text
from roost.money.models import TOPUP_CREDIT, TOPUP_EDIT, TopUp

_COLUMNS = ("id, user_id, project_id, amount, currency, source, kind, topup_id, created_at, created_by_bot, "
            "tainted, deleted_at")
_ZERO = Decimal("0")

TOPUP_UNDONE_TEXT = "That top-up was undone already."
TAKEN_BACK_TEXT = "That top-up was already taken back when the budget was cleared."
BUDGET_CLEARED_TEXT = "The total budget is cleared, so its top-ups cannot change. Set a budget first."
BELOW_ZERO_TEXT = "That would take the total budget below 0."


class TopUpUndone(ValueError):
    """An undone top-up can be neither changed nor undone again (HTTP 409)."""


@dataclass(frozen=True)
class LedgerRow:
    """One row to write: which project, by how much, and why."""

    project_id: str
    amount: Decimal                   # signed for an edit
    currency: str
    kind: str                         # TOPUP_CREDIT or TOPUP_EDIT
    topup_id: str | None = None       # the credit an edit changes; None when the budget itself was set
    source: str | None = None
    created_by_bot: str | None = None
    tainted: bool = False


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"money_topups:{column}")


def _amount(row: aiosqlite.Row, dek: bytes) -> Decimal:
    return Decimal(decrypt_field(row["amount"], dek, _aad(row["user_id"], "amount")) or "0")


def row_to_topup(row: aiosqlite.Row, dek: bytes, *, taken_back: bool = False) -> TopUp:
    return TopUp(
        id=row["id"], project_id=row["project_id"], amount=_amount(row, dek), currency=row["currency"],
        source=decrypt_field(row["source"], dek, _aad(row["user_id"], "source")), kind=row["kind"],
        topup_id=row["topup_id"], undone=row["deleted_at"] is not None, created_at=row["created_at"],
        created_by_bot=row["created_by_bot"], tainted=bool(row["tainted"]), taken_back=taken_back,
    )


def moved_budget(budget: Decimal | None, change: Decimal) -> Decimal:
    """The total budget after a top-up changes or goes. Refused when it would
    fall below 0. A cleared budget is refused too, as a backstop: a top-up that
    outlived a clearing is already refused by ``taken_back``."""
    if budget is None:
        raise ValueError(BUDGET_CLEARED_TEXT)
    moved = budget + change
    if moved < _ZERO:
        raise ValueError(BELOW_ZERO_TEXT)
    return moved


async def add_row(db: aiosqlite.Connection, user_id: str, dek: bytes, entry: LedgerRow, now: str) -> TopUp:
    topup_id = str(uuid4())
    await db.execute(
        "INSERT INTO money_topups (id, user_id, project_id, amount, currency, source, kind, topup_id, created_at, "
        "updated_at, created_by_bot, tainted) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (topup_id, user_id, entry.project_id, encrypt(amount_text(entry.amount), dek, _aad(user_id, "amount")),
         entry.currency, encrypt_field(entry.source, dek, _aad(user_id, "source")), entry.kind, entry.topup_id,
         now, now, entry.created_by_bot, int(entry.tainted)),
    )
    return TopUp(
        id=topup_id, project_id=entry.project_id, amount=entry.amount.quantize(CENT), currency=entry.currency,
        source=entry.source, kind=entry.kind, topup_id=entry.topup_id, undone=False, created_at=now,
        created_by_bot=entry.created_by_bot, tainted=entry.tainted,
    )


async def credit(db: aiosqlite.Connection, user_id: str, dek: bytes, topup_id: str) -> TopUp | None:
    """The user's credit row with this id, undone or not. An ``edit`` row is never a top-up to change."""
    rows = await (await db.execute(
        f"SELECT {_COLUMNS} FROM money_topups WHERE id = ? AND user_id = ? AND kind = ?",
        (topup_id, user_id, TOPUP_CREDIT),
    )).fetchall()
    return row_to_topup(rows[0], dek) if rows else None


async def live_total(db: aiosqlite.Connection, user_id: str, dek: bytes, credit_id: str) -> Decimal:
    """What a credit adds to the budget now: its amount plus its live edits."""
    rows = await (await db.execute(
        "SELECT user_id, amount FROM money_topups WHERE user_id = ? AND (id = ? OR topup_id = ?) "
        "AND deleted_at IS NULL",
        (user_id, credit_id, credit_id),
    )).fetchall()
    return sum((_amount(row, dek) for row in rows), _ZERO)


def _is_budget_set(row: aiosqlite.Row) -> bool:
    """A "Budget set" row: an ``edit`` that is no top-up's (``topup_id`` is NULL)."""
    return row["kind"] == TOPUP_EDIT and row["topup_id"] is None


def _budget_after(rows: list[aiosqlite.Row], amounts: list[Decimal], index: int) -> Decimal:
    """What the total budget was just after ``rows[index]`` (rows oldest first):
    the rows made by then that were not undone by then. A top-up undone later
    still counts, which is why this reads ``deleted_at`` and does not just sum
    the rows that are live now."""
    made_at = rows[index]["created_at"]
    return sum((amounts[i] for i in range(index + 1)
                if rows[i]["deleted_at"] is None or rows[i]["deleted_at"] > made_at), _ZERO)


def taken_back_ids(rows: list[aiosqlite.Row], dek: bytes) -> frozenset[str]:
    """H5: the ids of the credits that a clearing of the total budget took back.
    ``rows`` is a project's whole history, newest first (``history_rows``). A
    "Budget set" row that left the budget at 0 is a clearing (a set row always
    leaves a budget above 0, ``parse_amount``). It holds the amount of every
    credit made before it (−budget), so those credits can be neither changed nor
    undone, even when a later "Budget set" gave the project a new total."""
    oldest_first = list(reversed(rows))
    amounts = [_amount(row, dek) for row in oldest_first]
    last_clearing = max((i for i, row in enumerate(oldest_first)       # 0: none, and nothing comes before row 0
                         if _is_budget_set(row) and _budget_after(oldest_first, amounts, i) == _ZERO), default=0)
    return frozenset(row["id"] for row in oldest_first[:last_clearing] if row["kind"] == TOPUP_CREDIT)


async def taken_back(db: aiosqlite.Connection, user_id: str, dek: bytes, credit: TopUp) -> bool:
    """Was this credit taken back by a clearing of the total budget (``taken_back_ids``)?"""
    return credit.id in taken_back_ids(await history_rows(db, user_id, credit.project_id), dek)


async def mark_undone(db: aiosqlite.Connection, user_id: str, credit_id: str, now: str) -> None:
    await db.execute(
        "UPDATE money_topups SET deleted_at = ?, updated_at = ? WHERE user_id = ? AND (id = ? OR topup_id = ?) "
        "AND deleted_at IS NULL",
        (now, now, user_id, credit_id, credit_id),
    )


async def history_rows(db: aiosqlite.Connection, user_id: str, project_id: str) -> list[aiosqlite.Row]:
    """Every row of the project's history, newest first, undone ones included."""
    return list(await (await db.execute(
        f"SELECT {_COLUMNS} FROM money_topups WHERE user_id = ? AND project_id = ? "
        "ORDER BY created_at DESC, rowid DESC",
        (user_id, project_id),
    )).fetchall())


async def set_currency(db: aiosqlite.Connection, user_id: str, project_id: str, currency: str, now: str) -> None:
    """A project with no money changed its currency (H7): its "Budget set" rows
    follow. Undone top-ups keep the currency they had."""
    await db.execute(
        "UPDATE money_topups SET currency = ?, updated_at = ? WHERE user_id = ? AND project_id = ? AND kind = ? "
        "AND topup_id IS NULL",
        (currency, now, user_id, project_id, TOPUP_EDIT),
    )
