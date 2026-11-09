"""General's budget is what its live top-up rows add up to, or none (decision H4)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.money.amounts import amount_text


def recompute_general_budget(conn: sqlite3.Connection, dek: bytes, user_id: str, general_id: str) -> None:
    aad = user_aad(user_id, "money_topups:amount")
    rows = conn.execute("SELECT amount FROM money_topups WHERE user_id = ? AND project_id = ? AND deleted_at IS NULL",
                        (user_id, general_id)).fetchall()
    total = sum((Decimal(decrypt_field(r[0], dek, aad) or "0") for r in rows), Decimal("0.00"))
    sealed = encrypt_field(amount_text(total), dek, user_aad(user_id, "money_projects:budget")) if rows else None
    conn.execute("UPDATE money_projects SET budget = ? WHERE id = ? AND user_id = ?", (sealed, general_id, user_id))
