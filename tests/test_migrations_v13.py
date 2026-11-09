"""Migrating from the schema the live gateway runs at the start of redesign P3 (version 13).

``tests/fixtures/schema_v13.sql`` was frozen by redesign P3 Task 3. Rows go in every table the
user's account uses today (the v12 test's rows, plus a task in a project with a budget slice and an
expense filed under one of its steps). v14 only adds the ``task_comments`` table and its index."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import latest_version
from test_migrations_v8 import _NOW
from test_migrations_v12 import _EXPECTED as _V12_EXPECTED
from test_migrations_v12 import _ROWS as _V12_ROWS

_V13_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v13.sql"
_ROWS = (
    *_V12_ROWS,
    "INSERT INTO tasks (id, user_id, title, created_at, updated_at, project_id, allocated_budget) "
    f"VALUES ('task3','u1','enc:t','{_NOW}','{_NOW}','p1','enc:b')",
    "INSERT INTO money_expenses (id, user_id, project_id, task_id, step_id, amount, spent_at, created_at, updated_at) "
    f"VALUES ('e2','u1','p1','task3','s-1','enc:a','2026-10-03','{_NOW}','{_NOW}')",
)
_EXPECTED = {**_V12_EXPECTED, "tasks": 3, "money_expenses": 2}
_COMMENT_COLUMNS = {"id", "user_id", "task_id", "step_id", "author", "body", "tainted", "created_at", "edited_at",
                    "deleted_at"}
_COMMENT = ("INSERT INTO task_comments (id, user_id, task_id, step_id, author, body, created_at) "
            f"VALUES ('c1','u1','{{task}}',NULL,'user','enc:c','{_NOW}')")


def _query(db_path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def _counts(db_path: Path) -> dict[str, int]:
    return {table: _query(db_path, f"SELECT COUNT(*) FROM {table}")[0][0] for table in _EXPECTED}


def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


@pytest.fixture
def seeded_v13():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(_V13_SCHEMA.read_text())
        con.execute("PRAGMA user_version = 13")
        for statement in _ROWS:
            con.execute(statement)
        con.commit()
    finally:
        con.close()
    return cfg, db_path


async def test_v13_database_migrates_to_latest_and_keeps_every_row(seeded_v13):
    cfg, db_path = seeded_v13
    await init_db(cfg)
    assert latest_version() >= 14
    assert _query(db_path, "PRAGMA user_version")[0][0] == latest_version()
    assert _counts(db_path) == _EXPECTED
    assert _query(db_path, "SELECT project_id, allocated_budget FROM tasks WHERE id = 'task3'") == [("p1", "enc:b")]
    assert _query(db_path, "SELECT task_id, step_id FROM money_expenses WHERE id = 'e2'") == [("task3", "s-1")]


async def test_v13_database_gains_the_comments_table_and_its_index(seeded_v13):
    cfg, db_path = seeded_v13
    await init_db(cfg)
    assert {row[1] for row in _query(db_path, "PRAGMA table_info(task_comments)")} == _COMMENT_COLUMNS
    indexes = {row[0] for row in _query(db_path, "SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert "idx_task_comments_task" in indexes
    assert _query(db_path, "SELECT COUNT(*) FROM task_comments") == [(0,)]


async def test_a_comment_names_a_real_task_and_goes_with_its_row(seeded_v13):
    cfg, db_path = seeded_v13
    await init_db(cfg)
    con = _connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(_COMMENT.format(task="no-such-task"))
        con.execute(_COMMENT.format(task="task3"))
        assert con.execute("SELECT tainted, edited_at, deleted_at FROM task_comments").fetchall() == [(0, None, None)]
        con.execute("DELETE FROM tasks WHERE id = 'task3'")
        assert con.execute("SELECT COUNT(*) FROM task_comments").fetchone() == (0,)
    finally:
        con.close()


async def test_migrating_v13_twice_is_a_no_op_and_backs_up_once(seeded_v13):
    cfg, db_path = seeded_v13
    await init_db(cfg)
    await init_db(cfg)
    assert _counts(db_path) == _EXPECTED
    [backup] = sorted(db_path.parent.glob(f"roost.db.pre-v{latest_version()}-*.bak"))
    assert _query(backup, "PRAGMA user_version")[0][0] == 13
