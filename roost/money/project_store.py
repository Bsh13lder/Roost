# SPDX-License-Identifier: MIT
# Adapted from LazyClaw lazyclaw/budgets/store.py @ 21e1002 (names and semantics), for Roost
"""``ProjectStore`` — the user's projects (the ``money_projects`` table,
LazyClaw's projects).

- Names and both budgets are ``enc:v2``. ``name_key`` is HMAC(dek, folded
  name), so a name is unique among the user's live projects without ever
  being stored or compared in plaintext (LazyClaw kept a plaintext casefold
  key). Colour, dates, status and the lead bot are plaintext.
- ``budget`` is the total budget and already includes top-ups (LazyClaw's
  meaning). Every change to it writes a ``money_topups`` row in the same
  transaction (``roost/money/topup_store.py``), so while a budget is set it
  equals the sum of the live rows (H4). Clearing it writes an ``edit`` row of
  −budget (H5).
- General (H2) is the project whose ``name_key`` is the key of
  ``GENERAL_PROJECT_NAME``. It is never renamed, archived or deleted.
- Deleting is soft and one transaction (H9): the expenses move to General,
  the tasks (and their budget slices), notes and documents lose the link, and
  ``deleted_at`` is set.
  ``ON DELETE SET NULL`` is only a safety net.
- A write that depends on a read does the read inside its own
  ``db_session``. The session holds the connection's lock, so nothing can
  change in between."""

from __future__ import annotations

import hashlib
import hmac
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncIterator, Mapping
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.constants import DEFAULT_PROJECT_COLOR, GENERAL_PROJECT_NAME, PROJECT_STATUSES
from roost.crypto.encryption import decrypt_field, encrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.money import topup_store as ledger
from roost.money.amounts import amount_text, parse_amount
from roost.money.models import TOPUP_CREDIT, TOPUP_EDIT, Project, ProjectDraft, ProjectPatch, TopUp, check_dates

_COLUMNS = ("id, user_id, name, budget, currency, created_at, updated_at, created_by_bot, tainted, color, "
            "start_date, due_date, monthly_budget, lead_bot_id, status, pinned, pinned_at")
_INSERT = ("INSERT INTO money_projects (id, user_id, name, name_key, budget, currency, status, color, start_date, "
           "due_date, monthly_budget, lead_bot_id, created_at, updated_at, created_by_bot, tainted) "
           "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
_ACTIVE = PROJECT_STATUSES[0]                       # "active"
# Items that stay when their project goes (H9), each with the columns that are cleared. A task's budget
# slice is in the project's currency (H11), so it goes with the link.
_UNLINKED_COLUMNS = (("tasks", "project_id = NULL, allocated_budget = NULL"), ("notes", "project_id = NULL"),
                     ("documents", "project_id = NULL"))
_ZERO = Decimal("0")

NAME_TAKEN_TEXT = "A project with that name exists."
GENERAL_KEPT_TEXT = "General is where expenses with no project go; it cannot be renamed, archived or deleted."
CURRENCY_LOCKED_TEXT = "The currency can change only while the project has no expenses and no top-ups."
LEAD_BOT_GONE_TEXT = "The lead bot must be one of your bots."
PROJECT_GONE_TEXT = "No such project."


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"money_projects:{column}")


def _folded(name: str) -> str:
    return " ".join(name.casefold().split())


def _name_key(dek: bytes, name: str) -> str:
    return hmac.new(dek, _folded(name).encode("utf-8"), hashlib.sha256).hexdigest()


def is_general(project: Project) -> bool:
    """H2: General is the project whose ``name_key`` is the key of
    ``GENERAL_PROJECT_NAME``. The key is an HMAC of the folded name, so
    comparing the folded names is the same test, and needs no key."""
    return _folded(project.name) == _folded(GENERAL_PROJECT_NAME)


def _amount_or_none(text: str | None) -> Decimal | None:
    return Decimal(text) if text else None


def _encrypted_amount(user_id: str, dek: bytes, column: str, amount: object) -> str | None:
    if not isinstance(amount, Decimal):
        return None
    return encrypt(amount_text(amount), dek, _aad(user_id, column))


def _row_to_project(row: aiosqlite.Row, dek: bytes) -> Project:
    user_id = row["user_id"]

    def text(column: str) -> str | None:
        return decrypt_field(row[column], dek, _aad(user_id, column))

    return Project(
        id=row["id"], user_id=user_id, name=text("name") or "", budget=_amount_or_none(text("budget")),
        currency=row["currency"], created_at=row["created_at"], updated_at=row["updated_at"],
        created_by_bot=row["created_by_bot"], tainted=bool(row["tainted"]),
        color=row["color"] or DEFAULT_PROJECT_COLOR,      # a project saved before v13 has no colour yet
        start_date=row["start_date"], due_date=row["due_date"],
        monthly_budget=_amount_or_none(text("monthly_budget")), lead_bot_id=row["lead_bot_id"],
        status=row["status"], pinned=bool(row["pinned"]), pinned_at=row["pinned_at"],
    )


def _new_project(user_id: str, project_id: str, draft: ProjectDraft, now: str, created_by_bot: str | None,
                 tainted: bool) -> Project:
    return Project(
        id=project_id, user_id=user_id, name=draft.name, budget=draft.budget, currency=draft.currency,
        created_at=now, updated_at=now, created_by_bot=created_by_bot, tainted=tainted, color=draft.color,
        start_date=draft.start_date, due_date=draft.due_date, monthly_budget=draft.monthly_budget,
        lead_bot_id=draft.lead_bot_id, status=_ACTIVE,
    )


def _columns_for(user_id: str, dek: bytes, field: str, value: object) -> tuple[tuple[str, object], ...]:
    if field == "name":
        name = str(value)
        return (("name", encrypt(name, dek, _aad(user_id, "name"))), ("name_key", _name_key(dek, name)))
    if field == "monthly_budget":
        return (("monthly_budget", _encrypted_amount(user_id, dek, "monthly_budget", value)),)
    return ((field, value),)


def _assignments(user_id: str, dek: bytes, changes: Mapping[str, object]) -> tuple[tuple[str, object], ...]:
    """The columns a patch writes. Its keys are ``PROJECT_PATCHABLE`` (checked
    by ``ProjectPatch``), so they are safe column names."""
    return tuple(pair for field, value in changes.items() for pair in _columns_for(user_id, dek, field, value))


def _changes_general(current: Project, changes: Mapping[str, object]) -> bool:
    """A rename (beyond case and spacing) or an archive of General (H2)."""
    renamed = "name" in changes and _folded(str(changes["name"])) != _folded(current.name)
    archived = changes.get("status", current.status) != _ACTIVE
    return is_general(current) and (renamed or archived)


def _integrity_text(exc: aiosqlite.IntegrityError) -> str | None:
    """The two conflicts a caller can cause, as sentences: a live project
    already has the name (unique ``name_key``), or the lead bot does not exist
    (foreign key)."""
    text = str(exc)
    if "UNIQUE" in text:
        return NAME_TAKEN_TEXT
    return LEAD_BOT_GONE_TEXT if "FOREIGN KEY" in text else None


@asynccontextmanager
async def _transaction(config: Config) -> AsyncIterator[aiosqlite.Connection]:
    """One write transaction. Reads inside it see exactly what its writes
    change, because the session holds the connection's lock. Any error rolls
    all of it back."""
    async with db_session(config) as db:
        try:
            yield db
            await db.commit()
        except aiosqlite.IntegrityError as exc:
            await db.rollback()
            text = _integrity_text(exc)
            if text is None:
                raise
            raise ValueError(text) from exc
        except BaseException:
            await db.rollback()
            raise


async def _insert(db: aiosqlite.Connection, project: Project, dek: bytes) -> None:
    user_id = project.user_id
    await db.execute(_INSERT, (
        project.id, user_id, encrypt(project.name, dek, _aad(user_id, "name")), _name_key(dek, project.name),
        _encrypted_amount(user_id, dek, "budget", project.budget), project.currency, project.status, project.color,
        project.start_date, project.due_date, _encrypted_amount(user_id, dek, "monthly_budget", project.monthly_budget),
        project.lead_bot_id, project.created_at, project.updated_at, project.created_by_bot, int(project.tainted),
    ))


async def _live_project(db: aiosqlite.Connection, user_id: str, dek: bytes, project_id: str) -> Project | None:
    rows = await (await db.execute(
        f"SELECT {_COLUMNS} FROM money_projects WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (project_id, user_id),
    )).fetchall()
    return _row_to_project(rows[0], dek) if rows else None


async def _clear_project_mark(db: aiosqlite.Connection, user_id: str, project_id: str, now: str) -> None:
    await db.execute(
        "UPDATE money_projects SET tainted = 0, updated_at = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (now, project_id, user_id),
    )


async def _write_budget(db: aiosqlite.Connection, project: Project, budget: Decimal | None, dek: bytes,
                        now: str) -> None:
    await db.execute(
        "UPDATE money_projects SET budget = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (_encrypted_amount(project.user_id, dek, "budget", budget), now, project.id, project.user_id),
    )


async def _has_money(db: aiosqlite.Connection, user_id: str, project_id: str) -> bool:
    """H7: an expense that is not deleted (void ones count), or a live top-up.
    A budget alone is not money: its "Budget set" rows follow a currency change."""
    rows = await (await db.execute(
        "SELECT EXISTS (SELECT 1 FROM money_expenses WHERE user_id = ? AND project_id = ? AND deleted_at IS NULL) "
        "OR EXISTS (SELECT 1 FROM money_topups WHERE user_id = ? AND project_id = ? AND kind = ? "
        "AND deleted_at IS NULL)",
        (user_id, project_id, user_id, project_id, TOPUP_CREDIT),
    )).fetchall()
    return bool(rows[0][0])


async def _check_update(db: aiosqlite.Connection, current: Project, changes: Mapping[str, object]) -> None:
    if _changes_general(current, changes):
        raise ValueError(GENERAL_KEPT_TEXT)
    check_dates(changes.get("start_date", current.start_date), changes.get("due_date", current.due_date))
    new_currency = changes.get("currency", current.currency)
    if new_currency != current.currency and await _has_money(db, current.user_id, current.id):
        raise ValueError(CURRENCY_LOCKED_TEXT)


async def general_currency(db: aiosqlite.Connection, user_id: str, dek: bytes) -> str:
    """General's currency, the one a task in no project counts its money in (owner, 2026-10-26): an
    expense for such a task goes to General. Before General exists it is the default a new one gets."""
    rows = await (await db.execute(
        "SELECT currency FROM money_projects WHERE user_id = ? AND name_key = ? AND deleted_at IS NULL",
        (user_id, _name_key(dek, GENERAL_PROJECT_NAME)),
    )).fetchall()
    return rows[0]["currency"] if rows else ProjectDraft(name=GENERAL_PROJECT_NAME).currency


async def _general_id(db: aiosqlite.Connection, user_id: str, dek: bytes, now: str) -> str:
    """General's id, made inside the caller's transaction when it does not exist yet (H9)."""
    rows = await (await db.execute(
        "SELECT id FROM money_projects WHERE user_id = ? AND name_key = ? AND deleted_at IS NULL",
        (user_id, _name_key(dek, GENERAL_PROJECT_NAME)),
    )).fetchall()
    if rows:
        return rows[0]["id"]
    general = _new_project(user_id, str(uuid4()), ProjectDraft(name=GENERAL_PROJECT_NAME), now, None, False)
    await _insert(db, general, dek)
    return general.id


async def _hand_over(db: aiosqlite.Connection, user_id: str, project_id: str, general_id: str, now: str) -> None:
    """H9's first two steps. The expenses move to General. The tasks, notes and
    documents only lose the link (a task loses its budget slice too): their
    revision and ``updated_at`` stay, so an open editor is not disturbed."""
    await db.execute(
        "UPDATE money_expenses SET project_id = ?, updated_at = ? WHERE user_id = ? AND project_id = ?",
        (general_id, now, user_id, project_id),
    )
    for table, cleared in _UNLINKED_COLUMNS:
        await db.execute(f"UPDATE {table} SET {cleared} WHERE user_id = ? AND project_id = ?", (user_id, project_id))


async def _credit_and_project(db: aiosqlite.Connection, user_id: str, dek: bytes,
                              topup_id: str) -> tuple[TopUp, Project] | None:
    """A top-up the user may change: one of their credits, on a live project.
    An undone one is refused (``TopUpUndone``, HTTP 409). So is one that
    clearing the total budget already took back (a plain ``ValueError``, a
    broken rule: HTTP 422)."""
    credit = await ledger.credit(db, user_id, dek, topup_id)
    project = await _live_project(db, user_id, dek, credit.project_id) if credit is not None else None
    if credit is None or project is None:
        return None
    if credit.undone:
        raise ledger.TopUpUndone(ledger.TOPUP_UNDONE_TEXT)
    if await ledger.taken_back(db, user_id, dek, credit):
        raise ValueError(ledger.TAKEN_BACK_TEXT)
    return credit, project


class ProjectStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def list(self, user_id: str, *, include_archived: bool = True) -> tuple[Project, ...]:
        """Live projects, oldest first. ``include_archived=False`` keeps the active ones."""
        if include_archived:
            return await self._select(user_id, "WHERE user_id = ? AND deleted_at IS NULL ORDER BY created_at",
                                      (user_id,))
        return await self._select(
            user_id, "WHERE user_id = ? AND deleted_at IS NULL AND status = ? ORDER BY created_at", (user_id, _ACTIVE),
        )

    async def get(self, user_id: str, project_id: str) -> Project | None:
        found = await self._select(user_id, "WHERE id = ? AND user_id = ? AND deleted_at IS NULL", (project_id, user_id))
        return found[0] if found else None

    async def find(self, user_id: str, name: str) -> Project | None:
        """The live project with this name, case and spacing ignored, archived or
        not. It never creates one (H3)."""
        if not name.strip():
            return None
        dek = await get_user_dek(self._config, user_id)
        found = await self._select(user_id, "WHERE user_id = ? AND name_key = ? AND deleted_at IS NULL",
                                   (user_id, _name_key(dek, name)))
        return found[0] if found else None

    async def find_or_create(self, user_id: str, name: str, *, created_by_bot: str | None, tainted: bool) -> Project:
        """``log_expense``'s lookup, the only one that creates (H3): the live
        project with this name, else a new one. Two concurrent creations end on
        the same row."""
        found = await self.find(user_id, name)
        if found is not None:
            return found
        try:
            return await self.create(user_id, ProjectDraft(name=name), created_by_bot=created_by_bot, tainted=tainted)
        except ValueError as exc:
            if str(exc) != NAME_TAKEN_TEXT:
                raise
            made_meanwhile = await self.find(user_id, name)
            if made_meanwhile is None:
                raise
            return made_meanwhile

    async def create(self, user_id: str, draft: ProjectDraft, *, created_by_bot: str | None,
                     tainted: bool) -> Project:
        """A new active project. A total budget is written with its "Budget set"
        row, so the history holds it from the start (H4). A name in use (case
        and spacing ignored) or a lead bot that does not exist is a
        ``ValueError``."""
        dek = await get_user_dek(self._config, user_id)
        project = _new_project(user_id, str(uuid4()), draft, _now_iso(), created_by_bot, tainted)
        async with _transaction(self._config) as db:
            await _insert(db, project, dek)
            if project.budget is not None:
                entry = ledger.LedgerRow(project.id, project.budget, project.currency, TOPUP_EDIT,
                                         created_by_bot=created_by_bot, tainted=tainted)
                await ledger.add_row(db, user_id, dek, entry, project.created_at)
        return project

    async def update(self, user_id: str, project_id: str, patch: ProjectPatch) -> Project | None:
        """Rename (``name_key`` follows), colour, dates, monthly limit, lead bot,
        archive / unarchive and currency. ``None``: no such project. General
        keeps its name and stays active (H2). The currency changes only while
        the project has no money, and then its "Budget set" rows follow (H7)."""
        dek = await get_user_dek(self._config, user_id)
        now = _now_iso()
        async with _transaction(self._config) as db:
            current = await _live_project(db, user_id, dek, project_id)
            if current is None or not patch.changes:
                return current
            await _check_update(db, current, patch.changes)
            pairs = _assignments(user_id, dek, patch.changes)
            sets = ", ".join(f"{column} = ?" for column, _ in pairs)
            await db.execute(f"UPDATE money_projects SET {sets}, updated_at = ? WHERE id = ? AND user_id = ?",
                             (*(value for _, value in pairs), now, project_id, user_id))
            if patch.changes.get("currency", current.currency) != current.currency:
                await ledger.set_currency(db, user_id, project_id, str(patch.changes["currency"]), now)
        return await self.get(user_id, project_id)

    async def keep(self, user_id: str, project_id: str) -> Project | None:
        """The user vouches for a project a bot made from web content (the Board's
        Keep): its taint bit goes, and so do those of its "Budget set" rows (an
        ``edit`` row with no ``topup_id``: the one written when it was made, and
        any later set by a bot), so its page is not web content any more. A
        top-up row is a change of its own and stays as it is. HTTP only, never
        a tool. ``None``: no such project."""
        async with db_session(self._config) as db:
            now = _now_iso()
            await _clear_project_mark(db, user_id, project_id, now)
            await db.execute(
                "UPDATE money_topups SET tainted = 0, updated_at = ? WHERE project_id = ? AND user_id = ? "
                "AND tainted = 1 AND kind = ? AND topup_id IS NULL AND EXISTS (SELECT 1 FROM money_projects "
                "WHERE id = ? AND user_id = ? AND deleted_at IS NULL)",
                (now, project_id, user_id, TOPUP_EDIT, project_id, user_id),
            )
            await db.commit()
        return await self.get(user_id, project_id)

    async def set_pinned(self, user_id: str, project_id: str, pinned: bool) -> Project | None:
        """Pin the project (``pinned_at`` is now) or unpin it (``pinned_at`` is null). Pinning is not a
        change of content, so ``updated_at`` stays. ``None``: no such project."""
        async with db_session(self._config) as db:
            await db.execute(
                "UPDATE money_projects SET pinned = ?, pinned_at = ? "
                "WHERE id = ? AND user_id = ? AND deleted_at IS NULL AND pinned != ?",
                (int(pinned), _now_iso() if pinned else None, project_id, user_id, int(pinned)),
            )
            await db.commit()
        return await self.get(user_id, project_id)

    async def keep_name(self, user_id: str, project_id: str) -> Project | None:
        """Vouch for the project's *name* only: the Keep of an expense, whose row shows it. The history
        rows are the project's own Keep (``keep``). ``None``: no such project."""
        async with db_session(self._config) as db:
            await _clear_project_mark(db, user_id, project_id, _now_iso())
            await db.commit()
        return await self.get(user_id, project_id)

    async def set_budget(self, user_id: str, project_id: str, amount: Decimal | None, *,
                         created_by_bot: str | None, tainted: bool) -> Project | None:
        """Set the total budget to ``amount`` with an ``edit`` row of the change
        ("Budget set"). ``None`` clears it (H5): an ``edit`` row of −budget,
        then no budget. An unchanged budget writes no row. ``None`` back: no
        such project. The amount is read again with ``parse_amount`` here, so
        no caller can break ``budget == Σ live rows`` (a ``ValueError`` if it
        is not above 0 or has more than 2 decimals)."""
        checked = None if amount is None else parse_amount(amount)
        dek = await get_user_dek(self._config, user_id)
        now = _now_iso()
        async with _transaction(self._config) as db:
            current = await _live_project(db, user_id, dek, project_id)
            if current is None or checked == current.budget:
                return current
            change = (checked if checked is not None else _ZERO) - (current.budget or _ZERO)
            entry = ledger.LedgerRow(current.id, change, current.currency, TOPUP_EDIT,
                                     created_by_bot=created_by_bot, tainted=tainted)
            await ledger.add_row(db, user_id, dek, entry, now)
            await _write_budget(db, current, checked, dek, now)
        return replace(current, budget=checked, updated_at=now)

    async def add_topup(self, user_id: str, project_id: str, amount: Decimal, source: str | None, *,
                        created_by_bot: str | None, tainted: bool) -> TopUp:
        """A ``credit`` row that raises the total budget by ``amount``; a project
        with no budget gets one. The project must be the user's and live, else
        ``ValueError("No such project.")``. The amount is read again with
        ``parse_amount`` (see ``set_budget``)."""
        checked = parse_amount(amount)
        dek = await get_user_dek(self._config, user_id)
        now = _now_iso()
        async with _transaction(self._config) as db:
            current = await _live_project(db, user_id, dek, project_id)
            if current is None:
                raise ValueError(PROJECT_GONE_TEXT)
            entry = ledger.LedgerRow(current.id, checked, current.currency, TOPUP_CREDIT, source=source,
                                     created_by_bot=created_by_bot, tainted=tainted)
            topup = await ledger.add_row(db, user_id, dek, entry, now)
            await _write_budget(db, current, (current.budget or _ZERO) + checked, dek, now)
        return topup

    async def edit_topup(self, user_id: str, topup_id: str, amount: Decimal) -> TopUp | None:
        """``amount`` is the top-up's new amount (H4). The store writes an
        ``edit`` row of the difference, linked to the credit by ``topup_id``,
        and moves the budget by the same. It returns that row, or the credit
        itself when the amount is already that. ``None``: no such top-up of the
        user's on a live project. The amount is read again with ``parse_amount``
        (see ``set_budget``)."""
        checked = parse_amount(amount)
        dek = await get_user_dek(self._config, user_id)
        now = _now_iso()
        async with _transaction(self._config) as db:
            found = await _credit_and_project(db, user_id, dek, topup_id)
            if found is None:
                return None
            credit, project = found
            change = checked - await ledger.live_total(db, user_id, dek, credit.id)
            if change == _ZERO:
                return credit
            budget = ledger.moved_budget(project.budget, change)
            entry = ledger.LedgerRow(project.id, change, credit.currency, TOPUP_EDIT, topup_id=credit.id)
            edit = await ledger.add_row(db, user_id, dek, entry, now)
            await _write_budget(db, project, budget, dek, now)
        return edit

    async def undo_topup(self, user_id: str, topup_id: str) -> TopUp | None:
        """The credit and all its edits leave the budget together (H4):
        ``deleted_at`` on each, and the budget lowered by their sum. It returns
        the credit, now ``undone``."""
        dek = await get_user_dek(self._config, user_id)
        now = _now_iso()
        async with _transaction(self._config) as db:
            found = await _credit_and_project(db, user_id, dek, topup_id)
            if found is None:
                return None
            credit, project = found
            budget = ledger.moved_budget(project.budget, -await ledger.live_total(db, user_id, dek, credit.id))
            await ledger.mark_undone(db, user_id, credit.id, now)
            await _write_budget(db, project, budget, dek, now)
        return replace(credit, undone=True)

    async def topups(self, user_id: str, project_id: str) -> tuple[TopUp, ...]:
        """The budget history, newest first, undone rows included (``undone=True``).
        A credit the clearing of the budget took back is marked ``taken_back``."""
        async with db_session(self._config) as db:
            rows = await ledger.history_rows(db, user_id, project_id)
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        back = ledger.taken_back_ids(rows, dek)      # the same replay ``edit_topup`` and ``undo_topup`` refuse by
        return tuple(ledger.row_to_topup(row, dek, taken_back=row["id"] in back) for row in rows)

    async def general_currency(self, user_id: str) -> str:
        """General's currency (``general_currency``): what a task in no project counts its money in."""
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            return await general_currency(db, user_id, dek)

    async def has_money(self, user_id: str, project_id: str) -> bool:
        """Any expense or live top-up: then the currency can no longer change (H7)."""
        async with db_session(self._config) as db:
            return await _has_money(db, user_id, project_id)

    async def delete(self, user_id: str, project_id: str) -> bool:
        """H9 in one transaction: General is found or made, the expenses move to
        it, the tasks, notes and documents lose the link, and the project gets
        ``deleted_at``. General itself is refused. ``False``: no such project."""
        dek = await get_user_dek(self._config, user_id)
        now = _now_iso()
        async with _transaction(self._config) as db:
            current = await _live_project(db, user_id, dek, project_id)
            if current is None:
                return False
            if is_general(current):
                raise ValueError(GENERAL_KEPT_TEXT)
            await _hand_over(db, user_id, project_id, await _general_id(db, user_id, dek, now), now)
            await db.execute("UPDATE money_projects SET deleted_at = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                             (now, now, project_id, user_id))
        return True

    async def _select(self, user_id: str, where: str, params: tuple) -> tuple[Project, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_COLUMNS} FROM money_projects {where}", params)).fetchall()
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_project(row, dek) for row in rows)
