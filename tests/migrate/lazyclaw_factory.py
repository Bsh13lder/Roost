"""Builds synthetic, LazyClaw-shaped SQLite databases in a temp dir. Tests only.

Never points at a real path: ``refuse_real_paths`` is the tripwire every builder calls.
"""

from __future__ import annotations

import base64
import os
import sqlite3
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from roost.crypto.encryption import derive_key, wrap_dek

SHAPE_SQL = Path(__file__).resolve().parents[1] / "fixtures" / "lazyclaw_shape.sql"
TEST_SECRET = "test-secret-not-real"
OLD_USER_ID = "old-user-1"
OLD_USERNAME = "olduser"
_FORBIDDEN = ("lazyclaw/data", str(Path.home() / "Roost"))
_WRAP_ITERATIONS = 600_000


def refuse_real_paths(path: Path) -> None:
    text = str(path.resolve())
    if any(bad in text for bad in _FORBIDDEN):
        raise RuntimeError(f"tripwire: tests must not touch {text}")


def enc_v1(plain: str, dek: bytes) -> str:
    nonce = os.urandom(12)
    ct = AESGCM(dek).encrypt(nonce, plain.encode(), None)
    return f"enc:v1:{base64.b64encode(nonce).decode()}:{base64.b64encode(ct).decode()}"


def wrapped_dek_for(dek: bytes, secret: str, user_id: str, salt: str) -> str:
    key = derive_key(secret + user_id, salt.encode(), _WRAP_ITERATIONS)
    return wrap_dek(dek, key)


def password_wrapped_dek(dek: bytes, password: str, salt: str) -> str:
    """LazyClaw register_user: enc:v1(hex(master_key)) under PBKDF2(password, salt, 100k)."""
    key = derive_key(password, salt.encode("utf-8"), 100_000)
    return enc_v1(dek.hex(), key)


def new_db(path: Path) -> sqlite3.Connection:
    refuse_real_paths(path)
    conn = sqlite3.connect(path)
    conn.executescript(SHAPE_SQL.read_text())
    return conn


def add_user(conn: sqlite3.Connection, *, dek: bytes, user_id: str = OLD_USER_ID,
             username: str = OLD_USERNAME, secret: str = TEST_SECRET, salt: str = "salt-1",
             settings: str = "{}", password: str | None = None, pw_dek: bytes | None = None) -> None:
    wrapped = wrapped_dek_for(dek, secret, user_id, salt)
    pw_wrapped = password_wrapped_dek(pw_dek or dek, password, salt) if password else None
    conn.execute(
        "INSERT INTO users (id, username, password_hash, encryption_salt, encrypted_dek, settings, "
        "password_encrypted_dek) VALUES (?,?,?,?,?,?,?)",
        (user_id, username, "x", salt, wrapped, settings, pw_wrapped))
    conn.commit()


def insert(conn: sqlite3.Connection, table: str, **cols: object) -> None:
    names = ", ".join(cols)
    marks = ", ".join("?" for _ in cols)
    conn.execute(f"INSERT INTO {table} ({names}) VALUES ({marks})", tuple(cols.values()))
    conn.commit()


SAMPLE_PASSWORD = "sample-password-not-real"
SAMPLE_DEK = bytes(range(10, 42))


def build_sample(path: Path) -> Path:
    """A small, fully synthetic LazyClaw account with enc:v1 text fields. Returns the path."""
    import json
    conn = new_db(path)
    e = lambda text: None if text is None else enc_v1(text, SAMPLE_DEK)  # noqa: E731
    add_user(conn, dek=SAMPLE_DEK, password=SAMPLE_PASSWORD, settings=json.dumps({"timezone": "Europe/Madrid"}))
    u = OLD_USER_ID
    insert(conn, "projects", id="pg", user_id=u, name=e("General"), name_key="general", budget=0.0)
    insert(conn, "projects", id="pk", user_id=u, name=e("Kitchen"), name_key="kitchen", budget=150.0,
           color="#FF0000", created_at="2026-02-01 10:00:00")
    insert(conn, "projects", id="pt", user_id=u, name=e("Trip to Lisbon"), name_key="trip to lisbon",
           budget=0.0, currency="USD", status="archived")
    insert(conn, "budget_entries", id="b1", user_id=u, project_id="pk", amount=100.0, source=e("savings"))
    steps = [{"id": "s1", "title": "Measure", "done": True}, {"id": "s2", "title": "Order", "done": False}]
    comments = [{"id": "c1", "ts": "2026-03-01T10:00:00+00:00", "author": "user", "text": "ok", "subtask_id": "s1"}]
    insert(conn, "tasks", id="t1", user_id=u, title=e("Buy kitchen tiles from the big shop"),
           category=e("Kitchen"), status="todo", allocated_budget=40.0, created_at="2026-03-01 09:00:00")
    insert(conn, "tasks", id="t2", user_id=u, title=e("Call plumber"), status="done",
           completed_at="2026-03-02 09:00:00", created_at="2026-03-01 09:00:00")
    insert(conn, "tasks", id="t3", user_id=u, title=e("Deleted one"), deleted_at="2026-03-03 00:00:00")
    insert(conn, "tasks", id="t4", user_id=u, title=e("Renew passport application"), category=e("Errands"),
           status="in_progress", steps=e(json.dumps(steps)), comments=e(json.dumps(comments)),
           progress_log=e(json.dumps([{"a": 1}, {"a": 2}])), created_at="2026-03-01 09:00:00")
    for eid, proj, amt, cur, st, desc in (
            ("e1", "pk", 25.5, "EUR", "posted", "Tiles"), ("e2", "pk", 10.0, "USD", "posted", "Tool"),
            ("e3", "pk", 5.0, "EUR", "void", "Oops"), ("e4", "pt", 20.0, "USD", "posted", "Hotel"),
            ("e5", "pg", 3.2, "EUR", "posted", "Coffee")):
        insert(conn, "project_expenses", id=eid, user_id=u, project_id=proj, amount=amt, currency=cur,
               status=st, description=e(desc), spent_at="2026-03-05", created_at="2026-03-05 08:00:00")
    insert(conn, "recurring_expenses", id="r1", user_id=u, project_id="pk", amount=9.99,
           description=e("Hosting"), cron_expression="0 0 1 * *")
    insert(conn, "recurring_expenses", id="r2", user_id=u, project_id="pk", amount=1.0,
           description=e("Odd"), cron_expression="*/5 * * * *")
    conn.close()
    return path
