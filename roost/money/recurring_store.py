"""``RecurringStore`` — the user's repeating-expense rules (Task 12, design §5).

- ``amount``, ``description``, ``vendor`` and ``cadence`` are ``enc:v2`` with ``money_recurring:<column>``
  as the AAD (the same ones the LazyClaw migration wrote); the days are plaintext.
- Every query names ``user_id``. Deleting a rule is soft; the charges it made stay.
- ``catch_up`` is the lazy engine: in ONE session (one transaction, one connection lock) it makes every
  missed charge of every due rule, once. A rule's ``next_due`` moves first (compare-and-swap on its old value),
  and the unique index on (user, rule, occurrence) makes a charge exist once even across processes: a charge
  the user voided or deleted is a row that still exists, so it is never made again."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Sequence
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.constants import PROJECT_STATUSES, RECURRING_CATCH_UP_MAX
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.money.amounts import amount_text
from roost.money.expense_store import ExpenseStore
from roost.money.models import EXPENSE_POSTED, Expense
from roost.money.recurring import Recurring, next_occurrence, occurrences
from roost.records.project_link import require_project

_COLUMNS = ("id", "user_id", "project_id", "amount", "currency", "description", "vendor", "cadence", "anchor_day",
            "next_due", "ends_on", "created_at", "updated_at", "created_by_bot", "tainted")
_SELECT = ", ".join(_COLUMNS)
_SECRET = frozenset({"description", "vendor", "cadence"})
_PATCHABLE = frozenset({"project_id", "amount", "description", "vendor", "ends_on"})
_SHOWN = "deleted_at IS NULL"
_ARCHIVED = PROJECT_STATUSES[1]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"money_recurring:{column}")


def _encode(rule: Recurring, column: str, dek: bytes) -> Any:
    if column == "amount":
        return encrypt_field(amount_text(rule.amount), dek, _aad(rule.user_id, column))
    if column in _SECRET:
        return encrypt_field(getattr(rule, column), dek, _aad(rule.user_id, column))
    if column == "tainted":
        return int(rule.tainted)
    return getattr(rule, column)


def _decode(row: aiosqlite.Row, dek: bytes) -> Recurring:
    user_id = row["user_id"]

    def text(column: str) -> str | None:
        return decrypt_field(row[column], dek, _aad(user_id, column))

    return Recurring(
        id=row["id"], user_id=user_id, project_id=row["project_id"], amount=Decimal(text("amount") or "0"),
        currency=row["currency"], description=text("description"), vendor=text("vendor"),
        cadence=text("cadence") or "", anchor_day=row["anchor_day"][:10], next_due=row["next_due"][:10],
        ends_on=None if row["ends_on"] is None else row["ends_on"][:10], created_at=row["created_at"],
        updated_at=row["updated_at"], created_by_bot=row["created_by_bot"], tainted=bool(row["tainted"]),
    )


class RecurringStore:
    def __init__(self, config: Config, expenses: ExpenseStore) -> None:
        self._config = config
        self._expenses = expenses

    async def add(self, rule: Recurring) -> Recurring:
        """Insert a rule built by the service. The project is checked in the same session (``ValueError``)."""
        dek = await get_user_dek(self._config, rule.user_id)
        async with db_session(self._config) as db:
            await require_project(db, rule.user_id, rule.project_id)
            await db.execute(f"INSERT INTO money_recurring ({_SELECT}) VALUES ({','.join('?' * len(_COLUMNS))})",
                             tuple(_encode(rule, column, dek) for column in _COLUMNS))
            await db.commit()
        return rule

    async def get(self, user_id: str, rule_id: str) -> Recurring | None:
        found = await self._select(user_id, f"WHERE id = ? AND user_id = ? AND {_SHOWN}", (rule_id, user_id))
        return found[0] if found else None

    async def list(self, user_id: str, project_id: str | None = None) -> tuple[Recurring, ...]:
        """The user's live rules, soonest ``next_due`` first, optionally one project's."""
        where = f"WHERE user_id = ? AND {_SHOWN}" + ("" if project_id is None else " AND project_id = ?")
        params = (user_id,) if project_id is None else (user_id, project_id)
        return await self._select(user_id, f"{where} ORDER BY next_due, created_at", params)

    async def update(self, user_id: str, rule_id: str, changes: Mapping[str, Any]) -> Recurring | None:
        """Write only the changed columns. ``None``: no such rule (or deleted meanwhile)."""
        unknown = sorted(set(changes) - _PATCHABLE)
        if unknown:
            raise ValueError(f"A repeating expense has no field {', '.join(unknown)}.")
        current = await self.get(user_id, rule_id)
        if current is None:
            return None
        updated = replace(current, **dict(changes), updated_at=_now_iso())
        dek = await get_user_dek(self._config, user_id)
        columns = (*(column for column in _COLUMNS if column in changes), "updated_at")
        assignments = ", ".join(f"{column} = ?" for column in columns)
        async with db_session(self._config) as db:
            if "project_id" in changes:
                await require_project(db, user_id, updated.project_id)
            cursor = await db.execute(
                f"UPDATE money_recurring SET {assignments} WHERE id = ? AND user_id = ? AND {_SHOWN}",
                (*(_encode(updated, column, dek) for column in columns), rule_id, user_id))
            await db.commit()
        return updated if cursor.rowcount else None

    async def delete(self, user_id: str, rule_id: str) -> bool:
        return await self._soft_delete(user_id, "id = ?", rule_id) > 0

    async def delete_for_project(self, user_id: str, project_id: str) -> int:
        """A deleted project takes its rules with it (their past charges moved to General with the others)."""
        return await self._soft_delete(user_id, "project_id = ?", project_id)

    async def catch_up(self, user_id: str, today: date) -> tuple[str, ...]:
        """Make every missed charge of this user's due rules, once; returns the ids of the rules that made some.

        - A rule whose project is archived is paused: nothing is made, and ``next_due`` jumps past today so a
          later unarchive does not back-fill the pause.
        - At most ``RECURRING_CATCH_UP_MAX`` charges per rule per call; the rest come on the next read.
        - A rule past its ``ends_on`` is not selected."""
        dek = await get_user_dek(self._config, user_id)      # before the session: it reads the database too
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {', '.join('r.' + column for column in _COLUMNS)}, p.status AS project_status "
                "FROM money_recurring r JOIN money_projects p "
                "ON p.id = r.project_id AND p.user_id = r.user_id AND p.deleted_at IS NULL "
                "WHERE r.user_id = ? AND r.deleted_at IS NULL AND r.next_due <= ? "
                "AND (r.ends_on IS NULL OR r.next_due <= r.ends_on) ORDER BY r.next_due, r.id",
                (user_id, today.isoformat()))).fetchall()
            if not rows:
                return ()
            made: list[str] = []
            try:
                for row in rows:
                    rule = _decode(row, dek)
                    if row["project_status"] == _ARCHIVED:
                        await self._skip_pause(db, rule, today)
                    elif await self._make_due(db, rule, today, dek):
                        made.append(rule.id)
                await db.commit()
            except BaseException:
                await db.rollback()         # a pooled connection: never leave a half-done catch-up behind
                raise
        return tuple(made)

    async def _make_due(self, db: aiosqlite.Connection, rule: Recurring, today: date, dek: bytes) -> bool:
        days = occurrences(rule, today, RECURRING_CATCH_UP_MAX)
        if not days:
            return False
        following = next_occurrence(rule.cadence, date.fromisoformat(rule.anchor_day), days[-1])
        moved = await db.execute(
            "UPDATE money_recurring SET next_due = ?, updated_at = ? "
            "WHERE id = ? AND user_id = ? AND next_due = ? AND deleted_at IS NULL",
            (following.isoformat(), _now_iso(), rule.id, rule.user_id, rule.next_due))
        if moved.rowcount == 0:
            return False                    # another reader moved it first: they make these charges
        made = 0
        for day in days:
            made += await ExpenseStore.insert_once(db, _charge(rule, day), dek)
        return made > 0

    @staticmethod
    async def _skip_pause(db: aiosqlite.Connection, rule: Recurring, today: date) -> None:
        following = next_occurrence(rule.cadence, date.fromisoformat(rule.anchor_day), today)
        await db.execute("UPDATE money_recurring SET next_due = ?, updated_at = ? "
                         "WHERE id = ? AND user_id = ? AND next_due = ? AND deleted_at IS NULL",
                         (following.isoformat(), _now_iso(), rule.id, rule.user_id, rule.next_due))

    async def _soft_delete(self, user_id: str, condition: str, value: str) -> int:
        now = _now_iso()
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE money_recurring SET deleted_at = ?, updated_at = ? WHERE user_id = ? AND {condition} "
                f"AND {_SHOWN}", (now, now, user_id, value))
            await db.commit()
        return cursor.rowcount

    async def _select(self, user_id: str, where: str, params: Sequence[Any]) -> tuple[Recurring, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_SELECT} FROM money_recurring {where}", tuple(params))).fetchall()
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_decode(row, dek) for row in rows)


def _charge(rule: Recurring, day: date) -> Expense:
    now = _now_iso()
    return Expense(
        id=str(uuid4()), user_id=rule.user_id, project_id=rule.project_id, amount=rule.amount,
        currency=rule.currency, description=rule.description, vendor=rule.vendor, spent_at=day.isoformat(),
        status=EXPENSE_POSTED, created_at=now, updated_at=now, created_by_bot=rule.created_by_bot,
        tainted=rule.tainted, recurring_id=rule.id, occurrence=day.isoformat(),
    )
