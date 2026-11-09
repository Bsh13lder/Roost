"""The Sign-in card's migration (one step, the next version after Skills; the chief may renumber it at merge)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import aiosqlite

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import MIGRATIONS, _apply_one, latest_version

_NAME = "sign-in card"


def _query(db_path: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _columns(db_path: Path, table: str) -> dict[str, tuple]:
    return {row[1]: row for row in _query(db_path, f"PRAGMA table_info({table})")}


def _migration():
    return next(m for m in MIGRATIONS if m.name == _NAME)


def test_the_sign_in_migration_comes_after_skills():
    skills = next(m for m in MIGRATIONS if m.name == "skills")
    assert _migration().version > skills.version
    assert _migration().version <= latest_version()


async def test_it_adds_the_sign_in_flag_the_kept_flag_and_the_pending_clear():
    await init_db(load_config())
    db_path = get_db_path(load_config())
    stuck = _columns(db_path, "stuck_cards")
    logins = _columns(db_path, "site_logins")
    assert stuck["sign_in"][4] == "0" and stuck["sign_in"][3] == 1         # default 0, NOT NULL
    assert logins["kept"][4] == "1" and logins["kept"][3] == 1             # default 1 (older rows were kept)
    assert "clear_after_item_id" in logins
    indexes = {row[0] for row in _query(db_path, "SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert "idx_site_logins_pending" in indexes


async def test_it_is_idempotent():
    await init_db(load_config())
    db_path = get_db_path(load_config())
    async with aiosqlite.connect(db_path) as db:
        await _apply_one(db, _migration())
        await _apply_one(db, _migration())
    assert "kept" in _columns(db_path, "site_logins")
