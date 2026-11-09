"""Migrating from schema v23 (frozen before Computers) to v24: bots.computer and site_logins."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import aiosqlite
import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import apply_migrations, latest_version

_V23_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v23.sql"


def _query(db_path: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _seed_v23():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.executescript(_V23_SCHEMA.read_text())
        con.execute("INSERT INTO users (id, username, password_hash, encryption_salt) VALUES ('u', 'a', 'x', 's')")
        con.execute("INSERT INTO bots (id, user_id, name, name_key, job, instructions, avatar, created_at, updated_at) "
                    "VALUES ('b', 'u', 'n', 'n', 'j', 'i', '{}', 't', 't')")
        con.execute("PRAGMA user_version = 23")
        con.commit()
    finally:
        con.close()
    return cfg, db_path


_LOGIN = ("INSERT INTO site_logins (id, user_id, bot_id, host, host_key, label, created_at, updated_at) "
          "VALUES ('{id}', 'u', 'b', 'enc', '{key}', 'enc', 't', 't')")


def test_the_v23_fixture_is_really_v23():
    text = _V23_SCHEMA.read_text()
    assert "approval_cards" in text
    assert "site_logins" not in text


async def test_v23_upgrades_to_v24_additively():
    cfg, db_path = _seed_v23()
    await init_db(cfg)
    assert latest_version() >= 24
    assert _query(db_path, "PRAGMA user_version")[0][0] >= 24
    assert "computer" in {row[1] for row in _query(db_path, "PRAGMA table_info(bots)")}
    assert {row[1] for row in _query(db_path, "PRAGMA table_info(site_logins)")} == {
        "id", "user_id", "bot_id", "host", "host_key", "label", "created_at", "updated_at",
        "kept", "clear_after_item_id"}    # the Sign-in card added the last two
    names = {row[0] for row in _query(db_path, "SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert {"idx_site_logins_one", "idx_site_logins_bot"} <= names
    assert _query(db_path, "SELECT id FROM bots") == [("b",)]


async def test_old_bots_stay_on_mac_brave():
    cfg, db_path = _seed_v23()
    await init_db(cfg)
    assert _query(db_path, "SELECT computer FROM bots") == [("mac_brave",)]


async def test_site_logins_are_unique_per_host_key_and_leave_with_the_bot():
    cfg, db_path = _seed_v23()
    await init_db(cfg)
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute(_LOGIN.format(id="l1", key="k"))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(_LOGIN.format(id="l2", key="k"))
    con.execute(_LOGIN.format(id="l3", key="other"))
    con.execute("DELETE FROM bots WHERE id = 'b'")
    assert con.execute("SELECT COUNT(*) FROM site_logins").fetchone() == (0,)
    con.close()


async def test_migration_24_is_idempotent():
    cfg, db_path = _seed_v23()
    await init_db(cfg)
    before = _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name")
    async with aiosqlite.connect(db_path) as db:
        assert await apply_migrations(db) == latest_version()
        assert await apply_migrations(db) == latest_version()
    assert _query(db_path, "SELECT type, name, sql FROM sqlite_master ORDER BY name") == before
