"""Migrating from the schema the live gateway runs at the start of the stuck flow (version 11).

``tests/fixtures/schema_v11.sql`` was frozen by stuck-flow Task 3. Rows go in
every table the user's account uses today (the v10 test's rows); v12 adds the
``stuck_cards`` table, one open card per bot, gone with its bot or its chat."""

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

_V11_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v11.sql"
_STUCK_COLUMNS = {
    "id", "user_id", "bot_id", "thread_id", "work_item_id", "reason", "url", "note", "request",
    "suggest_main_browser", "tainted", "main_opened", "state", "answer_item_id", "created_at", "closed_at",
    "sign_in",   # the Sign-in card
    "secret_field",   # B3: its masked field (v35)
    "replied",   # answered in the chat (v38)
}
_CARD = ("INSERT INTO stuck_cards (id, user_id, bot_id, thread_id, reason, url, request, state, created_at) "
         "VALUES (?, 'u1', 'b2', ?, ?, 'enc:u', 'enc:r', ?, ?)")


def _query(db_path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def _version(db_path: Path) -> int:
    return _query(db_path, "PRAGMA user_version")[0][0]


def _counts(db_path: Path) -> dict[str, int]:
    return {table: _query(db_path, f"SELECT COUNT(*) FROM {table}")[0][0] for table in _V10_EXPECTED}


def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


@pytest.fixture
def seeded_v11():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(_V11_SCHEMA.read_text())
        con.execute("PRAGMA user_version = 11")
        for statement in _V10_ROWS:
            con.execute(statement)
        con.commit()
    finally:
        con.close()
    return cfg, db_path


async def test_v11_database_migrates_to_latest_and_keeps_every_row(seeded_v11):
    cfg, db_path = seeded_v11
    await init_db(cfg)
    assert latest_version() >= 12
    assert _version(db_path) == latest_version()
    assert _counts(db_path) == _V10_EXPECTED


async def test_v11_database_gains_the_stuck_cards_table(seeded_v11):
    cfg, db_path = seeded_v11
    await init_db(cfg)
    assert {row[1] for row in _query(db_path, "PRAGMA table_info(stuck_cards)")} == _STUCK_COLUMNS
    indexes = {row[0] for row in _query(
        db_path, "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'stuck_cards'",
    )}
    assert {"idx_stuck_cards_one_open", "idx_stuck_cards_user"} <= indexes
    assert _query(db_path, "SELECT COUNT(*) FROM stuck_cards") == [(0,)]


async def test_a_bot_can_have_only_one_open_stuck_card(seeded_v11):
    cfg, db_path = seeded_v11
    await init_db(cfg)
    con = _connect(db_path)
    try:
        con.execute(_CARD, ("c1", "t1", "login", "cleared", _NOW))
        con.execute(_CARD, ("c2", "t1", "login", "open", _NOW))
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(_CARD, ("c3", "t1", "challenge", "open", _NOW))
    finally:
        con.close()


async def test_a_stuck_cards_reason_and_state_are_checked(seeded_v11):
    cfg, db_path = seeded_v11
    await init_db(cfg)
    con = _connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(_CARD, ("c1", "t1", "bored", "open", _NOW))
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(_CARD, ("c2", "t1", "login", "paused", _NOW))
    finally:
        con.close()


async def test_a_stuck_card_goes_with_its_chat_and_with_its_bot(seeded_v11):
    cfg, db_path = seeded_v11
    await init_db(cfg)
    con = _connect(db_path)
    try:
        con.execute("INSERT INTO threads (id, user_id, bot_id, kind, created_at, updated_at) "
                    f"VALUES ('t3','u1','b2','chat','{_NOW}','{_NOW}')")
        con.execute(_CARD, ("c1", "t1", "login", "open", _NOW))
        con.execute(_CARD, ("c2", "t3", "code", "cleared", _NOW))
        con.execute("DELETE FROM threads WHERE id = 't1'")
        assert [row[0] for row in con.execute("SELECT id FROM stuck_cards")] == ["c2"]
        con.execute("DELETE FROM bots WHERE id = 'b2'")
        assert con.execute("SELECT COUNT(*) FROM stuck_cards").fetchone() == (0,)
    finally:
        con.close()


async def test_migrating_v11_twice_is_a_no_op_and_backs_up_once(seeded_v11):
    cfg, db_path = seeded_v11
    await init_db(cfg)
    await init_db(cfg)
    assert _counts(db_path) == _V10_EXPECTED
    [backup] = sorted(db_path.parent.glob(f"roost.db.pre-v{latest_version()}-*.bak"))
    assert _version(backup) == 11
