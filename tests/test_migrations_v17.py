"""Migrating from schema v17 (frozen before the LazyClaw migration) to v18: ``import_links``."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import apply_migrations, latest_version
from test_migrations_v15 import _EXPECTED as _V15_EXPECTED
from test_migrations_v15 import _ROWS as _V15_ROWS

_V17_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v17.sql"
_LINK_COLUMNS = {"user_id", "source", "kind", "old_id", "new_id", "run_id", "imported_at"}


def _query(db_path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


@pytest.fixture
def seeded_v17():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(_V17_SCHEMA.read_text())
        con.execute("PRAGMA user_version = 17")
        for statement in _V15_ROWS:
            con.execute(statement)
        con.commit()
    finally:
        con.close()
    return cfg, db_path


async def test_v17_upgrades_to_v18_additively(seeded_v17):
    cfg, db_path = seeded_v17
    await init_db(cfg)
    assert latest_version() >= 18
    assert _query(db_path, "PRAGMA user_version")[0][0] == latest_version()
    counts = {t: _query(db_path, f"SELECT COUNT(*) FROM {t}")[0][0] for t in _V15_EXPECTED}
    assert counts == _V15_EXPECTED
    assert {row[1] for row in _query(db_path, "PRAGMA table_info(import_links)")} == _LINK_COLUMNS
    assert _query(db_path, "SELECT COUNT(*) FROM import_links")[0][0] == 0


async def test_a_row_is_linked_once_per_user_source_kind_and_old_id(seeded_v17):
    cfg, db_path = seeded_v17
    await init_db(cfg)
    user = _query(db_path, "SELECT id FROM users LIMIT 1")[0][0]
    con = sqlite3.connect(db_path)
    try:
        insert = "INSERT INTO import_links VALUES (?, 'lazyclaw', 'task', ?, ?, 'run-1', 'n')"
        con.execute(insert, (user, "old-1", "new-1"))
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(insert, (user, "old-1", "new-2"))
        con.execute("INSERT INTO import_links VALUES (?, 'lazyclaw', 'expense', 'old-1', 'new-3', 'run-1', 'n')", (user,))
    finally:
        con.close()


async def test_migration_18_is_idempotent(seeded_v17):
    import aiosqlite

    cfg, db_path = seeded_v17
    await init_db(cfg)
    before = _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name")
    async with aiosqlite.connect(db_path) as db:
        assert await apply_migrations(db) == latest_version()
    assert _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name") == before
