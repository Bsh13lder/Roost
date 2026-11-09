"""The teach migration: one sealed step log per bot (docs/plans/2026-10-22-roost-teach.md)."""

from __future__ import annotations

import sqlite3

import aiosqlite
import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import MIGRATIONS, _apply_one, latest_version

_ROW = ("INSERT INTO teach_sessions (id, user_id, bot_id, steps, started_at) "
        "VALUES ('{id}', '{user}', '{bot}', 'enc', 't')")


def _teach_migration():
    return next(m for m in MIGRATIONS if m.name == "teach")


async def _db():
    cfg = load_config()
    await init_db(cfg)
    db_path = get_db_path(cfg)
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("INSERT INTO users (id, username, password_hash, encryption_salt) VALUES ('u', 'a', 'x', 's')")
    con.execute("INSERT INTO bots (id, user_id, name, name_key, job, instructions, avatar, created_at, updated_at) "
                "VALUES ('b', 'u', 'n', 'n', 'j', 'i', '{}', 't', 't')")
    con.commit()
    return db_path, con


async def test_the_teach_migration_adds_its_table():
    _, con = await _db()
    assert _teach_migration().version <= latest_version()
    columns = {row[1] for row in con.execute("PRAGMA table_info(teach_sessions)")}
    assert columns == {"id", "user_id", "bot_id", "steps", "step_count", "capped", "started_at"}
    assert con.execute("PRAGMA user_version").fetchone()[0] == latest_version()
    con.close()


async def test_one_session_per_bot_and_retiring_the_bot_removes_it():
    _, con = await _db()
    con.execute(_ROW.format(id="s1", user="u", bot="b"))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(_ROW.format(id="s2", user="u", bot="b"))
    con.execute("DELETE FROM bots WHERE id = 'b'")
    assert con.execute("SELECT count(*) FROM teach_sessions").fetchone()[0] == 0
    con.close()


async def test_teach_migration_is_idempotent():
    db_path, con = await _db()
    con.close()
    async with aiosqlite.connect(db_path) as db:
        await _apply_one(db, _teach_migration())
        await _apply_one(db, _teach_migration())
