"""``--undo <run_id>``: remove exactly the rows one import run made (plan section 5).

One transaction. A row changed since the import, or something the user added under an imported
project or task, stops the undo unless ``force``. The wipe that ``--apply`` did first cannot be
undone in place: the pre-import backup is the way back to it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from roost.migrate.lazyclaw import links
from roost.migrate.lazyclaw.budget import recompute_general_budget
from roost.migrate.lazyclaw.constants import (
    KIND_COMMENT, KIND_EXPENSE, KIND_PROJECT, KIND_RECURRING, KIND_TASK, KIND_TOPUP, UNDO_ORDER,
)

_TABLE = {KIND_PROJECT: "money_projects", KIND_TASK: "tasks", KIND_COMMENT: "task_comments",
          KIND_TOPUP: "money_topups", KIND_EXPENSE: "money_expenses", KIND_RECURRING: "money_recurring"}
_CHANGED_COLUMN = {KIND_COMMENT: "edited_at"}          # every other kind stamps updated_at
_CHILDREN = {   # a linked parent kind -> (child kind, child table, column naming the parent)
    KIND_PROJECT: ((KIND_EXPENSE, "money_expenses", "project_id"), (KIND_TOPUP, "money_topups", "project_id"),
                   (KIND_RECURRING, "money_recurring", "project_id"), (KIND_TASK, "tasks", "project_id")),
    KIND_TASK: ((KIND_COMMENT, "task_comments", "task_id"), (KIND_EXPENSE, "money_expenses", "task_id")),
}


class UndoError(RuntimeError):
    """Nothing to undo (message is user-facing)."""


class UndoRefused(UndoError):
    """Rows changed since the import; ``--force`` removes them anyway."""


@dataclass(frozen=True)
class UndoResult:
    removed: dict[str, int]


def _later(stamp: str | None, than: str) -> bool:
    if stamp is None:
        return False
    try:
        return datetime.fromisoformat(stamp) > datetime.fromisoformat(than)
    except ValueError:
        return True          # a stamp we cannot read is not proof of "untouched"


def _edited(conn: sqlite3.Connection, user_id: str, kind: str, new_id: str, imported_at: str) -> bool:
    table, column = _TABLE[kind], _CHANGED_COLUMN.get(kind, "updated_at")
    row = conn.execute(f"SELECT {column} FROM {table} WHERE id = ? AND user_id = ?", (new_id, user_id)).fetchone()
    if row is None:
        return False
    if kind == KIND_COMMENT:
        deleted = conn.execute("SELECT deleted_at FROM task_comments WHERE id = ? AND user_id = ?",
                               (new_id, user_id)).fetchone()
        return row[0] is not None or (deleted is not None and deleted[0] is not None)
    return _later(row[0], imported_at)


def _problems(conn: sqlite3.Connection, user_id: str, rows: list[tuple[str, str, str, str]]) -> list[str]:
    mine: dict[str, set[str]] = {kind: set() for kind in UNDO_ORDER}
    for kind, _old, new_id, _at in rows:
        mine[kind].add(new_id)
    problems = [f"{kind} {old}: changed since the import." for kind, old, new_id, at in rows
                if _edited(conn, user_id, kind, new_id, at)]
    for kind, parents in _CHILDREN.items():
        for child_kind, table, column in parents:
            for parent in sorted(mine[kind]):
                found = conn.execute(f"SELECT id FROM {table} WHERE user_id = ? AND {column} = ?",
                                     (user_id, parent)).fetchall()
                if any(r[0] not in mine[child_kind] for r in found):
                    problems.append(f"{kind} {parent}: has {child_kind}s that were added after the import.")
    return problems


def _delete(conn: sqlite3.Connection, user_id: str, rows: list[tuple[str, str, str, str]]) -> dict[str, int]:
    removed: dict[str, int] = {}
    for kind in UNDO_ORDER:
        ids = [new_id for k, _old, new_id, _at in rows if k == kind]
        for new_id in ids:
            conn.execute(f"DELETE FROM {_TABLE[kind]} WHERE id = ? AND user_id = ?", (new_id, user_id))
        if ids:
            removed[kind] = len(ids)
    return removed


def undo_run(conn: sqlite3.Connection, dek: bytes, user_id: str, run_id: str, *, general_id: str,
             force: bool = False) -> UndoResult:
    """``conn`` is in autocommit mode; this function owns the transaction."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        rows = links.run_links(conn, user_id, run_id)
        if not rows:
            raise UndoError(f"There is no import run called {run_id} for this account.")
        problems = [] if force else _problems(conn, user_id, rows)
        if problems:
            raise UndoRefused("Not undone, because " + " ".join(problems[:8]) + " Use --force to remove them too.")
        touches_general = conn.execute(
            "SELECT 1 FROM money_topups WHERE user_id = ? AND project_id = ? AND id IN "
            "(SELECT new_id FROM import_links WHERE user_id = ? AND run_id = ? AND kind = 'topup') LIMIT 1",
            (user_id, general_id, user_id, run_id)).fetchone()
        removed = _delete(conn, user_id, rows)
        links.drop_run(conn, user_id, run_id)
        if touches_general:
            recompute_general_budget(conn, dek, user_id, general_id)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return UndoResult(removed=removed)
