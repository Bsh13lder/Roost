"""Migrating from schema v22 (frozen before approval modes and Mac folders) to v23."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import aiosqlite
import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import apply_migrations, latest_version

_V22_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v22.sql"


def _query(db_path: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _seed_v22():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.executescript(_V22_SCHEMA.read_text())
        con.execute("INSERT INTO users (id, username, password_hash, encryption_salt) VALUES ('u', 'a', 'x', 's')")
        con.execute("INSERT INTO bots (id, user_id, name, name_key, job, instructions, avatar, created_at, updated_at) "
                    "VALUES ('b', 'u', 'n', 'n', 'j', 'i', '{}', 't', 't')")
        con.execute("INSERT INTO threads (id, user_id, bot_id, created_at, updated_at) VALUES ('t1', 'u', 'b', 't', 't')")
        con.execute("PRAGMA user_version = 22")
        con.commit()
    finally:
        con.close()
    return cfg, db_path


def _columns(db_path: Path, table: str) -> set[str]:
    return {row[1] for row in _query(db_path, f"PRAGMA table_info({table})")}


def _exec(db_path: Path, *statements: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    for sql in statements:
        con.execute(sql)
    return con


_GRANT = ("INSERT INTO mac_grants (id, user_id, bot_id, path, label, access, created_at) "
          "VALUES ('{id}', 'u', {bot}, 'enc', 'enc', '{access}', 't')")
_CARD = ("INSERT INTO approval_cards (id, user_id, bot_id, thread_id, kind, state, steps, request, created_at) "
         "VALUES ('{id}', 'u', 'b', 't1', '{kind}', '{state}', 'enc', 'enc', 't')")


async def test_v23_adds_approvals_grants_cards_and_marks_and_keeps_every_row():
    cfg, db_path = _seed_v22()
    await init_db(cfg)
    assert latest_version() >= 23
    assert _query(db_path, "PRAGMA user_version")[0][0] == latest_version()
    assert {"approval_mode", "approval_ask_topics"} <= _columns(db_path, "bots")
    assert _columns(db_path, "mac_grants") == {
        "id", "user_id", "bot_id", "path", "label", "access", "read_policy", "is_vault", "created_at", "revoked_at"}
    assert _columns(db_path, "approval_cards") == {
        "id", "user_id", "bot_id", "thread_id", "work_item_id", "kind", "state", "steps", "request", "tainted",
        "session_offer", "answer_item_id", "created_at", "closed_at"}
    assert _columns(db_path, "mac_file_marks") == {
        "user_id", "grant_id", "path_key", "sha256", "bot_id", "written_tainted", "updated_at"}
    assert _query(db_path, "SELECT id FROM bots") == [("b",)]
    assert _query(db_path, "SELECT id FROM threads") == [("t1",)]


async def test_old_bots_keep_auto_edit_with_files_asking():
    cfg, db_path = _seed_v22()
    await init_db(cfg)
    assert _query(db_path, "SELECT approval_mode, approval_ask_topics FROM bots") == [("auto_edit", '["files"]')]


async def test_v23_checks_modes_access_policies_and_card_values():
    cfg, db_path = _seed_v22()
    await init_db(cfg)
    bad = [
        "UPDATE bots SET approval_mode = 'yolo'",
        _GRANT.format(id="g", bot="NULL", access="write"),
        "INSERT INTO mac_grants (id, user_id, path, label, access, read_policy, created_at) "
        "VALUES ('g2', 'u', 'e', 'e', 'read', 'never', 't')",
        _CARD.format(id="c", kind="shout", state="open"),
        _CARD.format(id="c", kind="ask", state="maybe"),
    ]
    for sql in bad:
        con = _exec(db_path)
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(sql)
        con.close()
    con = _exec(db_path, _GRANT.format(id="ok", bot="NULL", access="read_write"), _CARD.format(id="ok", kind="plan", state="open"))
    con.commit()
    con.close()


async def test_one_open_approval_card_per_bot():
    cfg, db_path = _seed_v22()
    await init_db(cfg)
    con = _exec(db_path, _CARD.format(id="c1", kind="ask", state="open"))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(_CARD.format(id="c2", kind="ask", state="open"))
    con.execute(_CARD.format(id="c3", kind="ask", state="approved"))
    con.execute(_CARD.format(id="c4", kind="plan", state="declined"))
    con.close()


async def test_retiring_a_bot_drops_its_grants_cards_and_marks():
    cfg, db_path = _seed_v22()
    await init_db(cfg)
    con = _exec(
        db_path,
        _GRANT.format(id="mine", bot="'b'", access="read"),
        _GRANT.format(id="all", bot="NULL", access="read"),
        _CARD.format(id="c1", kind="ask", state="open"),
        "INSERT INTO mac_file_marks (user_id, grant_id, path_key, sha256, updated_at) VALUES ('u', 'mine', 'k', 'h', 't')",
        "INSERT INTO mac_file_marks (user_id, grant_id, path_key, sha256, updated_at) VALUES ('u', 'all', 'k', 'h', 't')",
    )
    con.execute("DELETE FROM bots WHERE id = 'b'")
    con.commit()
    assert con.execute("SELECT id FROM mac_grants").fetchall() == [("all",)]
    assert con.execute("SELECT id FROM approval_cards").fetchall() == []
    assert con.execute("SELECT grant_id FROM mac_file_marks").fetchall() == [("all",)]
    con.close()


async def test_migration_23_is_idempotent():
    cfg, db_path = _seed_v22()
    await init_db(cfg)
    before = _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name")
    async with aiosqlite.connect(db_path) as db:
        assert await apply_migrations(db) == latest_version()
        assert await apply_migrations(db) == latest_version()
    assert _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name") == before
