"""Schema v47 (docs/plans/2026-11-10-roost-self-healing.md): a routine's last error (a fixed word and a time, both
plaintext, no user content) and a watch's failed-check fold (``fail_count``, ``fail_run_id``)."""

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


def test_migration_47_is_listed_once_and_the_importer_knows_it():
    versions = [m.version for m in MIGRATIONS]
    assert versions.count(47) == 1 and versions == sorted(versions)
    assert 47 in SUPPORTED_SCHEMA_VERSIONS and latest_version() in SUPPORTED_SCHEMA_VERSIONS


async def test_a_fresh_database_has_the_last_error_and_fail_columns(cfg):
    assert {"last_error_kind", "last_error_at"} <= _columns("routines")
    assert {"fail_count", "fail_run_id"} <= _columns("routine_watches")


async def test_applying_v47_twice_is_harmless(cfg):
    from roost.db.migrations import _apply_one
    import aiosqlite

    (v47,) = [m for m in MIGRATIONS if m.version == 47]
    async with aiosqlite.connect(get_db_path(cfg)) as db:
        await _apply_one(db, v47)
    assert {"last_error_kind", "last_error_at"} <= _columns("routines")
