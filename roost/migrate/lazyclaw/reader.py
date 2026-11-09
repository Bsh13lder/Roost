"""Read one LazyClaw user's rows from the snapshot and decrypt their text fields (strict)."""

from __future__ import annotations

import json
import sqlite3

from roost.migrate.lazyclaw.models import LazyData, Row
from roost.migrate.lazyclaw.old_crypto import OldKeys

# table -> encrypted text columns (plan section 0)
_SEALED = {
    "tasks": ("title", "description", "category", "tags", "steps", "comments", "progress_log"),
    "projects": ("name", "description"),
    "project_expenses": ("description", "vendor", "notes"),
    "recurring_expenses": ("description", "vendor"),
    "budget_entries": ("source",),
}
_TIMEZONE_KEYS = ("timezone", "tz")


def _rows(conn: sqlite3.Connection, table: str, keys: OldKeys) -> tuple[Row, ...]:
    cursor = conn.execute(f'SELECT * FROM "{table}" WHERE user_id = ? ORDER BY id', (keys.user_id,))
    names = [d[0] for d in cursor.description]
    sealed = _SEALED[table]
    out: list[Row] = []
    for values in cursor.fetchall():
        row = dict(zip(names, values))
        for column in sealed:
            if column in row:
                row[column] = keys.decrypt(row[column], f"{table}.{row['id']}.{column}", f"{table}:{column}")
        out.append(row)
    return tuple(out)


def _timezone(conn: sqlite3.Connection, user_id: str) -> str | None:
    row = conn.execute("SELECT settings FROM users WHERE id = ?", (user_id,)).fetchone()
    try:
        settings = json.loads(row[0] or "{}") if row else {}
    except json.JSONDecodeError:
        return None
    value = next((settings.get(k) for k in _TIMEZONE_KEYS if isinstance(settings, dict) and settings.get(k)), None)
    return str(value) if value else None


def read_lazyclaw(conn: sqlite3.Connection, keys: OldKeys) -> LazyData:
    return LazyData(
        tasks=_rows(conn, "tasks", keys), projects=_rows(conn, "projects", keys),
        expenses=_rows(conn, "project_expenses", keys), topups=_rows(conn, "budget_entries", keys),
        recurring=_rows(conn, "recurring_expenses", keys), settings_timezone=_timezone(conn, keys.user_id),
    )
