"""Migrations from the deployed Night-1 schema (version 0) with live rows in it.

The live gateway's ``~/Roost/data/roost.db`` was created from
``tests/fixtures/schema_v0.sql`` (frozen from commit 9903514). These tests
rebuild exactly that database — one row in every table — in the
tripwire's temp data dir, then run ``init_db`` and check nothing was lost.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import roost.db.migrations as migrations_module
from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import MIGRATIONS, Migration, MigrationError, latest_version

_V0_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v0.sql"
_NOW = "2026-10-13T08:00:00+00:00"
_TABLES = ("users", "sessions", "bots", "threads", "messages", "events", "audit")
_AVATAR = '{"shape": "round", "color": "#22c55e", "badge": "none"}'


def _seed_v0_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(_V0_SCHEMA.read_text())
        con.execute(
            "INSERT INTO users (id, username, password_hash, encryption_salt) VALUES ('u1','alice','h','s')"
        )
        con.execute("INSERT INTO sessions (id, user_id, expires_at) VALUES ('s1','u1','2099-01-01T00:00:00+00:00')")
        con.execute(
            "INSERT INTO bots (id, user_id, name, name_key, job, instructions, avatar, status, created_at, updated_at) "
            "VALUES ('b1','u1','enc:x','k1','enc:x','enc:x',?,'resting',?,?)",
            (_AVATAR, _NOW, _NOW),
        )
        con.execute(
            "INSERT INTO threads (id, user_id, bot_id, title, kind, created_at, updated_at) "
            "VALUES ('t1','u1','b1',NULL,'chat',?,?)",
            (_NOW, _NOW),
        )
        con.execute(
            "INSERT INTO messages (id, user_id, thread_id, role, body, tainted, seq, created_at) "
            "VALUES ('m1','u1','t1','user','enc:x',0,1,?)",
            (_NOW,),
        )
        con.execute("INSERT INTO events (user_id, kind, payload, created_at) VALUES ('u1','message','enc:x',?)", (_NOW,))
        con.execute(
            "INSERT INTO audit (user_id, bot_id, action, decision, detail, created_at) "
            "VALUES ('u1','b1','open_page','do','enc:x',?)",
            (_NOW,),
        )
        con.commit()
    finally:
        con.close()


def _query(db_path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def _counts(db_path: Path) -> dict[str, int]:
    return {table: _query(db_path, f"SELECT COUNT(*) FROM {table}")[0][0] for table in _TABLES}


def _version(db_path: Path) -> int:
    return _query(db_path, "PRAGMA user_version")[0][0]


def _columns(db_path: Path, table: str) -> dict[str, tuple]:
    return {row[1]: row for row in _query(db_path, f"PRAGMA table_info({table})")}


@pytest.fixture
def seeded_v0():
    cfg = load_config()
    db_path = get_db_path(cfg)
    _seed_v0_database(db_path)
    assert _version(db_path) == 0
    return cfg, db_path


def test_versions_are_consecutive_from_one():
    assert [m.version for m in MIGRATIONS] == list(range(1, len(MIGRATIONS) + 1))
    assert latest_version() == MIGRATIONS[-1].version


async def test_v0_database_migrates_to_latest_and_keeps_every_row(seeded_v0):
    cfg, db_path = seeded_v0
    await init_db(cfg)
    assert _version(db_path) == latest_version()
    assert _counts(db_path) == dict.fromkeys(_TABLES, 1)


async def test_migrating_twice_is_a_no_op(seeded_v0):
    cfg, db_path = seeded_v0
    await init_db(cfg)
    await init_db(cfg)
    assert _version(db_path) == latest_version()
    assert _counts(db_path) == dict.fromkeys(_TABLES, 1)


async def test_existing_message_gets_kind_text_and_no_author(seeded_v0):
    cfg, db_path = seeded_v0
    await init_db(cfg)
    assert _query(db_path, "SELECT kind, author_bot_id FROM messages WHERE id = 'm1'") == [("text", None)]


async def test_existing_bot_is_on_duty_after_migrating(seeded_v0):
    cfg, db_path = seeded_v0
    await init_db(cfg)
    assert _query(db_path, "SELECT off_duty FROM bots WHERE id = 'b1'") == [(0,)]


async def test_every_work_item_carries_a_not_null_taint_flag(seeded_v0):
    cfg, db_path = seeded_v0
    await init_db(cfg)
    tainted = _columns(db_path, "work_items")["tainted"]
    assert tainted[3] == 1            # NOT NULL
    assert tainted[4] == "0"          # DEFAULT 0


async def test_a_pending_migration_backs_up_the_database_first(seeded_v0):
    cfg, db_path = seeded_v0
    await init_db(cfg)
    backups = sorted(db_path.parent.glob("roost.db.pre-v*.bak"))
    assert len(backups) == 1
    assert _version(backups[0]) == 0
    assert _counts(backups[0]) == dict.fromkeys(_TABLES, 1)


async def test_fresh_install_lands_on_latest_without_a_backup():
    cfg = load_config()
    await init_db(cfg)
    db_path = get_db_path(cfg)
    assert _version(db_path) == latest_version()
    assert list(db_path.parent.glob("roost.db.pre-v*.bak")) == []


async def test_existing_bot_is_not_the_main_bot_after_migrating(seeded_v0):
    cfg, db_path = seeded_v0
    await init_db(cfg)
    assert _query(db_path, "SELECT is_primary FROM bots WHERE id = 'b1'") == [(0,)]


async def test_two_main_bots_for_one_user_are_impossible(seeded_v0):
    cfg, db_path = seeded_v0
    await init_db(cfg)
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "INSERT INTO bots (id, user_id, name, name_key, job, instructions, avatar, status, created_at, updated_at) "
            "VALUES ('b2','u1','enc:y','k2','enc:y','enc:y',?,'resting',?,?)",
            (_AVATAR, _NOW, _NOW),
        )
        con.execute("UPDATE bots SET is_primary = 1 WHERE id = 'b1'")
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("UPDATE bots SET is_primary = 1 WHERE id = 'b2'")
    finally:
        con.close()


async def test_a_failing_migration_rolls_back_and_keeps_the_old_version(seeded_v0, monkeypatch):
    cfg, db_path = seeded_v0
    broken = (Migration(1, "broken", ("CREATE TABLE half_done (id TEXT)", "THIS IS NOT SQL")),)
    monkeypatch.setattr(migrations_module, "MIGRATIONS", broken)

    with pytest.raises(MigrationError, match="Migration 1 \\(broken\\)"):
        await init_db(cfg)

    assert _version(db_path) == 0
    assert _query(db_path, "SELECT name FROM sqlite_master WHERE name = 'half_done'") == []
    assert _counts(db_path) == dict.fromkeys(_TABLES, 1)


async def test_existing_thread_has_no_peer_after_migrating(seeded_v0):
    cfg, db_path = seeded_v0
    await init_db(cfg)
    assert _query(db_path, "SELECT kind, peer_bot_id FROM threads WHERE id = 't1'") == [("chat", None)]


async def test_v0_database_gains_rooms_tables(seeded_v0):
    cfg, db_path = seeded_v0
    await init_db(cfg)
    names = {row[0] for row in _query(db_path, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"rooms", "room_members", "work_items", "runs"} <= names
    assert _counts(db_path) == dict.fromkeys(_TABLES, 1)
