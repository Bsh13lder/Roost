"""Migrating from the schema the live gateway runs at the start of polish R1 (version 15).

``tests/fixtures/schema_v15.sql`` was frozen by polish R1 Task 1. v16 only adds ``bots.group_label``."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import apply_migrations, latest_version
from test_migrations_v8 import _NOW
from test_migrations_v14 import _EXPECTED as _V14_EXPECTED
from test_migrations_v14 import _ROWS as _V14_ROWS

_V15_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v15.sql"
_ROWS = (
    *_V14_ROWS,
    "INSERT INTO memories (id, user_id, bot_id, scope, kind, text, source, fingerprint, created_at, updated_at) "
    f"VALUES ('m1','u1',NULL,'*','fact','enc:m','user','fp','{_NOW}','{_NOW}')",
    "INSERT INTO chat_summaries (id, user_id, thread_id, upto_message_id, upto_created_at, text, created_at) "
    f"VALUES ('s1','u1','t1','m','{_NOW}','enc:s','{_NOW}')",
)
_EXPECTED = {**_V14_EXPECTED, "memories": 1, "chat_summaries": 1}


def _query(db_path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def _counts(db_path: Path) -> dict[str, int]:
    return {table: _query(db_path, f"SELECT COUNT(*) FROM {table}")[0][0] for table in _EXPECTED}


@pytest.fixture
def seeded_v15():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(_V15_SCHEMA.read_text())
        con.execute("PRAGMA user_version = 15")
        for statement in _ROWS:
            con.execute(statement)
        con.commit()
    finally:
        con.close()
    return cfg, db_path


async def test_v16_adds_bots_group_label_and_keeps_every_row(seeded_v15):
    cfg, db_path = seeded_v15
    await init_db(cfg)
    assert latest_version() >= 16
    assert _query(db_path, "PRAGMA user_version")[0][0] == latest_version()
    assert _counts(db_path) == _EXPECTED
    assert "group_label" in {row[1] for row in _query(db_path, "PRAGMA table_info(bots)")}


async def test_an_old_bot_has_no_group(seeded_v15):
    cfg, db_path = seeded_v15
    await init_db(cfg)
    rows = _query(db_path, "SELECT group_label FROM bots")
    assert rows and all(row[0] is None for row in rows)


async def test_migration_16_is_idempotent(seeded_v15):
    import aiosqlite

    cfg, db_path = seeded_v15
    await init_db(cfg)
    before = _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name")
    async with aiosqlite.connect(db_path) as db:
        assert await apply_migrations(db) == latest_version()
    assert _query(db_path, "PRAGMA user_version")[0][0] == latest_version()
    assert _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name") == before
