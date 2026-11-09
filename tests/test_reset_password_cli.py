"""``python -m roost reset-password <name>``: the operator's way back in. Only the login hash changes."""

from __future__ import annotations

import pytest

from roost.__main__ import main
from roost.config import load_config
from roost.db.connection import close_pool, db_session, init_db
from roost.gateway.auth import authenticate_user, create_session, get_session_user, register_user


async def _setup():
    config = load_config()
    await init_db(config)
    user = await register_user(config, "blck", "old-password-1")
    token = await create_session(config, user.id)
    return config, user, token


async def test_reset_changes_only_the_password_and_ends_sessions(monkeypatch):
    config, user, token = await _setup()
    answers = iter(["new-password-2", "new-password-2"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
    await close_pool()
    await _run(["reset-password", "blck"])
    config = load_config()
    await init_db(config)
    assert await authenticate_user(config, "blck", "new-password-2") is not None
    assert await authenticate_user(config, "blck", "old-password-1") is None
    assert await get_session_user(config, token) is None
    async with db_session(config) as db:
        row = await (await db.execute("SELECT id, encryption_salt FROM users WHERE username='blck'")).fetchone()
    assert row[0] == user.id  # same account, same key material
    await close_pool()


async def test_mismatch_or_short_password_is_refused(monkeypatch, capsys):
    await _setup()
    for pair in (["new-password-2", "different-3"], ["short", "short"]):
        answers = iter(pair)
        monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
        await close_pool()
        with pytest.raises(SystemExit):
            await _run(["reset-password", "blck"])
    await close_pool()


async def test_unknown_user_is_refused(monkeypatch):
    config = load_config()
    await init_db(config)
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "whatever-123")
    await close_pool()
    with pytest.raises(SystemExit):
        await _run(["reset-password", "nobody"])
    await close_pool()


async def _run(argv):
    import asyncio
    await asyncio.to_thread(main, argv)
