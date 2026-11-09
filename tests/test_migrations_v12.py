"""Migrating from the schema the live gateway runs at the start of the projects hub (version 12).

``tests/fixtures/schema_v12.sql`` was frozen by projects-hub Task 2. Rows go in
every table the user's account uses today (the v10 test's rows and a Stuck
card). v13 only adds: a project's colour, dates, monthly limit and lead bot,
an expense's step and star, a top-up's link to the credit it changes, and an
optional project on tasks, notes and documents."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import latest_version
from test_migrations_v10 import _EXPECTED as _V10_EXPECTED
from test_migrations_v10 import _ROWS as _V10_ROWS
from test_migrations_v8 import _NOW

_V12_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v12.sql"
_ROWS = (
    *_V10_ROWS,
    "INSERT INTO stuck_cards (id, user_id, bot_id, thread_id, reason, url, request, state, created_at) "
    f"VALUES ('c1','u1','b2','t1','login','enc:u','enc:r','open','{_NOW}')",
)
_EXPECTED = {**_V10_EXPECTED, "stuck_cards": 1}
_NEW_COLUMNS = {
    "money_projects": {"color", "start_date", "due_date", "monthly_budget", "lead_bot_id"},
    "money_expenses": {"step_id", "is_favorite"},
    "money_topups": {"topup_id"},
    "tasks": {"project_id", "allocated_budget"},
    "notes": {"project_id"},
    "documents": {"project_id"},
}
_NEW_INDEXES = {"idx_tasks_user_project", "idx_notes_user_project", "idx_documents_user_project"}
_LINKED = ("tasks", "notes", "documents")


def _query(db_path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def _version(db_path: Path) -> int:
    return _query(db_path, "PRAGMA user_version")[0][0]


def _counts(db_path: Path) -> dict[str, int]:
    return {table: _query(db_path, f"SELECT COUNT(*) FROM {table}")[0][0] for table in _EXPECTED}


def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


@pytest.fixture
def seeded_v12():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(_V12_SCHEMA.read_text())
        con.execute("PRAGMA user_version = 12")
        for statement in _ROWS:
            con.execute(statement)
        con.commit()
    finally:
        con.close()
    return cfg, db_path


async def test_v12_database_migrates_to_latest_and_keeps_every_row(seeded_v12):
    cfg, db_path = seeded_v12
    await init_db(cfg)
    assert latest_version() >= 13
    assert _version(db_path) == latest_version()
    assert _counts(db_path) == _EXPECTED


async def test_v12_database_gains_the_project_columns_and_indexes(seeded_v12):
    cfg, db_path = seeded_v12
    await init_db(cfg)
    for table, columns in _NEW_COLUMNS.items():
        assert columns <= {row[1] for row in _query(db_path, f"PRAGMA table_info({table})")}, table
    indexes = {row[0] for row in _query(db_path, "SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert _NEW_INDEXES <= indexes


async def test_existing_rows_keep_their_meaning(seeded_v12):
    cfg, db_path = seeded_v12
    await init_db(cfg)
    assert _query(db_path, "SELECT color, start_date, due_date, monthly_budget, lead_bot_id, status "
                           "FROM money_projects") == [(None, None, None, None, None, "active")]
    assert _query(db_path, "SELECT step_id, is_favorite, status FROM money_expenses") == [(None, 0, "posted")]
    assert _query(db_path, "SELECT kind, topup_id FROM money_topups") == [("credit", None)]
    assert _query(db_path, "SELECT project_id, allocated_budget FROM tasks") == [(None, None), (None, None)]
    for table in ("notes", "documents"):
        assert _query(db_path, f"SELECT project_id FROM {table}") == [(None,)]


async def test_a_projects_lead_bot_is_cleared_when_the_bot_goes(seeded_v12):
    cfg, db_path = seeded_v12
    await init_db(cfg)
    con = _connect(db_path)
    try:
        con.execute("UPDATE money_projects SET lead_bot_id = 'b2' WHERE id = 'p1'")
        con.execute("DELETE FROM bots WHERE id = 'b2'")
        assert con.execute("SELECT id, lead_bot_id FROM money_projects").fetchall() == [("p1", None)]
    finally:
        con.close()


async def test_items_lose_a_project_whose_row_goes_and_never_name_a_missing_one(seeded_v12):
    cfg, db_path = seeded_v12
    await init_db(cfg)
    con = _connect(db_path)
    try:
        for table in _LINKED:
            con.execute(f"UPDATE {table} SET project_id = 'p1'")
            with pytest.raises(sqlite3.IntegrityError):
                con.execute(f"UPDATE {table} SET project_id = 'no-such-project'")
        con.execute("DELETE FROM money_projects WHERE id = 'p1'")
        for table in _LINKED:
            assert {row[0] for row in con.execute(f"SELECT project_id FROM {table}")} == {None}, table
        assert con.execute("SELECT COUNT(*) FROM tasks").fetchone() == (2,)
    finally:
        con.close()


async def test_migrating_v12_twice_is_a_no_op_and_backs_up_once(seeded_v12):
    cfg, db_path = seeded_v12
    await init_db(cfg)
    await init_db(cfg)
    assert _counts(db_path) == _EXPECTED
    [backup] = sorted(db_path.parent.glob(f"roost.db.pre-v{latest_version()}-*.bak"))
    assert _version(backup) == 12
