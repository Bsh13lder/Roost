"""``--apply`` step 2: clear this user's tasks and money (user decision 2). Runs inside the caller's
transaction. Notes and documents stay; General stays (with its budget cleared, as its top-ups go)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class WipeResult:
    tasks: int = 0
    task_comments: int = 0
    expenses: int = 0
    topups: int = 0
    recurring: int = 0
    projects: int = 0


def _count(conn: sqlite3.Connection, sql: str, params: tuple) -> int:
    return conn.execute(sql, params).fetchone()[0]


def wipe_user_data(conn: sqlite3.Connection, user_id: str, general_id: str) -> WipeResult:
    """Delete in child-first order and return what went. Every statement names the user."""
    mine = (user_id,)
    result = WipeResult(
        tasks=_count(conn, "SELECT COUNT(*) FROM tasks WHERE user_id = ?", mine),
        task_comments=_count(conn, "SELECT COUNT(*) FROM task_comments WHERE user_id = ?", mine),
        expenses=_count(conn, "SELECT COUNT(*) FROM money_expenses WHERE user_id = ?", mine),
        topups=_count(conn, "SELECT COUNT(*) FROM money_topups WHERE user_id = ?", mine),
        recurring=_count(conn, "SELECT COUNT(*) FROM money_recurring WHERE user_id = ?", mine),
        projects=_count(conn, "SELECT COUNT(*) FROM money_projects WHERE user_id = ? AND id != ?", (user_id, general_id)),
    )
    for table in ("task_comments", "money_expenses", "money_topups", "money_recurring", "tasks"):
        conn.execute(f"DELETE FROM {table} WHERE user_id = ?", mine)
    conn.execute("DELETE FROM money_projects WHERE user_id = ? AND id != ?", (user_id, general_id))
    conn.execute("UPDATE money_projects SET budget = NULL, monthly_budget = NULL WHERE user_id = ? AND id = ?",
                 (user_id, general_id))
    return result
