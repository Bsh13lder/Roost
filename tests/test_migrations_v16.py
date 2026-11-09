"""Migrating from the schema the live gateway runs at the start of Tasks & Money polish (version 16).

``tests/fixtures/schema_v16.sql`` was frozen by Tasks & Money polish Task 2. The next migration (v17, by
the controller's amendment S) adds ``tasks.starred`` and ``tasks.estimate``, the ``money_recurring`` table,
and ``money_expenses.recurring_id`` / ``occurrence`` with their unique index."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import apply_migrations, latest_version
from test_migrations_v15 import _EXPECTED as _V15_EXPECTED
from test_migrations_v15 import _ROWS as _V15_ROWS

_V16_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v16.sql"
_RECURRING_COLUMNS = {"id", "user_id", "project_id", "amount", "currency", "description", "vendor", "cadence",
                      "anchor_day", "next_due", "ends_on", "created_at", "updated_at", "deleted_at",
                      "created_by_bot", "tainted"}


def _query(db_path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def _columns(db_path: Path, table: str) -> set[str]:
    return {row[1] for row in _query(db_path, f"PRAGMA table_info({table})")}


@pytest.fixture
def seeded_v16():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(_V16_SCHEMA.read_text())
        con.execute("PRAGMA user_version = 16")
        for statement in _V15_ROWS:
            con.execute(statement)
        con.commit()
    finally:
        con.close()
    return cfg, db_path


async def test_v16_upgrades_to_v17_additively(seeded_v16):
    cfg, db_path = seeded_v16
    await init_db(cfg)
    assert latest_version() >= 17
    assert _query(db_path, "PRAGMA user_version")[0][0] == latest_version()
    counts = {t: _query(db_path, f"SELECT COUNT(*) FROM {t}")[0][0] for t in _V15_EXPECTED}
    assert counts == _V15_EXPECTED
    assert {"starred", "estimate"} <= _columns(db_path, "tasks")
    assert {"recurring_id", "occurrence"} <= _columns(db_path, "money_expenses")
    assert _columns(db_path, "money_recurring") == _RECURRING_COLUMNS
    indexes = {row[0] for row in _query(db_path, "SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert {"idx_money_expenses_occurrence", "idx_money_recurring_project", "idx_money_recurring_due"} <= indexes


async def test_an_old_task_is_unstarred_with_no_estimate(seeded_v16):
    cfg, db_path = seeded_v16
    await init_db(cfg)
    rows = _query(db_path, "SELECT starred, estimate FROM tasks")
    assert rows and all(row == (0, None) for row in rows)


async def test_an_occurrence_is_made_once(seeded_v16):
    cfg, db_path = seeded_v16
    await init_db(cfg)
    con = sqlite3.connect(db_path)
    try:
        project = con.execute("SELECT id, user_id FROM money_projects LIMIT 1").fetchone()
        insert = ("INSERT INTO money_expenses (id, user_id, project_id, amount, spent_at, created_at, updated_at, "
                  "recurring_id, occurrence) VALUES (?, ?, ?, 'enc:a', '2026-11-01', 'n', 'n', ?, ?)")
        con.execute(insert, ("e-one", project[1], project[0], "r1", "2026-11-01"))
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(insert, ("e-two", project[1], project[0], "r1", "2026-11-01"))
        con.execute(insert.replace("'enc:a'", "'enc:b'"), ("e-three", project[1], project[0], None, None))
        con.execute(insert.replace("'enc:a'", "'enc:c'"), ("e-four", project[1], project[0], None, None))
    finally:
        con.close()


async def test_migration_17_is_idempotent(seeded_v16):
    import aiosqlite

    cfg, db_path = seeded_v16
    await init_db(cfg)
    before = _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name")
    async with aiosqlite.connect(db_path) as db:
        assert await apply_migrations(db) == latest_version()
    assert _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name") == before
