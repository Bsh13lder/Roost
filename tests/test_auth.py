"""Tests for roost/gateway/auth.py's session-cookie dependency.

Minimal, direct exercise of ``get_current_user`` against a hand-built
``starlette.requests.Request`` — no real app/TestClient needed for this
one. ``get_current_user`` reads its config from ``request.app.state``
(the app-factory design — see ``roost/gateway/app.py``), so the stub
request below carries a minimal stand-in ``app`` object exposing just
that attribute, rather than a real ``FastAPI`` instance.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from roost.config import load_config
from roost.db.connection import close_pool, init_db
from roost.gateway.auth import (
    SESSION_COOKIE_NAME,
    create_session,
    get_current_user,
    register_user,
)


def _request_with_cookie(cookie_value: str | None, config) -> Request:
    headers = []
    if cookie_value is not None:
        headers.append((b"cookie", f"{SESSION_COOKIE_NAME}={cookie_value}".encode()))
    app_stub = SimpleNamespace(state=SimpleNamespace(config=config))
    return Request(scope={"type": "http", "headers": headers, "app": app_stub})


@pytest.fixture
def config(tmp_path):
    return load_config({"ROOST_DATA_DIR": str(tmp_path / "data")})


async def test_get_current_user_reads_session_cookie(config):
    await init_db(config)
    try:
        user = await register_user(config, "alice", "Correct-Horse-9")
        session_id = await create_session(config, user.id)

        request = _request_with_cookie(session_id, config)
        resolved = await get_current_user(request)

        assert resolved.id == user.id
        assert resolved.username == "alice"
    finally:
        await close_pool()


async def test_get_current_user_rejects_missing_cookie(config):
    await init_db(config)
    try:
        request = _request_with_cookie(None, config)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)
        assert exc_info.value.status_code == 401
    finally:
        await close_pool()


async def test_get_current_user_rejects_unknown_session(config):
    await init_db(config)
    try:
        request = _request_with_cookie("not-a-real-session-id", config)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)
        assert exc_info.value.status_code == 401
    finally:
        await close_pool()


async def test_register_user_rejects_duplicate_username(config):
    await init_db(config)
    try:
        await register_user(config, "alice", "Correct-Horse-9")
        with pytest.raises(ValueError, match="already taken"):
            await register_user(config, "alice", "Different-Pw-1")
    finally:
        await close_pool()


async def _stored_session_ids(config) -> list[str]:
    from roost.db.connection import db_session

    async with db_session(config) as db:
        cur = await db.execute("SELECT id FROM sessions")
        return [r[0] for r in await cur.fetchall()]


async def test_session_row_holds_a_hash_not_the_cookie(config):
    from roost.gateway.auth import get_session_user

    await init_db(config)
    try:
        user = await register_user(config, "alice", "Correct-Horse-9")
        token = await create_session(config, user.id)
        stored = await _stored_session_ids(config)
        assert token not in stored
        # a stolen DB row used as a cookie is refused
        assert await get_session_user(config, stored[0]) is None
        # the real cookie still works
        assert (await get_session_user(config, token)).id == user.id
    finally:
        await close_pool()


async def test_delete_session_invalidates_it(config):
    from roost.gateway.auth import delete_session, get_session_user

    await init_db(config)
    try:
        user = await register_user(config, "alice", "Correct-Horse-9")
        token = await create_session(config, user.id)
        await delete_session(config, token)
        assert await get_session_user(config, token) is None
        assert await _stored_session_ids(config) == []
    finally:
        await close_pool()
