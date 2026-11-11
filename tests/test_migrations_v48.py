"""Schema v48 (docs/plans/2026-11-11-roost-routine-finish.md): a finished routine's ``finished_at`` (plaintext
UTC time) and its sealed ``finished_reason`` (``routines:finished_reason``)."""

from __future__ import annotations

import sqlite3

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import MIGRATIONS, latest_version
from roost.migrate.lazyclaw.constants import SUPPORTED_SCHEMA_VERSIONS


def _columns(table: str) -> set[str]:
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        return {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
    finally:
        con.close()


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


def test_migration_48_is_listed_once_and_the_importer_knows_it():
    versions = [m.version for m in MIGRATIONS]
    assert versions.count(48) == 1 and versions == sorted(versions)
    assert 48 in SUPPORTED_SCHEMA_VERSIONS and latest_version() in SUPPORTED_SCHEMA_VERSIONS


async def test_a_fresh_database_has_the_finished_columns(cfg):
    assert {"finished_at", "finished_reason"} <= _columns("routines")


async def test_applying_v48_twice_is_harmless(cfg):
    import aiosqlite

    from roost.db.migrations import _apply_one

    (v48,) = [m for m in MIGRATIONS if m.version == 48]
    async with aiosqlite.connect(get_db_path(cfg)) as db:
        await _apply_one(db, v48)
    assert {"finished_at", "finished_reason"} <= _columns("routines")
