"""Migrating from the schema the live gateway runs at the start of S1 (version 10).

``tests/fixtures/schema_v10.sql`` was frozen by S1 Task 2. Rows go in every
table the user's account uses today, including M2's notes and documents."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import latest_version
from test_migrations_v8 import _EXPECTED as _V8_EXPECTED
from test_migrations_v8 import _NOW, _ROWS as _V8_ROWS

_V10_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v10.sql"
_ROWS = (
    *_V8_ROWS,
    "INSERT INTO notes (id, user_id, title, title_key, content, created_at, updated_at, created_by_bot) "
    f"VALUES ('n1','u1','enc:t','tk','enc:c','{_NOW}','{_NOW}','b2')",
    "INSERT INTO documents (id, user_id, kind, title, payload, created_at, updated_at, created_by_bot) "
    f"VALUES ('d1','u1','doc','enc:t','enc:p','{_NOW}','{_NOW}','b2')",
)
_EXPECTED = {**_V8_EXPECTED, "notes": 1, "documents": 1}


def _query(db_path: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


@pytest.fixture
def seeded_v10():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(_V10_SCHEMA.read_text())
        con.execute("PRAGMA user_version = 10")
        for statement in _ROWS:
            con.execute(statement)
        con.commit()
    finally:
        con.close()
    return cfg, db_path


def _counts(db_path: Path) -> dict[str, int]:
    return {table: _query(db_path, f"SELECT COUNT(*) FROM {table}")[0][0] for table in _EXPECTED}


async def test_v10_database_migrates_to_latest_and_keeps_every_row(seeded_v10):
    cfg, db_path = seeded_v10
    await init_db(cfg)
    assert latest_version() >= 11
    assert _query(db_path, "PRAGMA user_version")[0][0] == latest_version()
    assert _counts(db_path) == _EXPECTED


async def test_existing_bots_have_notifications_on(seeded_v10):
    cfg, db_path = seeded_v10
    await init_db(cfg)
    assert _query(db_path, "SELECT id, notify FROM bots ORDER BY id") == [("b1", 1), ("b2", 1)]


async def test_migrating_twice_is_a_no_op_and_backs_up_once(seeded_v10):
    cfg, db_path = seeded_v10
    await init_db(cfg)
    await init_db(cfg)
    assert _counts(db_path) == _EXPECTED
    assert len(list(db_path.parent.glob(f"roost.db.pre-v{latest_version()}-*.bak"))) == 1
