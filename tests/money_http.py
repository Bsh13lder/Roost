"""Shared helpers for the money HTTP tests: two logged-in users on one app."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user

O = {"Origin": "http://127.0.0.1:18800"}
PW = "pw-123456"


@asynccontextmanager
async def two_users() -> AsyncIterator[tuple[httpx.AsyncClient, httpx.AsyncClient, object]]:
    """alice and bob, each logged in, plus the app (for its services)."""
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    for name in ("alice", "bob"):
        await register_user(cfg, name, PW)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            assert (await client.post("/api/auth/login", json={"username": name, "password": PW}, headers=O)
                    ).status_code == 200
        yield alice, bob, app
