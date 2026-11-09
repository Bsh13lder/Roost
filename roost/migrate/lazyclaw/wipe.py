"""Count (never delete) what ``--apply`` would clear first. Read-only on Roost's database."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote

from roost.migrate.lazyclaw.report import WipeCounts

_TABLES = {
    "tasks": "tasks", "task_comments": "task_comments", "expenses": "money_expenses",
    "topups": "money_topups", "recurring": "money_recurring", "projects": "money_projects",
}


def _count(conn: sqlite3.Connection, table: str, user_id: str) -> int:
    return conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE user_id = ?', (user_id,)).fetchone()[0]


def count_wipe(roost_db: Path | None) -> WipeCounts:
    if roost_db is None or not roost_db.is_file():
        return WipeCounts(available=False)
    conn = sqlite3.connect(f"file:{quote(str(roost_db.resolve()))}?mode=ro", uri=True)
    try:
        users = conn.execute("SELECT id FROM users").fetchall()
        if len(users) != 1:
            return WipeCounts(available=False)
        counts = {key: _count(conn, table, users[0][0]) for key, table in _TABLES.items()}
    except sqlite3.Error:
        return WipeCounts(available=False)
    finally:
        conn.close()
    counts["projects"] = max(counts["projects"] - 1, 0)  # General stays, if there is one (the dry run cannot tell)
    return WipeCounts(available=True, **counts)


def exact_wipe_counts(conn: sqlite3.Connection, user_id: str, general_id: str) -> WipeCounts:
    """What ``--apply`` will clear, exactly (General is known by now). Read only."""
    counts = {key: _count(conn, table, user_id) for key, table in _TABLES.items() if key != "projects"}
    counts["projects"] = conn.execute("SELECT COUNT(*) FROM money_projects WHERE user_id = ? AND id != ?",
                                      (user_id, general_id)).fetchone()[0]
    return WipeCounts(available=True, **counts)
