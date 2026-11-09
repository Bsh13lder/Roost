"""``import_links``: which Roost row came from which LazyClaw row, and in which run (schema v18)."""

from __future__ import annotations

import sqlite3

from roost.migrate.lazyclaw.constants import IMPORT_SOURCE, KIND_WIPE


def linked_id(conn: sqlite3.Connection, user_id: str, kind: str, old_id: str) -> str | None:
    row = conn.execute(
        "SELECT new_id FROM import_links WHERE user_id = ? AND source = ? AND kind = ? AND old_id = ?",
        (user_id, IMPORT_SOURCE, kind, old_id),
    ).fetchone()
    return None if row is None else row[0]


def add_link(conn: sqlite3.Connection, user_id: str, kind: str, old_id: str, new_id: str, run_id: str,
             imported_at: str) -> None:
    conn.execute("INSERT INTO import_links (user_id, source, kind, old_id, new_id, run_id, imported_at) "
                 "VALUES (?,?,?,?,?,?,?)", (user_id, IMPORT_SOURCE, kind, old_id, new_id, run_id, imported_at))


def count_links(conn: sqlite3.Connection, user_id: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM import_links WHERE user_id = ? AND source = ? AND kind != ?",
                        (user_id, IMPORT_SOURCE, KIND_WIPE)).fetchone()[0]


def wipe_done(conn: sqlite3.Connection, user_id: str) -> bool:
    """True once a wipe has ever run for this account (the marker is kept even after ``--undo``)."""
    return conn.execute("SELECT 1 FROM import_links WHERE user_id = ? AND source = ? AND kind = ?",
                        (user_id, IMPORT_SOURCE, KIND_WIPE)).fetchone() is not None


def mark_wipe(conn: sqlite3.Connection, user_id: str, run_id: str, imported_at: str) -> None:
    add_link(conn, user_id, KIND_WIPE, KIND_WIPE, KIND_WIPE, run_id, imported_at)


def run_links(conn: sqlite3.Connection, user_id: str, run_id: str) -> list[tuple[str, str, str, str]]:
    """``(kind, old_id, new_id, imported_at)`` for one run."""
    return [tuple(r) for r in conn.execute(
        "SELECT kind, old_id, new_id, imported_at FROM import_links WHERE user_id = ? AND source = ? AND run_id = ? "
        "AND kind != ?", (user_id, IMPORT_SOURCE, run_id, KIND_WIPE)).fetchall()]


def drop_run(conn: sqlite3.Connection, user_id: str, run_id: str) -> None:
    conn.execute("DELETE FROM import_links WHERE user_id = ? AND source = ? AND run_id = ? AND kind != ?",
                 (user_id, IMPORT_SOURCE, run_id, KIND_WIPE))
