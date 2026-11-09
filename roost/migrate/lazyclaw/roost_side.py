"""Facts about the Roost account the importer writes into (sync sqlite3, the caller's connection)."""

from __future__ import annotations

import sqlite3
from uuid import uuid4

from roost.constants import DEFAULT_PROJECT_COLOR, GENERAL_PROJECT_NAME
from roost.crypto.encryption import encrypt, user_aad
from roost.money.project_store import _name_key  # the one HMAC definition; the writer must match it exactly


class RoostAccountError(RuntimeError):
    """The Roost database is not in a shape the importer can use (message is user-facing)."""


def only_user_id(conn: sqlite3.Connection) -> str:
    rows = conn.execute("SELECT id FROM users").fetchall()
    if len(rows) != 1:
        raise RoostAccountError(f"Expected exactly one Roost account, found {len(rows)}. Nothing was changed.")
    return rows[0][0]


def main_bot_id(conn: sqlite3.Connection, user_id: str) -> str | None:
    row = conn.execute("SELECT id FROM bots WHERE user_id = ? AND is_primary = 1", (user_id,)).fetchone()
    return None if row is None else row[0]


def find_general(conn: sqlite3.Connection, dek: bytes, user_id: str) -> str | None:
    row = conn.execute("SELECT id FROM money_projects WHERE user_id = ? AND name_key = ? AND deleted_at IS NULL",
                       (user_id, _name_key(dek, GENERAL_PROJECT_NAME))).fetchone()
    return None if row is None else row[0]


def ensure_general(conn: sqlite3.Connection, dek: bytes, user_id: str, now: str) -> str:
    """General's id; General is made (as ``ProjectStore`` would) when the account has none yet.
    The caller owns the transaction."""
    found = find_general(conn, dek, user_id)
    if found is not None:
        return found
    project_id = str(uuid4())
    conn.execute(
        "INSERT INTO money_projects (id, user_id, name, name_key, budget, currency, status, color, created_at, "
        "updated_at, tainted) VALUES (?,?,?,?,NULL,'EUR','active',?,?,?,0)",
        (project_id, user_id, encrypt(GENERAL_PROJECT_NAME, dek, user_aad(user_id, "money_projects:name")),
         _name_key(dek, GENERAL_PROJECT_NAME), DEFAULT_PROJECT_COLOR, now, now))
    return project_id


def general_currency(conn: sqlite3.Connection, user_id: str, general_id: str) -> str:
    row = conn.execute("SELECT currency FROM money_projects WHERE id = ? AND user_id = ?",
                       (general_id, user_id)).fetchone()
    return "EUR" if row is None else row[0]
