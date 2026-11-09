"""Migrating from the schema the live gateway runs at the start of memory (version 14).

``tests/fixtures/schema_v14.sql`` was frozen by memory Task 1. Rows go in every table the user's account
uses today (the v13 test's rows, plus a task comment). v15 only adds ``memories`` and ``chat_summaries``."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import apply_migrations, latest_version
from test_migrations_v8 import _NOW
from test_migrations_v13 import _EXPECTED as _V13_EXPECTED
from test_migrations_v13 import _ROWS as _V13_ROWS

_V14_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v14.sql"
_ROWS = (
    *_V13_ROWS,
    "INSERT INTO task_comments (id, user_id, task_id, step_id, author, body, created_at) "
    f"VALUES ('c1','u1','task3',NULL,'user','enc:c','{_NOW}')",
)
_EXPECTED = {**_V13_EXPECTED, "task_comments": 1}
_MEMORY_COLUMNS = {"id", "user_id", "bot_id", "scope", "kind", "text", "source", "created_by_bot", "importance",
                   "pinned", "tainted", "fingerprint", "created_at", "updated_at", "last_recalled_at",
                   "archived_at", "tags"}
_SUMMARY_COLUMNS = {"id", "user_id", "thread_id", "upto_message_id", "upto_created_at", "text", "created_at"}
_MEMORY = ("INSERT INTO memories (id, user_id, bot_id, scope, kind, text, source, fingerprint, created_at, "
           "updated_at) VALUES (?, 'u1', ?, ?, 'fact', 'enc:m', 'user', ?, ?, ?)")


def _query(db_path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def _counts(db_path: Path) -> dict[str, int]:
    return {table: _query(db_path, f"SELECT COUNT(*) FROM {table}")[0][0] for table in _EXPECTED}


def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _add_memory(con: sqlite3.Connection, memory_id: str, bot_id: str | None, scope: str, fingerprint: str) -> None:
    con.execute(_MEMORY, (memory_id, bot_id, scope, fingerprint, _NOW, _NOW))


@pytest.fixture
def seeded_v14():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(_V14_SCHEMA.read_text())
        con.execute("PRAGMA user_version = 14")
        for statement in _ROWS:
            con.execute(statement)
        con.commit()
    finally:
        con.close()
    return cfg, db_path


async def test_v15_adds_memories_and_chat_summaries_and_keeps_every_row(seeded_v14):
    cfg, db_path = seeded_v14
    await init_db(cfg)
    assert latest_version() >= 16
    assert _query(db_path, "PRAGMA user_version")[0][0] == latest_version()
    assert _counts(db_path) == _EXPECTED
    assert {row[1] for row in _query(db_path, "PRAGMA table_info(memories)")} == _MEMORY_COLUMNS
    assert {row[1] for row in _query(db_path, "PRAGMA table_info(chat_summaries)")} == _SUMMARY_COLUMNS
    indexes = {row[0] for row in _query(db_path, "SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert {"idx_memories_fingerprint", "idx_memories_scope", "idx_chat_summaries_thread"} <= indexes


async def test_the_shared_scope_is_unique_too(seeded_v14):
    cfg, db_path = seeded_v14
    await init_db(cfg)
    con = _connect(db_path)
    try:
        _add_memory(con, "m1", None, "*", "fp")
        with pytest.raises(sqlite3.IntegrityError):
            _add_memory(con, "m2", None, "*", "fp")
        _add_memory(con, "m3", "b1", "b1", "fp")
        _add_memory(con, "m4", "b2", "b2", "fp")
    finally:
        con.close()


async def test_retiring_a_bot_drops_its_memories_and_keeps_about_you(seeded_v14):
    cfg, db_path = seeded_v14
    await init_db(cfg)
    con = _connect(db_path)
    try:
        _add_memory(con, "m1", None, "*", "fp1")
        _add_memory(con, "m2", "b1", "b1", "fp2")
        con.execute("DELETE FROM bots WHERE id = 'b1'")
        assert con.execute("SELECT id FROM memories").fetchall() == [("m1",)]
    finally:
        con.close()


async def test_deleting_a_thread_drops_its_summaries(seeded_v14):
    cfg, db_path = seeded_v14
    await init_db(cfg)
    con = _connect(db_path)
    try:
        con.execute("INSERT INTO chat_summaries (id, user_id, thread_id, upto_message_id, upto_created_at, text, "
                    f"created_at) VALUES ('s1','u1','t1','m','{_NOW}','enc:s','{_NOW}')")
        assert con.execute("SELECT COUNT(*) FROM chat_summaries").fetchone() == (1,)
        con.execute("DELETE FROM threads WHERE id = 't1'")
        assert con.execute("SELECT COUNT(*) FROM chat_summaries").fetchone() == (0,)
    finally:
        con.close()


async def test_migration_15_is_idempotent(seeded_v14):
    import aiosqlite

    cfg, db_path = seeded_v14
    await init_db(cfg)
    before = _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name")
    async with aiosqlite.connect(db_path) as db:
        assert await apply_migrations(db) == latest_version()
    assert _query(db_path, "PRAGMA user_version")[0][0] == latest_version()
    assert _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name") == before
