"""python -m roost.gateway.reset_password: list usernames, set a new password from the terminal."""

from __future__ import annotations

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import authenticate_user, create_session, get_session_user, register_user
from roost.gateway.reset_password import ResetError, list_usernames, main, reset_password


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def test_it_lists_the_usernames(cfg):
    await register_user(cfg, "blckit", "old-pass-123")
    assert await list_usernames(cfg) == ("blckit",)


async def test_a_reset_lets_the_new_password_in_and_ends_old_sessions(cfg):
    user = await register_user(cfg, "blckit", "old-pass-123")
    token = await create_session(cfg, user.id)
    await reset_password(cfg, "blckit", "new-pass-456")
    assert await authenticate_user(cfg, "blckit", "new-pass-456") == user
    assert await authenticate_user(cfg, "blckit", "old-pass-123") is None
    assert await get_session_user(cfg, token) is None


async def test_an_unknown_user_or_a_short_password_is_refused(cfg):
    await register_user(cfg, "blckit", "old-pass-123")
    with pytest.raises(ResetError, match="No Roost user named bick"):
        await reset_password(cfg, "bick", "new-pass-456")
    with pytest.raises(ResetError, match="at least"):
        await reset_password(cfg, "blckit", "x")
    assert await authenticate_user(cfg, "blckit", "old-pass-123") is not None


def test_main_never_prints_the_password(cfg, capsys, monkeypatch):
    import asyncio
    asyncio.run(register_user(cfg, "blckit", "old-pass-123"))
    answers = iter(["new-pass-456", "new-pass-456"])
    monkeypatch.setattr("roost.gateway.reset_password.getpass.getpass", lambda _prompt: next(answers))
    assert main(["blckit"]) == 0
    out = capsys.readouterr()
    assert "new-pass-456" not in out.out + out.err
    assert "Password changed for blckit" in out.out


def test_main_refuses_when_the_two_passwords_differ(cfg, capsys, monkeypatch):
    import asyncio
    asyncio.run(register_user(cfg, "blckit", "old-pass-123"))
    answers = iter(["new-pass-456", "other-pass-789"])
    monkeypatch.setattr("roost.gateway.reset_password.getpass.getpass", lambda _prompt: next(answers))
    assert main(["blckit"]) == 1
    assert "didn't match" in capsys.readouterr().err
