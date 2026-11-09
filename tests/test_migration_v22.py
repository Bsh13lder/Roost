"""Migrating from schema v21 (frozen before day notes and pins) to v22."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import aiosqlite

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import apply_migrations, latest_version

_V21_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v21.sql"


def _query(db_path: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _seed_v21():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.executescript(_V21_SCHEMA.read_text())
        con.execute("INSERT INTO users (id, username, password_hash, encryption_salt) VALUES ('u', 'a', 'x', 's')")
        con.execute("INSERT INTO money_projects (id, user_id, name, name_key, currency, created_at, updated_at) "
                    "VALUES ('p', 'u', 'enc', 'k', 'EUR', 't', 't')")
        con.execute("PRAGMA user_version = 21")
        con.commit()
    finally:
        con.close()
    return cfg, db_path


async def test_v22_adds_day_notes_and_project_pins():
    cfg, db_path = _seed_v21()
    await init_db(cfg)
    assert latest_version() >= 22
    assert _query(db_path, "PRAGMA user_version")[0][0] == latest_version()
    columns = {row[1]: row for row in _query(db_path, "PRAGMA table_info(day_notes)")}
    assert set(columns) == {"id", "user_id", "day", "author_kind", "bot_id", "text", "created_at", "tainted"}
    assert columns["text"][3] == 1 and columns["tainted"][4] == "0"
    pins = {row[1]: row for row in _query(db_path, "PRAGMA table_info(money_projects)")}
    assert pins["pinned"][3] == 1 and pins["pinned"][4] == "0" and pins["pinned_at"][3] == 0
    assert _query(db_path, "SELECT pinned, pinned_at FROM money_projects") == [(0, None)]
    assert _query(db_path, "SELECT name FROM sqlite_master WHERE name = 'idx_day_notes_user_day'")


async def test_a_v21_database_upgrades_in_place():
    cfg, db_path = _seed_v21()
    await init_db(cfg)
    before = _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name")
    async with aiosqlite.connect(db_path) as db:
        assert await apply_migrations(db) == latest_version()
    assert _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name") == before


async def test_author_kind_allows_only_user_or_bot():
    cfg, db_path = _seed_v21()
    await init_db(cfg)
    con = sqlite3.connect(db_path)
    try:
        sql = ("INSERT INTO day_notes (id, user_id, day, author_kind, text, created_at) "
               "VALUES (?, 'u', '2026-10-21', ?, 'enc', 't')")
        con.execute(sql, ("a", "user"))
        try:
            con.execute(sql, ("b", "robot"))
        except sqlite3.IntegrityError:
            return
        raise AssertionError("an author kind other than user or bot was accepted")
    finally:
        con.close()
