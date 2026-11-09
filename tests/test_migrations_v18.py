"""Migrating from schema v18 (frozen before pinned bots) to v19: ``bots.pinned`` and ``bots.pinned_at``."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import apply_migrations, latest_version
from test_migrations_v15 import _EXPECTED as _V15_EXPECTED
from test_migrations_v15 import _ROWS as _V15_ROWS

_V18_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v18.sql"


def _query(db_path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


@pytest.fixture
def seeded_v18():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(_V18_SCHEMA.read_text())
        con.execute("PRAGMA user_version = 18")
        for statement in _V15_ROWS:
            con.execute(statement)
        con.commit()
    finally:
        con.close()
    return cfg, db_path


async def test_v18_upgrades_to_v19_additively(seeded_v18):
    cfg, db_path = seeded_v18
    await init_db(cfg)
    assert latest_version() >= 19
    assert _query(db_path, "PRAGMA user_version")[0][0] == latest_version()
    counts = {t: _query(db_path, f"SELECT COUNT(*) FROM {t}")[0][0] for t in _V15_EXPECTED}
    assert counts == _V15_EXPECTED
    columns = {row[1] for row in _query(db_path, "PRAGMA table_info(bots)")}
    assert {"pinned", "pinned_at"} <= columns


async def test_existing_bots_start_unpinned(seeded_v18):
    cfg, db_path = seeded_v18
    await init_db(cfg)
    rows = _query(db_path, "SELECT is_primary, pinned FROM bots")
    assert all(pinned == 0 for _primary, pinned in rows)


async def test_migration_19_is_idempotent(seeded_v18):
    import aiosqlite

    cfg, db_path = seeded_v18
    await init_db(cfg)
    before = _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name")
    async with aiosqlite.connect(db_path) as db:
        assert await apply_migrations(db) == latest_version()
    assert _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name") == before
