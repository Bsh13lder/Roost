"""The obsidian migration: tags on expenses and memories, the Bot Journal, the vault export switches."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import aiosqlite
import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import MIGRATIONS, _apply_one, latest_version


def _obsidian():
    return next(m for m in MIGRATIONS if m.name == "obsidian")


def _query(db_path: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _columns(db_path: Path, table: str) -> set[str]:
    return {row[1] for row in _query(db_path, f"PRAGMA table_info({table})")}


async def _fresh() -> Path:
    cfg = load_config()
    await init_db(cfg)
    return get_db_path(cfg)


def test_the_obsidian_migration_is_in_the_list():
    assert _obsidian().version <= latest_version()


async def test_it_adds_the_tag_columns_and_the_export_switch():
    db_path = await _fresh()
    assert "tags" in _columns(db_path, "money_expenses")
    assert "tags" in _columns(db_path, "memories")
    assert "vault_export" in _columns(db_path, "money_projects")


async def test_it_adds_the_journal_and_the_export_tables():
    db_path = await _fresh()
    assert _columns(db_path, "bot_journals") == {
        "id", "user_id", "bot_id", "day", "content", "tainted", "revision", "created_at", "updated_at"}
    assert _columns(db_path, "vault_exports") == {
        "user_id", "grant_id", "journals", "manifest", "last_result", "last_written", "last_conflicts",
        "last_export_at", "updated_at"}
    indexes = {row[0] for row in _query(db_path, "SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert "idx_bot_journals_day" in indexes


async def test_it_is_idempotent():
    db_path = await _fresh()
    async with aiosqlite.connect(db_path) as db:
        await _apply_one(db, _obsidian())
        await _apply_one(db, _obsidian())
    assert _query(db_path, "PRAGMA user_version")[0][0] == _obsidian().version


async def test_one_journal_row_per_bot_per_day_and_it_goes_with_the_bot():
    db_path = await _fresh()
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("INSERT INTO users (id, username, password_hash, encryption_salt) VALUES ('u', 'a', 'x', 's')")
    con.execute("INSERT INTO bots (id, user_id, name, name_key, job, instructions, avatar, created_at, updated_at) "
                "VALUES ('b', 'u', 'n', 'n', 'j', 'i', '{}', 't', 't')")
    row = ("INSERT INTO bot_journals (id, user_id, bot_id, day, content, created_at, updated_at) "
           "VALUES ('{id}', 'u', 'b', '2026-10-22', 'enc', 't', 't')")
    con.execute(row.format(id="j1"))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(row.format(id="j2"))
    con.execute("DELETE FROM bots WHERE id = 'b' AND user_id = 'u'")
    assert con.execute("SELECT count(*) FROM bot_journals").fetchone() == (0,)
    con.close()


async def test_a_new_project_does_not_export_by_default():
    db_path = await _fresh()
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO users (id, username, password_hash, encryption_salt) VALUES ('u', 'a', 'x', 's')")
    con.execute("INSERT INTO money_projects (id, user_id, name, name_key, created_at, updated_at) "
                "VALUES ('p', 'u', 'enc', 'k', 't', 't')")
    assert con.execute("SELECT vault_export FROM money_projects").fetchone() == (0,)
    con.close()
