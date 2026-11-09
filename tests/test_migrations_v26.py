"""Migrating from schema v25 (frozen before Skills) to v26."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import aiosqlite
import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import MIGRATIONS, _apply_one, latest_version

_V25_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v25.sql"

_SKILL = ("INSERT INTO skills (id, user_id, name, use_when, body, name_key, origin, created_at, updated_at) "
          "VALUES ('{id}', '{user}', 'enc', 'enc', 'enc', '{key}', 'user', 't', 't')")
_OFF = "INSERT INTO bot_skill_off (user_id, bot_id, skill_id, created_at) VALUES ('u', 'b', 's1', 't')"
_PROPOSAL = ("INSERT INTO skill_proposals (id, user_id, bot_id, skill_id, action, payload, base_revision, state, "
             "thread_id, created_at) VALUES ('sp1', 'u', 'b', 's1', 'change', 'enc', 1, 'open', 't1', 't')")


def _query(db_path: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _seed_v25():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.executescript(_V25_SCHEMA.read_text())
        con.execute("INSERT INTO users (id, username, password_hash, encryption_salt) VALUES ('u', 'a', 'x', 's')")
        con.execute("INSERT INTO users (id, username, password_hash, encryption_salt) VALUES ('u2', 'b', 'x', 's')")
        con.execute("INSERT INTO bots (id, user_id, name, name_key, job, instructions, avatar, created_at, updated_at) "
                    "VALUES ('b', 'u', 'n', 'n', 'j', 'i', '{}', 't', 't')")
        con.execute("INSERT INTO threads (id, user_id, bot_id, created_at, updated_at) VALUES ('t1', 'u', 'b', 't', 't')")
        con.execute("INSERT INTO routines (id, user_id, bot_id, thread_id, name, instructions, schedule, created_by, "
                    "created_at, updated_at) VALUES ('r1', 'u', 'b', 't1', 'enc', 'enc', 'enc', 'user', 't', 't')")
        con.execute("PRAGMA user_version = 25")
        con.commit()
    finally:
        con.close()
    return cfg, db_path


def _columns(db_path: Path, table: str) -> set[str]:
    return {row[1] for row in _query(db_path, f"PRAGMA table_info({table})")}


def _indexes(db_path: Path) -> set[str]:
    return {row[0] for row in _query(db_path, "SELECT name FROM sqlite_master WHERE type = 'index'")}


def _con(db_path: Path, *statements: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    for sql in statements:
        con.execute(sql)
    return con


def test_v25_fixture_matches_the_frozen_schema():
    text = _V25_SCHEMA.read_text()
    assert "CREATE TABLE routines" in text
    assert "full_limit_until" in text
    assert "CREATE TABLE skills" not in text
    assert "skill_proposals" not in text


async def test_v26_adds_the_skill_tables_and_indexes():
    _, db_path = _seed_v25()
    await init_db(load_config())
    assert latest_version() >= 26
    assert _query(db_path, "PRAGMA user_version")[0][0] == latest_version()
    assert _columns(db_path, "skills") == {
        "id", "user_id", "name", "use_when", "body", "name_key", "origin", "tainted", "created_by_bot",
        "revision", "created_at", "updated_at"}
    assert _columns(db_path, "bot_skill_off") == {"user_id", "bot_id", "skill_id", "created_at"}
    assert _columns(db_path, "skill_proposals") == {
        "id", "user_id", "bot_id", "skill_id", "action", "payload", "base_revision", "tainted", "from_routine",
        "state", "thread_id", "message_id", "created_at", "decided_at"}
    assert {"idx_skills_name", "idx_skill_proposals_open"} <= _indexes(db_path)


async def test_v26_is_idempotent():
    _, db_path = _seed_v25()
    await init_db(load_config())
    v26 = next(m for m in MIGRATIONS if m.version == 26)
    async with aiosqlite.connect(db_path) as db:
        await _apply_one(db, v26)
        await _apply_one(db, v26)
    assert _query(db_path, "PRAGMA user_version")[0][0] == 26


async def test_a_v25_database_upgrades_with_its_rows_intact():
    _, db_path = _seed_v25()
    await init_db(load_config())
    for table in ("users", "bots", "threads", "routines"):
        assert _query(db_path, f"SELECT count(*) FROM {table}")[0][0] >= 1
    assert _query(db_path, "SELECT id FROM routines") == [("r1",)]


async def test_skill_name_key_is_unique_per_user():
    _, db_path = _seed_v25()
    await init_db(load_config())
    con = _con(db_path, _SKILL.format(id="s1", user="u", key="k"), _SKILL.format(id="s2", user="u2", key="k"))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(_SKILL.format(id="s3", user="u", key="k"))
    con.close()


async def test_deleting_a_skill_cascades_its_off_rows_and_proposals():
    _, db_path = _seed_v25()
    await init_db(load_config())
    con = _con(db_path, _SKILL.format(id="s1", user="u", key="k"), _OFF, _PROPOSAL)
    con.execute("DELETE FROM skills WHERE id = 's1' AND user_id = 'u'")
    assert con.execute("SELECT count(*) FROM bot_skill_off").fetchone() == (0,)
    assert con.execute("SELECT count(*) FROM skill_proposals").fetchone() == (0,)
    con.close()


async def test_retiring_a_bot_cascades_its_off_rows():
    _, db_path = _seed_v25()
    await init_db(load_config())
    con = _con(db_path, _SKILL.format(id="s1", user="u", key="k"), _OFF)
    con.execute("DELETE FROM bots WHERE id = 'b' AND user_id = 'u'")
    assert con.execute("SELECT count(*) FROM bot_skill_off").fetchone() == (0,)
    assert con.execute("SELECT count(*) FROM skills").fetchone() == (1,)
    con.close()
