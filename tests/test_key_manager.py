"""Tests for roost/crypto/key_manager.py's DEK lifecycle.

``register_user`` already exercises ``create_user_dek`` (Task 1's
tests cover that indirectly), but nothing exercised ``get_user_dek``
itself — the unwrap-and-cache read path — until now. DEK creation AND
retrieval are both explicitly "keep" items for Task 2 (every later
task's encrypted columns depend on this working), so it gets its own
direct coverage rather than relying on later tasks to notice a gap.
"""

from __future__ import annotations

import pytest

from roost.config import load_config
from roost.crypto.encryption import decrypt, encrypt
from roost.crypto.key_manager import clear_user_dek, get_user_dek
from roost.db.connection import close_pool, db_session, init_db
from roost.gateway.auth import register_user


@pytest.fixture
def config(tmp_path):
    return load_config({"ROOST_DATA_DIR": str(tmp_path / "data")})


async def test_get_user_dek_roundtrips_after_register(config):
    await init_db(config)
    try:
        user = await register_user(config, "alice", "pw-123456")
        clear_user_dek(user.id)  # force a cache miss so the unwrap path actually runs

        dek = await get_user_dek(config, user.id)
        assert isinstance(dek, bytes) and len(dek) == 32

        token = encrypt("secret note", dek)
        assert decrypt(token, dek) == "secret note"
    finally:
        await close_pool()


async def test_get_user_dek_cache_hit_returns_same_key(config):
    await init_db(config)
    try:
        user = await register_user(config, "alice", "pw-123456")
        first = await get_user_dek(config, user.id)
        second = await get_user_dek(config, user.id)  # should hit the cache
        assert first == second
    finally:
        await close_pool()


async def test_get_user_dek_unknown_user_raises(config):
    await init_db(config)
    try:
        with pytest.raises(ValueError, match="not found"):
            await get_user_dek(config, "no-such-user")
    finally:
        await close_pool()


async def test_get_user_dek_without_encrypted_dek_raises(config):
    await init_db(config)
    try:
        async with db_session(config) as db:
            await db.execute(
                "INSERT INTO users (id, username, password_hash, encryption_salt) "
                "VALUES ('u1', 'bob', 'hash', 'salt')",
            )
            await db.commit()

        with pytest.raises(ValueError, match="no encryption key"):
            await get_user_dek(config, "u1")
    finally:
        await close_pool()


async def test_clear_user_dek_forces_recompute(config):
    await init_db(config)
    try:
        user = await register_user(config, "alice", "pw-123456")
        first = await get_user_dek(config, user.id)
        clear_user_dek(user.id)
        second = await get_user_dek(config, user.id)  # re-unwrapped, not cached
        assert first == second  # same DEK either way — just recomputed
    finally:
        await close_pool()
