"""Tests for roost/db/connection.py — schema application, pragmas, cascade
delete, and the corruption guard.

Every DB-touching test gets its own ``RoostConfig`` pointed at a fresh
``tmp_path`` (never the session-wide throwaway dir) so each test's
connection pool entry has a unique key and tests can't interfere with
each other; each test closes the pool it opened when done.
"""

from __future__ import annotations

import pytest

from roost.config import load_config
from roost.db.connection import (
    DatabaseCorruptionError,
    close_pool,
    db_session,
    get_db_path,
    init_db,
)


@pytest.fixture
def config(tmp_path):
    return load_config({"ROOST_DATA_DIR": str(tmp_path / "data")})


async def test_init_db_creates_users_and_sessions_tables(config):
    await init_db(config)
    try:
        async with db_session(config) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name IN ('users', 'sessions')"
            )
            names = {row[0] for row in await cursor.fetchall()}
        assert names == {"users", "sessions"}
    finally:
        await close_pool()


async def test_db_session_connection_has_foreign_keys_on(config):
    await init_db(config)
    try:
        async with db_session(config) as db:
            cursor = await db.execute("PRAGMA foreign_keys")
            row = await cursor.fetchone()
        assert row[0] == 1
    finally:
        await close_pool()


async def test_deleting_user_cascades_to_sessions(config):
    await init_db(config)
    try:
        async with db_session(config) as db:
            await db.execute(
                "INSERT INTO users (id, username, password_hash, encryption_salt) "
                "VALUES ('u1', 'alice', 'hash', 'salt')"
            )
            await db.execute(
                "INSERT INTO sessions (id, user_id, expires_at) "
                "VALUES ('s1', 'u1', '2099-01-01T00:00:00')"
            )
            await db.commit()

            cursor = await db.execute("SELECT COUNT(*) FROM sessions WHERE id = 's1'")
            assert (await cursor.fetchone())[0] == 1

            await db.execute("DELETE FROM users WHERE id = 'u1'")
            await db.commit()

            cursor = await db.execute("SELECT COUNT(*) FROM sessions WHERE id = 's1'")
            assert (await cursor.fetchone())[0] == 0
    finally:
        await close_pool()


async def test_corrupt_db_is_backed_up_and_raises(config):
    await init_db(config)
    db_path = get_db_path(config)
    await close_pool()

    # Clear WAL/SHM sidecars so the corruption below is deterministic —
    # otherwise SQLite could treat a stale WAL as authoritative over the
    # (now-garbage) main file.
    for sidecar in db_path.parent.glob(f"{db_path.name}-*"):
        sidecar.unlink()

    garbage = b"not a sqlite file at all"
    db_path.write_bytes(garbage)

    with pytest.raises(DatabaseCorruptionError):
        await init_db(config)

    backups = list(db_path.parent.glob(f"{db_path.name}.corrupt-*.bak"))
    assert len(backups) == 1
    # Copied aside, never deleted or modified.
    assert db_path.read_bytes() == garbage
    assert backups[0].read_bytes() == garbage


async def test_close_pool_clears_the_pool(config):
    await init_db(config)
    async with db_session(config):
        pass
    await close_pool()

    # A fresh call after close_pool() must open a brand new connection,
    # not reuse a closed one — proves the pool dict was actually cleared.
    async with db_session(config) as db:
        cursor = await db.execute("SELECT 1")
        assert (await cursor.fetchone())[0] == 1
    await close_pool()
