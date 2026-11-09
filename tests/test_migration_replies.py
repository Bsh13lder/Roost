"""The replies migration: reply quotes on messages and the instruction_proposals table (one migration, the latest)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import aiosqlite
import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import MIGRATIONS, _apply_one, latest_version

_PROPOSAL = ("INSERT INTO instruction_proposals (id, user_id, bot_id, payload, state, thread_id, created_at) "
             "VALUES ('p1', 'u', 'b', 'enc', '{state}', 't1', 't')")


def _query(db_path: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _columns(db_path: Path, table: str) -> set[str]:
    return {row[1] for row in _query(db_path, f"PRAGMA table_info({table})")}


def _replies_migration():
    return next(m for m in MIGRATIONS if m.name == "replies and instruction proposals")


async def _fresh() -> Path:
    cfg = load_config()
    await init_db(cfg)
    return get_db_path(cfg)


def _seed(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("INSERT INTO users (id, username, password_hash, encryption_salt) VALUES ('u', 'a', 'x', 's')")
    con.execute("INSERT INTO bots (id, user_id, name, name_key, job, instructions, avatar, created_at, updated_at) "
                "VALUES ('b', 'u', 'n', 'n', 'j', 'i', '{}', 't', 't')")
    con.execute("INSERT INTO threads (id, user_id, bot_id, created_at, updated_at) VALUES ('t1', 'u', 'b', 't', 't')")
    return con


def test_the_replies_migration_is_the_latest():
    assert _replies_migration().version <= latest_version()


async def test_messages_gain_reply_columns():
    db_path = await _fresh()
    assert {"reply_to", "reply_quote", "reply_tainted"} <= _columns(db_path, "messages")


async def test_instruction_proposals_table_and_index():
    db_path = await _fresh()
    assert _columns(db_path, "instruction_proposals") == {
        "id", "user_id", "bot_id", "payload", "tainted", "from_routine", "state", "thread_id", "message_id",
        "created_at", "decided_at"}
    indexes = {row[0] for row in _query(db_path, "SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert "idx_instruction_proposals_open" in indexes


async def test_the_migration_is_idempotent():
    db_path = await _fresh()
    async with aiosqlite.connect(db_path) as db:
        await _apply_one(db, _replies_migration())
        await _apply_one(db, _replies_migration())
    assert _query(db_path, "PRAGMA user_version")[0][0] == _replies_migration().version


async def test_a_proposal_state_must_be_known_and_retiring_the_bot_removes_it():
    con = _seed(await _fresh())
    con.execute(_PROPOSAL.format(state="open"))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(_PROPOSAL.replace("'p1'", "'p2'").format(state="maybe"))
    con.execute("DELETE FROM bots WHERE id = 'b' AND user_id = 'u'")
    assert con.execute("SELECT count(*) FROM instruction_proposals").fetchone() == (0,)
    con.close()


async def test_an_old_message_reads_as_no_reply():
    con = _seed(await _fresh())
    con.execute("INSERT INTO messages (id, user_id, thread_id, role, body, seq, created_at) "
                "VALUES ('m1', 'u', 't1', 'user', 'enc', 1, 't')")
    assert con.execute("SELECT reply_to, reply_quote, reply_tainted FROM messages").fetchone() == (None, None, 0)
    con.close()
