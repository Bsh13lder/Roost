"""Migrations from the schema the live gateway runs at the start of M1 (version 4).

``tests/fixtures/schema_v4.sql`` was frozen by M1 Task 1 from ``schema.sql`` +
migrations 1-4. These tests rebuild that database with rows in every table,
run ``init_db`` and check that nothing is lost and every existing bot keeps
its browser (the ``web`` role)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import latest_version

_V4_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v4.sql"
_NOW = "2026-10-13T08:00:00+00:00"
_AVATAR = '{"shape": "round", "color": "#22c55e", "badge": "none"}'
_EXPECTED = {
    "users": 1, "sessions": 1, "bots": 2, "threads": 2, "messages": 1, "events": 1, "audit": 1,
    "work_items": 1, "runs": 1, "rooms": 1, "room_members": 2,
}
_ROWS = (
    "INSERT INTO users (id, username, password_hash, encryption_salt) VALUES ('u1','alice','h','s')",
    "INSERT INTO sessions (id, user_id, expires_at) VALUES ('s1','u1','2099-01-01T00:00:00+00:00')",
    "INSERT INTO bots (id, user_id, name, name_key, job, instructions, avatar, status, created_at, updated_at, "
    f"is_primary) VALUES ('b1','u1','enc:x','k1','enc:x','enc:x','{_AVATAR}','resting','{_NOW}','{_NOW}',1)",
    "INSERT INTO bots (id, user_id, name, name_key, job, instructions, avatar, status, created_at, updated_at) "
    f"VALUES ('b2','u1','enc:y','k2','enc:y','enc:y','{_AVATAR}','resting','{_NOW}','{_NOW}')",
    f"INSERT INTO threads (id, user_id, bot_id, kind, created_at, updated_at) VALUES ('t1','u1','b1','chat','{_NOW}','{_NOW}')",
    f"INSERT INTO threads (id, user_id, bot_id, kind, created_at, updated_at) VALUES ('t2','u1','b1','room','{_NOW}','{_NOW}')",
    "INSERT INTO messages (id, user_id, thread_id, role, body, tainted, seq, created_at) "
    f"VALUES ('m1','u1','t1','user','enc:x',0,1,'{_NOW}')",
    f"INSERT INTO events (user_id, kind, payload, created_at) VALUES ('u1','message','enc:x','{_NOW}')",
    "INSERT INTO audit (user_id, bot_id, action, decision, detail, created_at) "
    f"VALUES ('u1','b1','open_page','do','enc:x','{_NOW}')",
    "INSERT INTO work_items (id, user_id, bot_id, thread_id, kind, origin, body, state, created_at, updated_at) "
    f"VALUES ('w1','u1','b2','t1','handoff','enc:o','enc:b','done','{_NOW}','{_NOW}')",
    f"INSERT INTO runs (id, user_id, bot_id, thread_id, outcome, started_at, ended_at) VALUES ('r1','u1','b1','t1','done','{_NOW}','{_NOW}')",
    "INSERT INTO rooms (id, user_id, name, coordinator_bot_id, thread_id, created_at, updated_at) "
    f"VALUES ('room1','u1','enc:r','b1','t2','{_NOW}','{_NOW}')",
    f"INSERT INTO room_members (room_id, bot_id, user_id, added_at) VALUES ('room1','b1','u1','{_NOW}')",
    f"INSERT INTO room_members (room_id, bot_id, user_id, added_at) VALUES ('room1','b2','u1','{_NOW}')",
)


def _seed_v4_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(_V4_SCHEMA.read_text())
        con.execute("PRAGMA user_version = 4")
        for statement in _ROWS:
            con.execute(statement)
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
    return {table: _query(db_path, f"SELECT COUNT(*) FROM {table}")[0][0] for table in _EXPECTED}


def _version(db_path: Path) -> int:
    return _query(db_path, "PRAGMA user_version")[0][0]


def _columns(db_path: Path, table: str) -> dict[str, tuple]:
    return {row[1]: row for row in _query(db_path, f"PRAGMA table_info({table})")}


@pytest.fixture
def seeded_v4():
    cfg = load_config()
    db_path = get_db_path(cfg)
    _seed_v4_database(db_path)
    assert _version(db_path) == 4
    return cfg, db_path


async def test_v4_database_migrates_to_latest_and_keeps_every_row(seeded_v4):
    cfg, db_path = seeded_v4
    await init_db(cfg)
    assert _version(db_path) == latest_version()
    assert _counts(db_path) == _EXPECTED


async def test_migrating_v4_twice_is_a_no_op(seeded_v4):
    cfg, db_path = seeded_v4
    await init_db(cfg)
    await init_db(cfg)
    assert _counts(db_path) == _EXPECTED
    assert _query(db_path, "SELECT COUNT(*) FROM bot_roles") == [(2,)]


async def test_every_existing_bot_keeps_its_browser_as_the_web_role(seeded_v4):
    cfg, db_path = seeded_v4
    await init_db(cfg)
    assert _query(db_path, "SELECT user_id, bot_id, role_id FROM bot_roles ORDER BY bot_id") == [
        ("u1", "b1", "web"), ("u1", "b2", "web"),
    ]


async def test_a_v4_database_is_backed_up_before_migrating(seeded_v4):
    cfg, db_path = seeded_v4
    await init_db(cfg)
    [backup] = sorted(db_path.parent.glob("roost.db.pre-v*.bak"))
    assert _version(backup) == 4
    assert _counts(backup) == _EXPECTED


async def test_v6_adds_audit_reason_and_taint_and_a_link_scope_column(seeded_v4):
    cfg, db_path = seeded_v4
    await init_db(cfg)
    assert _query(db_path, "SELECT reason, tainted FROM audit") == [(None, 0)]
    assert _query(db_path, "SELECT link_scope FROM work_items WHERE id = 'w1'") == [(None,)]
    assert _columns(db_path, "audit")["tainted"][3] == 1   # NOT NULL


async def test_retiring_a_migrated_bot_drops_its_role_rows(seeded_v4):
    cfg, db_path = seeded_v4
    await init_db(cfg)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("DELETE FROM bots WHERE id = 'b2'")
        con.commit()
    finally:
        con.close()
    assert _query(db_path, "SELECT bot_id FROM bot_roles") == [("b1",)]


async def test_v7_adds_an_empty_tasks_table_with_provenance(seeded_v4):
    cfg, db_path = seeded_v4
    await init_db(cfg)
    assert _query(db_path, "SELECT COUNT(*) FROM tasks") == [(0,)]
    columns = _columns(db_path, "tasks")
    assert {"user_id", "created_by_bot", "tainted", "due_date", "reminder_at", "pre_reminders", "deleted_at"} <= set(columns)
    assert columns["tainted"][3] == 1


async def test_v8_adds_empty_money_tables_with_provenance(seeded_v4):
    cfg, db_path = seeded_v4
    await init_db(cfg)
    for table in ("money_projects", "money_expenses", "money_topups"):
        assert _query(db_path, f"SELECT COUNT(*) FROM {table}") == [(0,)]
        assert {"user_id", "created_by_bot", "tainted", "deleted_at"} <= set(_columns(db_path, table))
    assert _counts(db_path) == _EXPECTED
