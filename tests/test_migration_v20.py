"""Migrating from schema v19 (frozen before models and helpers) to v20."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import aiosqlite

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import apply_migrations, latest_version

_V19_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v19.sql"


def _query(db_path: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _seed_v19():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.executescript(_V19_SCHEMA.read_text())
        con.execute("PRAGMA user_version = 19")
        con.commit()
    finally:
        con.close()
    return cfg, db_path


async def test_v20_adds_effort_and_the_model_tables():
    cfg, db_path = _seed_v19()
    await init_db(cfg)
    assert latest_version() >= 20
    assert _query(db_path, "PRAGMA user_version")[0][0] == latest_version()
    assert "effort" in {row[1] for row in _query(db_path, "PRAGMA table_info(bots)")}
    assert {row[1] for row in _query(db_path, "PRAGMA table_info(seen_models)")} == {"model_id", "label", "first_seen_at"}
    assert {row[1] for row in _query(db_path, "PRAGMA table_info(model_notice_dismissals)")} == {
        "user_id", "model_id", "dismissed_at"}

    before = _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name")
    async with aiosqlite.connect(db_path) as db:
        assert await apply_migrations(db) == latest_version()
    assert _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name") == before
