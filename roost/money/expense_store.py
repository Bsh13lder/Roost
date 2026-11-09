# SPDX-License-Identifier: MIT
# Adapted from LazyClaw lazyclaw/budgets/store.py @ 21e1002 (project_expenses names and semantics), for Roost
"""``ExpenseStore`` — the user's expenses.

- Amount, description and vendor are ``enc:v2``.
- ``spent_at`` (a local day), the currency, the status, the task and step
  links and the star stay plaintext, so a month is one indexed range query.
- A project the expense is filed under is checked in the same session as the write (``require_project``),
  so it can't be deleted in between.
- Deleting is soft, as in LazyClaw.
- A void expense is still shown (H6): every read here filters on
  ``deleted_at`` only. The sums leave voids out (``roost.projects.numbers.counted``)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Sequence
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.constants import TASK_EXPENSES_QUERY_CHUNK
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.money.amounts import amount_text
from roost.money.models import EXPENSE_POSTED, Expense, ExpenseDraft, ExpensePatch
from roost.money.months import month_bounds
from roost.records.imports import IMPORTED_FROM_LAZYCLAW, imported_ids
from roost.records.project_link import require_project
from roost.tags.codec import open_tags, seal_tags

_COLUMNS = ("id", "user_id", "project_id", "task_id", "step_id", "amount", "currency", "description", "vendor",
            "spent_at", "status", "is_favorite", "created_at", "updated_at", "created_by_bot", "tainted",
            "recurring_id", "occurrence", "kind", "tags")
_SELECT = ", ".join(_COLUMNS)
_MUTABLE = ("project_id", "task_id", "step_id", "amount", "currency", "description", "vendor", "spent_at", "status",
            "is_favorite")
_SHOWN = "deleted_at IS NULL"
_SECRET = frozenset({"description", "vendor"})
_FLAGS = frozenset({"is_favorite", "tainted"})
_NEWEST_FIRST = "ORDER BY spent_at DESC, created_at DESC"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"money_expenses:{column}")


def _encode(expense: Expense, column: str, dek: bytes) -> Any:
    if column == "amount":
        return encrypt_field(amount_text(expense.amount), dek, _aad(expense.user_id, column))
    if column in _SECRET:
        return encrypt_field(getattr(expense, column), dek, _aad(expense.user_id, column))
    if column in _FLAGS:
        return int(getattr(expense, column))
    if column == "tags":
        return seal_tags(expense.tags, dek, _aad(expense.user_id, column))
    return getattr(expense, column)


def _row_to_expense(row: aiosqlite.Row, dek: bytes) -> Expense:
    user_id = row["user_id"]

    def text(column: str) -> str | None:
        return decrypt_field(row[column], dek, _aad(user_id, column))

    return Expense(
        id=row["id"], user_id=user_id, project_id=row["project_id"], amount=Decimal(text("amount") or "0"),
        currency=row["currency"], description=text("description"), vendor=text("vendor"), spent_at=row["spent_at"],
        status=row["status"], created_at=row["created_at"], updated_at=row["updated_at"],
        created_by_bot=row["created_by_bot"], tainted=bool(row["tainted"]), task_id=row["task_id"],
        step_id=row["step_id"], is_favorite=bool(row["is_favorite"]), recurring_id=row["recurring_id"],
        occurrence=row["occurrence"], kind=row["kind"], tags=open_tags(row["tags"], dek, _aad(user_id, "tags")),
    )


class ExpenseStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    @property
    def config(self) -> Config:
        return self._config

    @staticmethod
    async def insert_once(db: aiosqlite.Connection, expense: Expense, dek: bytes) -> bool:
        """Insert in the caller's session unless the (rule, occurrence) pair already has a row: the unique index
        makes a repeating charge exist once, even a void or deleted one. ``True``: a row was written."""
        cursor = await db.execute(
            f"INSERT OR IGNORE INTO money_expenses ({_SELECT}) VALUES ({','.join('?' * len(_COLUMNS))})",
            tuple(_encode(expense, column, dek) for column in _COLUMNS))
        return cursor.rowcount > 0

    async def add(self, user_id: str, draft: ExpenseDraft, *, created_by_bot: str | None, tainted: bool) -> Expense:
        now = _now_iso()
        expense = Expense(
            id=str(uuid4()), user_id=user_id, project_id=draft.project_id, amount=draft.amount,
            currency=draft.currency, description=draft.description, vendor=draft.vendor, spent_at=draft.spent_at,
            status=EXPENSE_POSTED, created_at=now, updated_at=now, created_by_bot=created_by_bot, tainted=tainted,
            task_id=draft.task_id, step_id=draft.step_id, is_favorite=draft.is_favorite,
            recurring_id=draft.recurring_id, occurrence=draft.occurrence, kind=draft.kind, tags=draft.tags,
        )
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            await require_project(db, user_id, expense.project_id)    # same session: it can't be deleted before the insert
            await db.execute(f"INSERT INTO money_expenses ({_SELECT}) VALUES ({','.join('?' * len(_COLUMNS))})",
                             tuple(_encode(expense, column, dek) for column in _COLUMNS))
            await db.commit()
        return expense

    async def get(self, user_id: str, expense_id: str) -> Expense | None:
        found = await self._select(user_id, f"WHERE id = ? AND user_id = ? AND {_SHOWN}", (expense_id, user_id))
        return found[0] if found else None

    async def get_many(self, user_id: str, expense_ids: Sequence[str]) -> dict[str, Expense]:
        """This user's live expenses among ``expense_ids``, by id. An id that is not theirs, or is deleted or
        unknown, is simply missing: the caller compares the counts."""
        if not expense_ids:
            return {}
        marks = ",".join("?" * len(expense_ids))
        found = await self._select(user_id, f"WHERE user_id = ? AND id IN ({marks}) AND {_SHOWN}",
                                   (user_id, *expense_ids))
        return {expense.id: expense for expense in found}

    async def list_month(self, user_id: str, month: str) -> tuple[Expense, ...]:
        """The month's expenses, voids included; sum them with ``numbers.counted``."""
        first, following = month_bounds(month)
        return await self._select(
            user_id, f"WHERE user_id = ? AND {_SHOWN} AND spent_at >= ? AND spent_at < ? {_NEWEST_FIRST}",
            (user_id, first, following),
        )

    async def list_range(self, user_id: str, first: str, following: str, project_id: str | None = None,
                         limit: int | None = None) -> tuple[Expense, ...]:
        """Expenses spent on ``first <= day < following`` (ISO days), voids included, newest first; optionally one
        project's and at most ``limit``."""
        where = f"WHERE user_id = ? AND {_SHOWN} AND spent_at >= ? AND spent_at < ?"
        params: tuple = (user_id, first, following)
        if project_id is not None:
            where, params = f"{where} AND project_id = ?", (*params, project_id)
        if limit is not None:
            return await self._select(user_id, f"{where} {_NEWEST_FIRST} LIMIT ?", (*params, limit))
        return await self._select(user_id, f"{where} {_NEWEST_FIRST}", params)

    async def list_starred(self, user_id: str, limit: int) -> tuple[Expense, ...]:
        """The starred expenses that still count (posted, not void), newest first, at most ``limit``."""
        return await self._select(
            user_id, f"WHERE user_id = ? AND {_SHOWN} AND is_favorite = 1 AND status = ? {_NEWEST_FIRST} LIMIT ?",
            (user_id, EXPENSE_POSTED, limit))

    async def list_general(self, user_id: str, general_id: str, before: str | None,
                           limit: int) -> tuple[tuple[Expense, ...], str | None]:
        """One page of the General project's expenses, newest first, from the days before ``before`` (an ISO
        day; none: the newest). The page ends at a whole day, so a day is never split across pages; the second
        answer is the ``before`` for the next page, or ``None`` when this is the last."""
        where = f"WHERE user_id = ? AND project_id = ? AND {_SHOWN} AND spent_at < ?"
        page = await self._select(user_id, f"{where} {_NEWEST_FIRST} LIMIT ?",
                                  (user_id, general_id, before or "9999-12-31", limit + 1))
        if len(page) <= limit:
            return page, None
        day = page[limit - 1].spent_at
        newer = tuple(e for e in page[:limit] if e.spent_at != day)
        that_day = await self._select(user_id, f"WHERE user_id = ? AND project_id = ? AND {_SHOWN} AND spent_at = ? "
                                               "ORDER BY created_at DESC", (user_id, general_id, day))
        return (*newer, *that_day), day

    async def list_project(self, user_id: str, project_id: str) -> tuple[Expense, ...]:
        """Every expense of one project, all time, voids included, newest first.
        A project's total needs them all, and the amounts are summed in Python."""
        return await self._select(user_id, f"WHERE user_id = ? AND project_id = ? AND {_SHOWN} {_NEWEST_FIRST}",
                                  (user_id, project_id))

    async def for_tasks(self, user_id: str, task_ids: Sequence[str]) -> tuple[Expense, ...]:
        """Every expense linked to any of these tasks (H11), whatever project it is filed
        under, voids included. A task's spent is summed from these in Python, so the
        caller keeps the counted ones (``numbers.counted``). Only this user's."""
        found: tuple[Expense, ...] = ()
        for start in range(0, len(task_ids), TASK_EXPENSES_QUERY_CHUNK):
            chunk = tuple(task_ids[start:start + TASK_EXPENSES_QUERY_CHUNK])
            marks = ",".join("?" * len(chunk))
            found += await self._select(user_id, f"WHERE user_id = ? AND task_id IN ({marks}) AND {_SHOWN} "
                                                 f"{_NEWEST_FIRST}", (user_id, *chunk))
        return found

    async def unlink_step(self, user_id: str, task_id: str, step_id: str) -> tuple[str, ...]:
        """A deleted step's expenses stay on its task (redesign P3, LazyClaw's rule): their
        ``step_id`` is cleared. Deleted expenses too, so none is left naming a missing step.
        Returns the ids of the expenses that moved."""
        where = "WHERE user_id = ? AND task_id = ? AND step_id = ?"
        params = (user_id, task_id, step_id)
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT id FROM money_expenses {where}", params)).fetchall()
            await db.execute(f"UPDATE money_expenses SET step_id = NULL, updated_at = ? {where}", (_now_iso(), *params))
            await db.commit()
        return tuple(row[0] for row in rows)

    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[Expense, ...]:
        return await self._select(user_id, f"WHERE user_id = ? AND created_by_bot = ? AND {_SHOWN} "
                                           "ORDER BY created_at DESC LIMIT ?", (user_id, bot_id, limit))

    async def update(self, user_id: str, expense_id: str, patch: ExpensePatch) -> Expense | None:
        """Write only the patched columns (plus ``updated_at``), never the whole stale row, so a change
        to another column made between this read and this write is not put back. ``None``: no such
        expense, or it was deleted meanwhile."""
        current = await self.get(user_id, expense_id)
        if current is None:
            return None
        updated = replace(current, **dict(patch.changes), updated_at=_now_iso())
        dek = await get_user_dek(self._config, user_id)
        columns = tuple(column for column in _MUTABLE if column in patch.changes) + ("updated_at",)
        assignments = ", ".join(f"{column} = ?" for column in columns)
        async with db_session(self._config) as db:
            if "project_id" in columns:
                await require_project(db, user_id, updated.project_id)
            cursor = await db.execute(
                f"UPDATE money_expenses SET {assignments} WHERE id = ? AND user_id = ? AND {_SHOWN}",
                (*(_encode(updated, column, dek) for column in columns), expense_id, user_id))
            await db.commit()
        return updated if cursor.rowcount else None

    async def keep(self, user_id: str, expense_id: str) -> Expense | None:
        """The user vouches for an expense (the Board's Keep): its taint bit is
        cleared. Only the HTTP route reaches this; ``ExpensePatch`` can't."""
        async with db_session(self._config) as db:
            await db.execute(
                f"UPDATE money_expenses SET tainted = 0, updated_at = ? WHERE id = ? AND user_id = ? AND {_SHOWN}",
                (_now_iso(), expense_id, user_id),
            )
            await db.commit()
        return await self.get(user_id, expense_id)

    async def delete(self, user_id: str, expense_id: str) -> bool:
        now = _now_iso()
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE money_expenses SET deleted_at = ?, updated_at = ? WHERE id = ? AND user_id = ? AND {_SHOWN}",
                (now, now, expense_id, user_id),
            )
            await db.commit()
        return cursor.rowcount > 0

    async def restore(self, user_id: str, expense_id: str) -> Expense | None:
        """Undo a delete: ``deleted_at`` is cleared only for this user's deleted expense. Its project is checked
        in the same session as the write (``require_project``: ``ValueError`` when it is gone). ``None``: no
        such deleted expense."""
        gone = await self._select(user_id, "WHERE id = ? AND user_id = ? AND deleted_at IS NOT NULL",
                                  (expense_id, user_id))
        if not gone:
            return None
        now = _now_iso()
        async with db_session(self._config) as db:
            await require_project(db, user_id, gone[0].project_id)
            cursor = await db.execute(
                "UPDATE money_expenses SET deleted_at = NULL, updated_at = ? "
                "WHERE id = ? AND user_id = ? AND deleted_at IS NOT NULL", (now, expense_id, user_id))
            await db.commit()
        return replace(gone[0], updated_at=now) if cursor.rowcount else None

    async def move_many(self, user_id: str, expense_ids: Sequence[str], project_id: str) -> dict[str, str] | None:
        """File these expenses under ``project_id``, all or none, in one transaction: the project is checked in
        the same session (``require_project``, ``ValueError``), every id must be this user's live expense
        (checked, then the update's rowcount must equal ``len(expense_ids)``), else everything is rolled back and
        the answer is ``None``. Returns each moved id's earlier project."""
        ids = tuple(expense_ids)
        if not ids or len(set(ids)) != len(ids):
            return None
        marks = ",".join("?" * len(ids))
        async with db_session(self._config) as db:
            await require_project(db, user_id, project_id)
            try:
                before = {row["id"]: row["project_id"] for row in await (await db.execute(
                    f"SELECT id, project_id FROM money_expenses WHERE user_id = ? AND id IN ({marks}) AND {_SHOWN}",
                    (user_id, *ids))).fetchall()}
                if len(before) != len(ids):
                    return None
                cursor = await db.execute(
                    f"UPDATE money_expenses SET project_id = ?, updated_at = ? "
                    f"WHERE user_id = ? AND id IN ({marks}) AND {_SHOWN}", (project_id, _now_iso(), user_id, *ids))
                if cursor.rowcount != len(ids):
                    await db.rollback()
                    return None
                await db.commit()
            except BaseException:
                await db.rollback()          # a pooled connection: never leave a half-done transaction behind
                raise
        return before

    async def _select(self, user_id: str, where: str, params: tuple) -> tuple[Expense, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_SELECT} FROM money_expenses {where}", params)).fetchall()
            if not rows:
                return ()
            marked = await imported_ids(db, user_id, "expense", [row["id"] for row in rows])
        dek = await get_user_dek(self._config, user_id)
        return tuple(replace(expense, imported_from=IMPORTED_FROM_LAZYCLAW) if expense.id in marked else expense
                     for expense in (_row_to_expense(row, dek) for row in rows))
