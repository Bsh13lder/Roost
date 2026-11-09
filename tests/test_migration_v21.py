"""Migrating from schema v20 (frozen before money income) to v21: ``money_expenses.kind``."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import aiosqlite

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import apply_migrations, latest_version

_V20_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v20.sql"


def _query(db_path: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _seed_v20():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.executescript(_V20_SCHEMA.read_text())
        con.execute("INSERT INTO users (id, username, password_hash, encryption_salt) VALUES ('u', 'a', 'x', 's')")
        con.execute("INSERT INTO money_projects (id, user_id, name, name_key, currency, created_at, updated_at) "
                    "VALUES ('p', 'u', 'enc', 'k', 'EUR', 't', 't')")
        con.execute("INSERT INTO money_expenses (id, user_id, project_id, amount, currency, spent_at, status, "
                    "created_at, updated_at) VALUES ('e', 'u', 'p', 'enc', 'EUR', '2026-10-01', 'posted', 't', 't')")
        con.execute("PRAGMA user_version = 20")
        con.commit()
    finally:
        con.close()
    return cfg, db_path


async def test_v21_adds_kind_and_old_rows_stay_expenses():
    cfg, db_path = _seed_v20()
    await init_db(cfg)
    assert latest_version() >= 21
    assert _query(db_path, "PRAGMA user_version")[0][0] == latest_version()
    assert _query(db_path, "SELECT kind FROM money_expenses") == [("expense",)]
    columns = {row[1]: row for row in _query(db_path, "PRAGMA table_info(money_expenses)")}
    assert columns["kind"][2] == "TEXT" and columns["kind"][3] == 1       # NOT NULL
    before = _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name")
    async with aiosqlite.connect(db_path) as db:
        assert await apply_migrations(db) == latest_version()
    assert _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name") == before


async def test_kind_allows_only_expense_or_income():
    cfg, db_path = _seed_v20()
    await init_db(cfg)
    con = sqlite3.connect(db_path)
    try:
        con.execute("UPDATE money_expenses SET kind = 'income'")
        try:
            con.execute("UPDATE money_expenses SET kind = 'gift'")
        except sqlite3.IntegrityError:
            return
        raise AssertionError("a kind other than expense or income was accepted")
    finally:
        con.close()
