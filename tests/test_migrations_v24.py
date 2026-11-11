"""Migrating from schema v24 (frozen before Routines and Plan) to v25."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import aiosqlite
import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import apply_migrations, latest_version

_V24_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v24.sql"


def _query(db_path: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _seed_v24():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.executescript(_V24_SCHEMA.read_text())
        con.execute("INSERT INTO users (id, username, password_hash, encryption_salt) VALUES ('u', 'a', 'x', 's')")
        con.execute("INSERT INTO bots (id, user_id, name, name_key, job, instructions, avatar, created_at, updated_at) "
                    "VALUES ('b', 'u', 'n', 'n', 'j', 'i', '{}', 't', 't')")
        con.execute("INSERT INTO threads (id, user_id, bot_id, created_at, updated_at) VALUES ('t1', 'u', 'b', 't', 't')")
        con.execute("INSERT INTO tasks (id, user_id, title, created_at, updated_at) VALUES ('k1', 'u', 'enc', 't', 't')")
        con.execute("INSERT INTO money_projects (id, user_id, name, name_key, created_at, updated_at) "
                    "VALUES ('p1', 'u', 'enc', 'k', 't', 't')")
        con.execute("PRAGMA user_version = 24")
        con.commit()
    finally:
        con.close()
    return cfg, db_path


def _columns(db_path: Path, table: str) -> set[str]:
    return {row[1] for row in _query(db_path, f"PRAGMA table_info({table})")}


def _con(db_path: Path, *statements: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    for sql in statements:
        con.execute(sql)
    return con


_ROUTINE = ("INSERT INTO routines (id, user_id, bot_id, thread_id, name, instructions, schedule, created_by, "
            "created_at, updated_at) VALUES ('r1', 'u', 'b', 't1', 'enc', 'enc', 'enc', 'user', 't', 't')")
_RUN = ("INSERT INTO routine_runs (id, user_id, routine_id, bot_id, slot_at, state, created_at) "
        "VALUES ('{id}', 'u', 'r1', 'b', '2026-10-21T08:00:00+00:00', '{state}', 't')")
_PROPOSAL = ("INSERT INTO routine_proposals (id, user_id, bot_id, routine_id, action, payload, state, thread_id, created_at) "
             "VALUES ('pr1', 'u', 'b', 'r1', 'change', 'enc', 'open', 't1', 't')")
_QUESTION = ("INSERT INTO bot_questions (id, user_id, bot_id, routine_id, thread_id, question, default_choice, state, "
             "created_at) VALUES ('q1', 'u', 'b', 'r1', 't1', 'enc', 'enc', 'open', 't')")
_PLAN = ("INSERT INTO bot_plans (id, user_id, bot_id, content, item_taint, created_at, updated_at) "
         "VALUES ('{id}', 'u', 'b', 'enc', 'enc', 't', 't')")
_REMINDER = ("INSERT INTO reminder_sends (id, user_id, task_id, fire_at, sent_at) "
             "VALUES ('{id}', 'u', 'k1', '2026-10-21T08:00:00+00:00', 't')")
_ALERT = ("INSERT INTO budget_alerts (id, user_id, project_id, budget, level, month, sent_at) "
          "VALUES ('{id}', 'u', 'p1', 'month', 'warn', '2026-10', 't')")


def test_the_v24_fixture_is_really_v24():
    text = _V24_SCHEMA.read_text()
    assert "site_logins" in text
    assert "CREATE TABLE routines" not in text


async def test_v25_adds_the_routine_and_plan_tables_and_keeps_every_row():
    cfg, db_path = _seed_v24()
    await init_db(cfg)
    assert latest_version() >= 25
    assert _query(db_path, "PRAGMA user_version")[0][0] == latest_version()
    assert _columns(db_path, "routines") == {
        "id", "user_id", "bot_id", "thread_id", "name", "instructions", "schedule", "builtin", "enabled", "tainted",
        "created_by", "next_run_at", "last_run_at", "created_at", "updated_at",
        "watch_url", "watch_part", "watch_every_min",   # v40: the routine watch
        "model", "model_failures",     # v46: a routine's own model
        "last_error_kind", "last_error_at",     # v47: its last error
        "finished_at", "finished_reason"}       # v48: the bot finished it (finish_routine)
    assert _columns(db_path, "routine_runs") == {
        "id", "user_id", "routine_id", "bot_id", "slot_at", "work_item_id", "state", "missed_count", "note",
        "started_at", "finished_at", "created_at"}
    assert _columns(db_path, "routine_proposals") == {
        "id", "user_id", "bot_id", "routine_id", "action", "payload", "tainted", "from_routine", "state",
        "thread_id", "message_id", "created_at", "decided_at"}
    assert _columns(db_path, "bot_questions") == {
        "id", "user_id", "bot_id", "routine_id", "thread_id", "question", "default_choice", "why", "answer",
        "tainted", "state", "created_at", "answered_at"}
    assert _columns(db_path, "bot_plans") == {
        "id", "user_id", "bot_id", "content", "item_taint", "revision", "export_enabled", "created_at", "updated_at"}
    assert _columns(db_path, "reminder_sends") == {"id", "user_id", "task_id", "fire_at", "missed", "sent_at"}
    assert _columns(db_path, "budget_alerts") == {
        "id", "user_id", "project_id", "budget", "level", "month", "sent_at"}
    assert "full_limit_until" in _columns(db_path, "bots")
    assert _query(db_path, "SELECT full_limit_until FROM bots") == [(None,)]
    for table in ("bots", "threads", "tasks", "money_projects"):
        assert _query(db_path, f"SELECT count(*) FROM {table}") == [(1,)]


async def test_a_slot_can_hold_a_missed_row_and_one_run():
    cfg, db_path = _seed_v24()
    await init_db(cfg)
    con = _con(db_path, _ROUTINE, _RUN.format(id="a", state="missed"), _RUN.format(id="b", state="queued"))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(_RUN.format(id="c", state="queued"))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(_RUN.format(id="d", state="sleeping"))
    con.close()


async def test_reminders_and_budget_alerts_are_sent_once():
    cfg, db_path = _seed_v24()
    await init_db(cfg)
    con = _con(db_path, _REMINDER.format(id="a"), _ALERT.format(id="a"))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(_REMINDER.format(id="b"))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(_ALERT.format(id="b"))
    con.close()


async def test_one_plan_per_bot():
    cfg, db_path = _seed_v24()
    await init_db(cfg)
    con = _con(db_path, _PLAN.format(id="a"))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(_PLAN.format(id="b"))
    con.close()


async def test_retiring_a_bot_drops_its_routines_runs_questions_proposals_and_plan():
    cfg, db_path = _seed_v24()
    await init_db(cfg)
    con = _con(db_path, _ROUTINE, _RUN.format(id="a", state="queued"), _PROPOSAL, _QUESTION, _PLAN.format(id="a"))
    con.commit()
    con.execute("DELETE FROM bots WHERE id = 'b'")
    con.commit()
    con.close()
    for table in ("routines", "routine_runs", "routine_proposals", "bot_questions", "bot_plans"):
        assert _query(db_path, f"SELECT count(*) FROM {table}") == [(0,)], table


async def test_migration_25_is_idempotent():
    cfg, db_path = _seed_v24()
    await init_db(cfg)
    before = _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name")
    async with aiosqlite.connect(db_path) as db:
        assert await apply_migrations(db) == latest_version()
        await db.execute("PRAGMA user_version = 24")
        assert await apply_migrations(db) == latest_version()
    assert _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name") == before
