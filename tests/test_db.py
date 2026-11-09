"""Contract test: the full Night-1 schema applies with foreign keys on.

Verbatim from the Task 2 brief — exercises ``load_config()`` with no
explicit override (relies on the per-test ``ROOST_DATA_DIR`` fixture in
``conftest.py``) against the real ``schema.sql``.
"""

from __future__ import annotations

from roost.config import load_config
from roost.db.connection import init_db, db_session


async def test_schema_and_foreign_keys():
    cfg = load_config()
    await init_db(cfg)
    async with db_session(cfg) as db:
        assert (await (await db.execute("PRAGMA foreign_keys")).fetchone())[0] == 1
        names = {
            r[0]
            for r in await (
                await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
        assert {"users", "sessions", "bots", "threads", "messages", "events", "audit"} <= names


async def test_schema_has_expected_indexes():
    cfg = load_config()
    await init_db(cfg)
    async with db_session(cfg) as db:
        names = {
            r[0]
            for r in await (
                await db.execute("SELECT name FROM sqlite_master WHERE type='index'")
            ).fetchall()
        }
    assert {
        "idx_bots_user",
        "idx_threads_bot",
        "idx_messages_thread",
        "idx_events_user",
    } <= names


async def test_init_db_is_idempotent():
    cfg = load_config()
    await init_db(cfg)
    await init_db(cfg)  # must not raise on a second call against the same dir
