"""Migrations from the schema the live gateway runs at the start of M2 (version 8).

``tests/fixtures/schema_v8.sql`` was frozen by M2 Task 1 from ``schema.sql`` +
migrations 1-8. These tests rebuild that database with rows in every table the
user's account uses today (bots and their roles, Talk, the work queue, rooms,
tasks and money), run ``init_db`` and check that nothing is lost."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import latest_version

_V8_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v8.sql"
_NOW = "2026-10-14T08:00:00+00:00"
_AVATAR = '{"shape": "round", "color": "#22c55e", "badge": "none"}'
_EXPECTED = {
    "users": 1, "sessions": 1, "bots": 2, "bot_roles": 3, "threads": 2, "messages": 2, "events": 1, "audit": 1,
    "work_items": 1, "runs": 1, "rooms": 1, "room_members": 2, "tasks": 2, "money_projects": 1,
    "money_expenses": 1, "money_topups": 1,
}
_ROWS = (
    "INSERT INTO users (id, username, password_hash, encryption_salt) VALUES ('u1','alice','h','s')",
    "INSERT INTO sessions (id, user_id, expires_at) VALUES ('s1','u1','2099-01-01T00:00:00+00:00')",
    "INSERT INTO bots (id, user_id, name, name_key, job, instructions, avatar, status, created_at, updated_at, "
    f"is_primary) VALUES ('b1','u1','enc:x','k1','enc:x','enc:x','{_AVATAR}','resting','{_NOW}','{_NOW}',1)",
    "INSERT INTO bots (id, user_id, name, name_key, job, instructions, avatar, status, created_at, updated_at) "
    f"VALUES ('b2','u1','enc:y','k2','enc:y','enc:y','{_AVATAR}','resting','{_NOW}','{_NOW}')",
    f"INSERT INTO bot_roles (user_id, bot_id, role_id, added_at) VALUES ('u1','b1','web','{_NOW}')",
    f"INSERT INTO bot_roles (user_id, bot_id, role_id, added_at) VALUES ('u1','b2','tasks','{_NOW}')",
    f"INSERT INTO bot_roles (user_id, bot_id, role_id, added_at) VALUES ('u1','b2','finance','{_NOW}')",
    f"INSERT INTO threads (id, user_id, bot_id, kind, created_at, updated_at) VALUES ('t1','u1','b2','chat','{_NOW}','{_NOW}')",
    f"INSERT INTO threads (id, user_id, bot_id, kind, created_at, updated_at) VALUES ('t2','u1','b1','room','{_NOW}','{_NOW}')",
    "INSERT INTO messages (id, user_id, thread_id, role, body, tainted, seq, created_at) "
    f"VALUES ('m1','u1','t1','user','enc:x',0,1,'{_NOW}')",
    "INSERT INTO messages (id, user_id, thread_id, role, body, tainted, seq, created_at, author_bot_id) "
    f"VALUES ('m2','u1','t1','bot','enc:y',0,2,'{_NOW}','b2')",
    f"INSERT INTO events (user_id, kind, payload, created_at) VALUES ('u1','tasks_changed','enc:x','{_NOW}')",
    "INSERT INTO audit (user_id, bot_id, action, decision, detail, created_at, reason, tainted) "
    f"VALUES ('u1','b2','add_task','do','enc:x','{_NOW}','allowed',0)",
    "INSERT INTO work_items (id, user_id, bot_id, thread_id, kind, origin, body, state, created_at, updated_at) "
    f"VALUES ('w1','u1','b2','t1','message','enc:o','enc:b','done','{_NOW}','{_NOW}')",
    f"INSERT INTO runs (id, user_id, bot_id, thread_id, outcome, started_at, ended_at) VALUES ('r1','u1','b2','t1','done','{_NOW}','{_NOW}')",
    "INSERT INTO rooms (id, user_id, name, coordinator_bot_id, thread_id, created_at, updated_at) "
    f"VALUES ('room1','u1','enc:r','b1','t2','{_NOW}','{_NOW}')",
    f"INSERT INTO room_members (room_id, bot_id, user_id, added_at) VALUES ('room1','b1','u1','{_NOW}')",
    f"INSERT INTO room_members (room_id, bot_id, user_id, added_at) VALUES ('room1','b2','u1','{_NOW}')",
    "INSERT INTO tasks (id, user_id, title, created_at, updated_at, created_by_bot, tainted) "
    f"VALUES ('task1','u1','enc:t','{_NOW}','{_NOW}','b2',0)",
    "INSERT INTO tasks (id, user_id, title, created_at, updated_at, created_by_bot, tainted) "
    f"VALUES ('task2','u1','enc:t','{_NOW}','{_NOW}',NULL,1)",
    "INSERT INTO money_projects (id, user_id, name, name_key, created_at, updated_at) "
    f"VALUES ('p1','u1','enc:n','key1','{_NOW}','{_NOW}')",
    "INSERT INTO money_expenses (id, user_id, project_id, amount, spent_at, created_at, updated_at) "
    f"VALUES ('e1','u1','p1','enc:a','2026-10-03','{_NOW}','{_NOW}')",
    "INSERT INTO money_topups (id, user_id, project_id, amount, created_at, updated_at) "
    f"VALUES ('top1','u1','p1','enc:a','{_NOW}','{_NOW}')",
)


def _seed_v8_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(_V8_SCHEMA.read_text())
        con.execute("PRAGMA user_version = 8")
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
def seeded_v8():
    cfg = load_config()
    db_path = get_db_path(cfg)
    _seed_v8_database(db_path)
    assert _version(db_path) == 8
    return cfg, db_path


async def test_v8_database_migrates_to_latest_and_keeps_every_row(seeded_v8):
    cfg, db_path = seeded_v8
    await init_db(cfg)
    assert _version(db_path) == latest_version()
    assert _counts(db_path) == _EXPECTED


async def test_migrating_v8_twice_is_a_no_op(seeded_v8):
    cfg, db_path = seeded_v8
    await init_db(cfg)
    await init_db(cfg)
    assert _counts(db_path) == _EXPECTED
    assert _version(db_path) == latest_version()


async def test_a_v8_database_is_backed_up_before_migrating(seeded_v8):
    cfg, db_path = seeded_v8
    await init_db(cfg)
    [backup] = sorted(db_path.parent.glob("roost.db.pre-v*.bak"))
    assert _version(backup) == 8
    assert _counts(backup) == _EXPECTED


async def test_v9_adds_an_empty_notes_table_with_provenance_and_a_revision(seeded_v8):
    cfg, db_path = seeded_v8
    await init_db(cfg)
    assert _query(db_path, "SELECT COUNT(*) FROM notes") == [(0,)]
    columns = _columns(db_path, "notes")
    assert {"user_id", "title", "title_key", "content", "tags", "pinned", "revision", "created_at", "updated_at",
            "deleted_at", "created_by_bot", "tainted"} <= set(columns)
    assert columns["revision"][3] == 1 and columns["tainted"][3] == 1   # NOT NULL


async def test_retiring_a_bot_keeps_the_users_notes(seeded_v8):
    cfg, db_path = seeded_v8
    await init_db(cfg)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("INSERT INTO notes (id, user_id, title, title_key, content, created_at, updated_at, created_by_bot) "
                    f"VALUES ('n1','u1','enc:t','k','enc:c','{_NOW}','{_NOW}','b2')")
        con.execute("DELETE FROM bots WHERE id = 'b2'")
        con.commit()
    finally:
        con.close()
    assert _query(db_path, "SELECT id, created_by_bot FROM notes") == [("n1", None)]


async def test_v10_adds_an_empty_documents_table_that_only_takes_known_kinds(seeded_v8):
    cfg, db_path = seeded_v8
    await init_db(cfg)
    assert _query(db_path, "SELECT COUNT(*) FROM documents") == [(0,)]
    assert {"user_id", "kind", "title", "payload", "pages", "tags", "revision", "created_at", "updated_at",
            "deleted_at", "created_by_bot", "tainted"} <= set(_columns(db_path, "documents"))
    con = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO documents (id, user_id, kind, title, payload, created_at, updated_at) "
                        f"VALUES ('d1','u1','xlsx','enc:t','enc:p','{_NOW}','{_NOW}')")
    finally:
        con.close()
    assert _counts(db_path) == _EXPECTED
