"""``TaskStore`` — the user's tasks, encrypted (M1 D2, D6).

Tasks belong to the USER: every bot holding the tasks role reads and writes
the same rows, scoped by ``user_id`` only. Each row records the bot that
created it (``created_by_bot``, NULL for the user or a retired bot) and a
taint bit. Title, description, category, tags, steps and the budget slice
(``allocated_budget``) are ``enc:v2`` under ``tasks:<column>``; dates, status,
priority, the cron string and ``project_id`` stay plaintext for queries.
Deleting is soft (``deleted_at``), as in LazyClaw.

Projects hub (H11): a task may belong to one of the user's live projects
(another user's, an unknown or a deleted one is refused, see
``roost.records.project_link``) and carry a budget slice in its project's
currency, or General's for a task in no project (owner, 2026-10-26). ``fail`` closes a task like ``complete`` does, and
``closed_between`` reads the tasks closed in a time window."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.constants import STEP_WRITE_ATTEMPTS
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.money.amounts import amount_text, parse_amount
from roost.records.imports import IMPORTED_FROM_LAZYCLAW, imported_ids
from roost.money.project_store import general_currency
from roost.records.project_link import project_currencies, require_project
from roost.tasks.models import DueSet, Step, Task, TaskDraft, TaskFilter, TaskPatch
from roost.tasks.steps import cascade_steps, steps_from_json, steps_from_titles, steps_to_json, uncascade_steps

logger = logging.getLogger(__name__)

SLICE_NEEDS_PROJECT = "A budget slice needs a project."   # the bots' rule still (H11, roost.tasks.tools)
STEPS_BUSY_TEXT = "This task's steps changed while yours was being saved. Try again."

_COLUMNS = (
    "id", "user_id", "title", "description", "category", "priority", "status", "owner", "due_date",
    "reminder_at", "pre_reminders", "recurring", "recur_until", "tags", "steps", "created_at", "updated_at",
    "completed_at", "created_by_bot", "tainted", "project_id", "allocated_budget", "starred", "estimate",
)
_SELECT = ", ".join(_COLUMNS)
_MUTABLE = (
    "title", "description", "category", "priority", "status", "due_date", "reminder_at", "pre_reminders",
    "recurring", "recur_until", "tags", "steps", "completed_at", "updated_at", "project_id", "allocated_budget",
    "starred", "estimate_minutes",
)
_SQL_NAME = {"estimate_minutes": "estimate"}   # a patch names the field, the table the column
_TEXT = frozenset({"title", "description", "category"})
_ORDER = ("CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, "
          "due_date IS NULL, due_date, created_at DESC")
_OPEN_STATUSES = ("todo", "in_progress")
_OPEN_SQL = " AND status IN ('todo','in_progress')"
_FILTERS = {"open": _OPEN_SQL, "done": " AND status = 'done'", "failed": " AND status = 'failed'", "all": ""}
_PROJECT_SQL = " AND project_id = ?"
_NO_PROJECT_SQL = " AND project_id IS NULL"
_SAME_VERSION_SQL = " AND updated_at = ?"
_STEP_COLUMNS = ("steps", "tainted", "updated_at")
_CLOSED_STATUSES = ("done", "failed")
_REMINDERS_SQL = ("WHERE user_id = ? AND deleted_at IS NULL AND status IN ('todo','in_progress') "
                  "AND reminder_at IS NOT NULL AND reminder_at >= ? AND reminder_at < ? ORDER BY reminder_at")
_CLOSED_SQL = ("WHERE user_id = ? AND deleted_at IS NULL AND status IN ('done','failed') "
               "AND completed_at >= ? AND completed_at < ? ORDER BY completed_at")


class StepsBusy(RuntimeError):
    """A steps change lost the compare-and-set ``STEP_WRITE_ATTEMPTS`` times (a 409 over HTTP)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"tasks:{column}")


def _checked_slice(task: Task) -> Task:
    """A budget slice follows the amount rules (``parse_amount``: more than 0, at most 2 decimals, at most
    the cap). A task in no project may have one too, in General's currency (owner, 2026-10-26)."""
    if task.allocated_budget is None:
        return task
    return replace(task, allocated_budget=parse_amount(task.allocated_budget))


def _utc_bound(value: str) -> str:
    """A ``closed_between`` bound as the UTC ISO text that ``completed_at`` is
    written in (``_now_iso``), so comparing the strings compares the times."""
    try:
        moment = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"“{value}” is not a time.") from exc
    if moment.tzinfo is None:
        raise ValueError(f"“{value}” has no time zone.")
    return moment.astimezone(timezone.utc).isoformat()


def _encode(task: Task, column: str, dek: bytes) -> Any:
    if column in _TEXT:
        return encrypt_field(getattr(task, column), dek, _aad(task.user_id, column))
    if column == "tags":
        return encrypt_field(json.dumps(list(task.tags)), dek, _aad(task.user_id, column))
    if column == "steps":
        return encrypt_field(steps_to_json(task.steps), dek, _aad(task.user_id, column))
    if column == "allocated_budget":
        amount = task.allocated_budget
        return encrypt_field(None if amount is None else amount_text(amount), dek, _aad(task.user_id, column))
    if column in ("estimate", "estimate_minutes"):
        minutes = task.estimate_minutes
        return encrypt_field(None if minutes is None else str(minutes), dek, _aad(task.user_id, "estimate"))
    if column == "starred":
        return int(task.starred)
    if column == "pre_reminders":
        return json.dumps(list(task.pre_reminders))
    if column == "tainted":
        return int(task.tainted)
    return getattr(task, column)


def _json_list(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    return tuple(str(item) for item in parsed) if isinstance(parsed, list) else ()


def _slice(row: aiosqlite.Row, dek: bytes) -> Decimal | None:
    """The budget slice, or ``None``. A value that won't decrypt under its own
    AAD (``decrypt_field`` then gives its fallback text) or won't read as a
    finite amount (a damaged row) reads as no slice, and is logged."""
    text = decrypt_field(row["allocated_budget"], dek, _aad(row["user_id"], "allocated_budget"))
    if text is None:
        return None
    try:
        amount = Decimal(text)
    except InvalidOperation:
        amount = None
    if amount is None or not amount.is_finite():
        logger.warning("Task %s has an unreadable budget slice; it reads as none", row["id"])
        return None
    return amount


def _minutes(text: str | None) -> int | None:
    """The sealed estimate, or ``None`` (also for a value that is not a whole number of minutes)."""
    try:
        return None if text is None else int(text)
    except ValueError:
        return None


def _row_to_task(row: aiosqlite.Row, dek: bytes) -> Task:
    user_id = row["user_id"]

    def text(column: str) -> str | None:
        return decrypt_field(row[column], dek, _aad(user_id, column))

    return Task(
        id=row["id"], user_id=user_id, title=text("title") or "", description=text("description"),
        category=text("category"), priority=row["priority"], status=row["status"], owner=row["owner"],
        due_date=row["due_date"], reminder_at=row["reminder_at"], pre_reminders=_json_list(row["pre_reminders"]),
        recurring=row["recurring"], recur_until=row["recur_until"], tags=_json_list(text("tags")),
        steps=steps_from_json(text("steps")), created_at=row["created_at"], updated_at=row["updated_at"],
        completed_at=row["completed_at"], created_by_bot=row["created_by_bot"], tainted=bool(row["tainted"]),
        project_id=row["project_id"], allocated_budget=_slice(row, dek), starred=bool(row["starred"]),
        estimate_minutes=_minutes(text("estimate")),
    )


class ClientIdTaken(Exception):
    """The user already has a task made from this offline client id."""


class TaskStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def create(self, user_id: str, draft: TaskDraft, *, created_by_bot: str | None, tainted: bool,
                     client_id: str | None = None) -> Task:
        """``ValueError`` (nothing written) for a project that isn't the
        user's, or a slice without a project or outside the amount rules. ``client_id`` is the phone's id for a
        task it added offline, written in the same transaction: ``ClientIdTaken`` (nothing written) when the
        user already has a task with it."""
        now = _now_iso()
        task = _checked_slice(Task(
            id=str(uuid4()), user_id=user_id, title=draft.title, description=draft.description,
            category=draft.category, priority=draft.priority, status="todo", owner=draft.owner,
            due_date=draft.due_date, reminder_at=draft.reminder_at, pre_reminders=draft.pre_reminders,
            recurring=draft.recurring, recur_until=draft.recur_until, tags=draft.tags,
            steps=steps_from_titles(draft.steps), created_at=now, updated_at=now, completed_at=None,
            created_by_bot=created_by_bot, tainted=tainted, project_id=draft.project_id,
            allocated_budget=draft.allocated_budget, starred=draft.starred,
            estimate_minutes=draft.estimate_minutes,
        ))
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            await require_project(db, user_id, task.project_id)
            await db.execute(f"INSERT INTO tasks ({_SELECT}) VALUES ({','.join('?' * len(_COLUMNS))})",
                             tuple(_encode(task, column, dek) for column in _COLUMNS))
            if client_id is not None:
                try:
                    await db.execute("UPDATE tasks SET client_id = ? WHERE id = ? AND user_id = ?",
                                     (client_id, task.id, user_id))
                except aiosqlite.IntegrityError as exc:
                    await db.rollback()
                    raise ClientIdTaken(client_id) from exc
            await db.commit()
        return task

    async def find_by_client_id(self, user_id: str, client_id: str) -> Task | None:
        """Deleted ones too: a sync sent again after you deleted its task on the Mac must not bring it back."""
        found = await self._select(user_id, "WHERE user_id = ? AND client_id = ?", (user_id, client_id))
        return found[0] if found else None

    async def get(self, user_id: str, task_id: str) -> Task | None:
        found = await self._select(user_id, "WHERE id = ? AND user_id = ? AND deleted_at IS NULL", (task_id, user_id))
        return found[0] if found else None

    async def list(self, user_id: str, *, status: TaskFilter = "open",
                   project_id: str | None = None, no_project: bool = False) -> tuple[Task, ...]:
        """``project_id`` keeps only that project's tasks, ``no_project`` only the tasks in none: fixed SQL
        fragments plus a parameter, never text from the caller."""
        project_sql, params = ("", (user_id,)) if project_id is None else (_PROJECT_SQL, (user_id, project_id))
        if no_project:
            project_sql, params = _NO_PROJECT_SQL, (user_id,)
        return await self._select(
            user_id, f"WHERE user_id = ? AND deleted_at IS NULL{_FILTERS[status]}{project_sql} ORDER BY {_ORDER}",
            params,
        )

    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[Task, ...]:
        return await self._select(user_id, "WHERE user_id = ? AND created_by_bot = ? AND deleted_at IS NULL "
                                           "ORDER BY created_at DESC LIMIT ?", (user_id, bot_id, limit))

    async def update(self, user_id: str, task_id: str, patch: TaskPatch) -> Task | None:
        """Write only the patched columns (plus ``updated_at``), never the
        whole stale row — so a concurrent change to a column this patch
        doesn't touch (e.g. a Board complete) is never clobbered.

        A new project must be the user's (checked in ``_write``): ``ValueError``,
        nothing written.

        A slice is in its project's currency (General's for no project), so it
        follows the project: a move into another currency clears it, unless the
        same change sends a slice of its own. A move that keeps the currency
        keeps it."""
        current = await self.get(user_id, task_id)
        if current is None:
            return None
        changes = await self._with_slice_settled(user_id, current, patch.changes)
        updated = replace(current, **dict(changes), updated_at=_now_iso())
        if changes.get("allocated_budget") is not None:
            updated = _checked_slice(updated)
        columns = tuple(column for column in _MUTABLE if column in changes) + ("updated_at",)
        return await self._write(updated, columns)

    async def _with_slice_settled(self, user_id: str, current: Task, changes: Mapping[str, Any]) -> Mapping[str, Any]:
        """``changes`` plus ``allocated_budget: None`` when this move of the task leaves its slice in
        the wrong currency. A project that can't be read (gone, not the user's) can't vouch for it."""
        if current.allocated_budget is None or "allocated_budget" in changes or "project_id" not in changes:
            return changes
        target = changes["project_id"]
        if target == current.project_id:
            return changes
        before, after = await self._home_currencies(user_id, (current.project_id, target))
        if before is not None and before == after:
            return changes
        return {**changes, "allocated_budget": None}

    async def _home_currencies(self, user_id: str, project_ids: Sequence[str | None]) -> tuple[str | None, ...]:
        """The currency each of these homes counts money in: a project's own, General's for ``None``,
        and ``None`` for a project that is not one of the user's live ones."""
        dek = await get_user_dek(self._config, user_id)
        named = tuple(project_id for project_id in project_ids if project_id is not None)
        async with db_session(self._config) as db:
            currencies = await project_currencies(db, user_id, named) if named else {}
            general = await general_currency(db, user_id, dek)
        return tuple(general if project_id is None else currencies.get(project_id) for project_id in project_ids)

    async def money_currency(self, user_id: str, task: Task) -> str | None:
        """The currency the task's money is counted in (owner, 2026-10-26): its project's, or General's
        when it has none. ``None`` for a project that can no longer be read."""
        return (await self._home_currencies(user_id, (task.project_id,)))[0]

    async def complete(self, user_id: str, task_id: str) -> Task | None:
        """Close an open task (open steps are ticked as cascaded). ``None`` when
        there is no open task with that id. The UPDATE itself is guarded on
        the status it read, a compare-and-set, so two concurrent completes
        can't both succeed and both respawn — a double tap never repeats."""
        current = await self.get(user_id, task_id)
        if current is None or current.status not in _OPEN_STATUSES:
            return None
        now = _now_iso()
        updated = replace(current, status="done", completed_at=now, updated_at=now,
                          steps=cascade_steps(current.steps))
        return await self._write(updated, ("status", "completed_at", "updated_at", "steps"), guard_sql=_OPEN_SQL)

    async def fail(self, user_id: str, task_id: str) -> Task | None:
        """Close an open task as failed (H11). Like ``complete`` it sets
        ``completed_at`` and is a compare-and-set on the status it read;
        unlike it, the open steps stay open, since a failed task did not do
        them. ``None`` when there is no open task with that id."""
        current = await self.get(user_id, task_id)
        if current is None or current.status not in _OPEN_STATUSES:
            return None
        now = _now_iso()
        updated = replace(current, status="failed", completed_at=now, updated_at=now)
        return await self._write(updated, ("status", "completed_at", "updated_at"), guard_sql=_OPEN_SQL)

    async def reopen(self, user_id: str, task_id: str) -> Task | None:
        """Open a done or failed task again (the Undo of a complete): the status goes back to ``todo``, the
        close time is cleared, and the steps closing ticked for the user are open again. ``None`` when there
        is no closed task of the user's with that id. A compare-and-set on the status it read."""
        current = await self.get(user_id, task_id)
        if current is None or current.status not in _CLOSED_STATUSES:
            return None
        updated = replace(current, status="todo", completed_at=None, updated_at=_now_iso(),
                          steps=uncascade_steps(current.steps))
        return await self._write(updated, ("status", "completed_at", "updated_at", "steps"),
                                 guard_sql=" AND status = ?", guard_params=(current.status,))

    async def set_dues(self, user_id: str, items: Sequence[DueSet]) -> tuple[DueSet, ...] | None:
        """Write each item's due, reminder and advance reminders, all or none, in one transaction. Every id must
        be a live task of this user's (else nothing is written and the answer is ``None``). Returns the values
        the tasks had before, in the items' order."""
        ids = tuple(item.id for item in items)
        if not ids or len(set(ids)) != len(ids):
            return None
        marks = ",".join("?" * len(ids))
        async with db_session(self._config) as db:
            try:
                rows = await (await db.execute(
                    f"SELECT id, due_date, reminder_at, pre_reminders FROM tasks "
                    f"WHERE user_id = ? AND deleted_at IS NULL AND id IN ({marks})", (user_id, *ids))).fetchall()
                if len(rows) != len(ids):
                    return None
                before = {row["id"]: DueSet(row["id"], row["due_date"], row["reminder_at"],
                                            _json_list(row["pre_reminders"])) for row in rows}
                now = _now_iso()
                for item in items:
                    cursor = await db.execute(
                        "UPDATE tasks SET due_date = ?, reminder_at = ?, pre_reminders = ?, updated_at = ? "
                        "WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                        (item.due_date, item.reminder_at, json.dumps(list(item.pre_reminders)), now, item.id, user_id))
                    if cursor.rowcount != 1:
                        await db.rollback()
                        return None
                await db.commit()
            except BaseException:
                await db.rollback()          # a pooled connection: never leave a half-done transaction behind
                raise
        return tuple(before[item_id] for item_id in ids)

    async def closed_between(self, user_id: str, start_utc: str, end_utc: str) -> tuple[Task, ...]:
        """Done and failed tasks with ``completed_at`` in ``[start_utc,
        end_utc)``, oldest first. Each bound may carry any offset; one with
        none is refused (``ValueError``)."""
        params = (user_id, _utc_bound(start_utc), _utc_bound(end_utc))
        return await self._select(user_id, _CLOSED_SQL, params)

    async def reminders_between(self, user_id: str, start: datetime, end: datetime) -> tuple[Task, ...]:
        """Open, not-deleted tasks whose ``reminder_at`` (stored as UTC text) is in ``[start, end)``, soonest first.
        Both bounds need a time zone; the reminders job reads its window through this."""
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("The reminder window needs a time zone.")
        params = (user_id, start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat())
        return await self._select(user_id, _REMINDERS_SQL, params)

    async def edit_steps(self, user_id: str, task_id: str, edit: Callable[[tuple[Step, ...]], tuple[Step, ...]],
                         *, taint: bool = False) -> Task | None:
        """Apply one checklist change (redesign P3) to the task's current steps and write them, a
        compare-and-set on ``updated_at``: when anything changed the task in between (a bot ticks a
        step while the user renames another), the change is applied again to the new steps, so
        neither is lost. ``taint`` marks the task "from web content" (a step a tainted run added).
        ``None``: no live task of the user's. ``edit``'s own errors propagate; ``StepsBusy`` after
        ``STEP_WRITE_ATTEMPTS`` lost races."""
        for _ in range(STEP_WRITE_ATTEMPTS):
            current = await self.get(user_id, task_id)
            if current is None:
                return None
            updated = replace(current, steps=edit(current.steps), tainted=current.tainted or taint,
                              updated_at=_now_iso())
            written = await self._write(updated, _STEP_COLUMNS, guard_sql=_SAME_VERSION_SQL,
                                        guard_params=(current.updated_at,))
            if written is not None:
                return written
        raise StepsBusy(STEPS_BUSY_TEXT)

    async def keep(self, user_id: str, task_id: str) -> Task | None:
        """The user vouches for a task (the Board's Keep): its taint bit is
        cleared. Only the HTTP route reaches this — no tool can launder a
        web-made row — and ``TaskPatch`` can't carry ``tainted`` either."""
        current = await self.get(user_id, task_id)
        if current is None:
            return None
        return await self._write(replace(current, tainted=False, updated_at=_now_iso()), ("tainted", "updated_at"))

    async def delete(self, user_id: str, task_id: str) -> bool:
        now = _now_iso()
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE tasks SET deleted_at = ?, updated_at = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (now, now, task_id, user_id),
            )
            await db.commit()
        return cursor.rowcount > 0

    async def restore(self, user_id: str, task_id: str) -> Task | None:
        """Undo a delete: the same task, its comments and expenses with it. ``None`` when the id is not one of the
        user's deleted tasks. A project deleted meanwhile already unlinked it (``unlink_project``)."""
        now = _now_iso()
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE tasks SET deleted_at = NULL, updated_at = ? "
                "WHERE id = ? AND user_id = ? AND deleted_at IS NOT NULL",
                (now, task_id, user_id),
            )
            await db.commit()
        return await self.get(user_id, task_id) if cursor.rowcount > 0 else None

    async def unlink_project(self, user_id: str, project_id: str) -> int:
        """H9: a deleted project's tasks stay and lose the link and their
        budget slices (a slice is in the project's currency, H11). The same
        statement as ``ProjectStore``'s delete runs for ``tasks``: deleted
        tasks too, ``updated_at`` untouched. Returns how many of the user's
        tasks were unlinked."""
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE tasks SET project_id = NULL, allocated_budget = NULL WHERE user_id = ? AND project_id = ?",
                (user_id, project_id))
            await db.commit()
        return cursor.rowcount

    async def _write(self, task: Task, columns: tuple[str, ...], *, guard_sql: str = "",
                     guard_params: tuple = ()) -> Task | None:
        """Update exactly ``columns``. ``guard_sql`` is a literal, caller-fixed
        SQL fragment (never built from user input) that makes the UPDATE a
        compare-and-set against the row the caller already checked, so a
        racing write that no longer matches touches nothing; ``guard_params``
        fill its ``?`` marks. A new ``project_id`` is checked in the same
        session as the UPDATE."""
        dek = await get_user_dek(self._config, task.user_id)
        assignments = ", ".join(f"{_SQL_NAME.get(column, column)} = ?" for column in columns)
        async with db_session(self._config) as db:
            if "project_id" in columns:
                await require_project(db, task.user_id, task.project_id)
            cursor = await db.execute(
                f"UPDATE tasks SET {assignments} WHERE id = ? AND user_id = ? AND deleted_at IS NULL{guard_sql}",
                (*(_encode(task, column, dek) for column in columns), task.id, task.user_id, *guard_params),
            )
            await db.commit()
        return task if cursor.rowcount else None

    async def _select(self, user_id: str, where: str, params: tuple) -> tuple[Task, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_SELECT} FROM tasks {where}", params)).fetchall()
            if not rows:
                return ()
            marked = await imported_ids(db, user_id, "task", [row["id"] for row in rows])
        dek = await get_user_dek(self._config, user_id)
        return tuple(replace(task, imported_from=IMPORTED_FROM_LAZYCLAW) if task.id in marked else task
                     for task in (_row_to_task(row, dek) for row in rows))
