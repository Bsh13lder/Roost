"""``--apply``: wipe, import and link in ONE transaction (plan section 5, user decisions 2-4).

Rows are trusted (``tainted = 0``). Every inserted row gets an ``import_links`` row. A re-run
skips what is linked and never wipes again (it would erase edits made since).
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable
from uuid import uuid4

from roost.migrate.lazyclaw import links
from roost.migrate.lazyclaw.budget import recompute_general_budget
from roost.migrate.lazyclaw.constants import (
    KIND_COMMENT, KIND_EXPENSE, KIND_PROJECT, KIND_RECURRING, KIND_TASK, KIND_TOPUP,
)
from roost.migrate.lazyclaw.models import Mapped
from roost.migrate.lazyclaw.writer_rows import (
    Sealer, insert_comment, insert_expense, insert_project, insert_recurring, insert_task, insert_topup,
)
from roost.migrate.lazyclaw.writer_wipe import WipeResult, wipe_user_data


class ImportRefused(RuntimeError):
    """The import cannot start (message is user-facing); nothing was written."""


@dataclass(frozen=True)
class ImportResult:
    run_id: str
    imported: dict[str, int] = field(default_factory=dict)
    already: int = 0
    wiped: WipeResult | None = None


def _comment_id(conn: sqlite3.Connection, wanted: str) -> str:
    taken = conn.execute("SELECT 1 FROM task_comments WHERE id = ?", (wanted,)).fetchone()
    return str(uuid4()) if taken else wanted


class _Run:
    """One import's bookkeeping: links each new row and counts it."""

    def __init__(self, conn: sqlite3.Connection, user_id: str, run_id: str, at: str) -> None:
        self.conn, self.user_id, self.run_id, self.at = conn, user_id, run_id, at
        self.counts: Counter[str] = Counter()
        self.already = 0

    def once(self, kind: str, old_id: str, new_id: str, insert: Callable[[], None]) -> None:
        if links.linked_id(self.conn, self.user_id, kind, old_id) is not None:
            self.already += 1
            return
        insert()
        links.add_link(self.conn, self.user_id, kind, old_id, new_id, self.run_id, self.at)
        self.counts[kind] += 1


def _import_all(run: _Run, s: Sealer, m: Mapped, *, wiped: bool) -> None:
    conn = run.conn
    for p in m.projects:
        if not p.is_general:
            run.once(KIND_PROJECT, p.id, p.target_id, lambda p=p: insert_project(conn, s, p))
        elif wiped and p.budget is not None:       # only the wiping run sets General's budget
            conn.execute("UPDATE money_projects SET budget = ? WHERE id = ? AND user_id = ?",
                         (s.money("money_projects", "budget", p.budget), p.target_id, s.user_id))
    for x in m.topups:
        run.once(KIND_TOPUP, x.id, x.id, lambda x=x: insert_topup(conn, s, x, x.id))
    for t in m.tasks:
        run.once(KIND_TASK, t.id, t.id, lambda t=t: insert_task(conn, s, t))
    for c in m.comments:
        new_id = _comment_id(conn, c.id)
        run.once(KIND_COMMENT, c.id, new_id, lambda c=c, n=new_id: insert_comment(conn, s, c, n))
    for r in m.recurring:
        run.once(KIND_RECURRING, r.id, r.id, lambda r=r: insert_recurring(conn, s, r))
    for e in m.expenses:
        run.once(KIND_EXPENSE, e.id, e.id, lambda e=e: insert_expense(conn, s, e))


def _added_general_topups(conn: sqlite3.Connection, user_id: str, run_id: str, general_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM money_topups WHERE user_id = ? AND project_id = ? AND id IN "
        "(SELECT new_id FROM import_links WHERE user_id = ? AND run_id = ? AND kind = ?) LIMIT 1",
        (user_id, general_id, user_id, run_id, KIND_TOPUP)).fetchone() is not None


def _check_general_budget(conn: sqlite3.Connection, m: Mapped, user_id: str) -> None:
    for p in m.projects:
        if p.is_general and p.budget is not None and p.budget != Decimal(0):
            row = conn.execute("SELECT currency FROM money_projects WHERE id = ? AND user_id = ?",
                               (p.target_id, user_id)).fetchone()
            if row is None or row[0] != p.currency:
                raise ImportRefused("LazyClaw's General project has a budget in a different currency than Roost's "
                                    "General. Nothing was changed.")


def apply_import(conn: sqlite3.Connection, dek: bytes, user_id: str, mapped: Mapped, *, run_id: str,
                 imported_at: str, general_id: str, wipe: bool = False) -> ImportResult:
    """Run the whole import on ``conn`` (autocommit mode; this function owns the transaction).

    ``general_id`` is Roost's General: the one project the wipe keeps. The wipe runs only when ``wipe`` is
    asked for, and at most once ever per account: never after a wipe (even an undone one) or any import.
    """
    if mapped.blocked:
        raise ImportRefused("The report has blocking anomalies. Fix them and run the dry run again.")
    conn.execute("BEGIN IMMEDIATE")
    try:
        _check_general_budget(conn, mapped, user_id)
        first = not links.wipe_done(conn, user_id) and not links.count_links(conn, user_id)
        wiped = wipe_user_data(conn, user_id, general_id) if wipe and first else None
        if wiped is not None:
            links.mark_wipe(conn, user_id, run_id, imported_at)
        run = _Run(conn, user_id, run_id, imported_at)
        _import_all(run, Sealer(dek, user_id), mapped, wiped=wiped is not None)
        if wiped is None and _added_general_topups(conn, user_id, run_id, general_id):
            recompute_general_budget(conn, dek, user_id, general_id)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return ImportResult(run_id=run_id, imported=dict(run.counts), already=run.already, wiped=wiped)
