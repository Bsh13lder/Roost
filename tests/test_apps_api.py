"""The Apps list on the Computer tab (docs/plans/2026-10-22-roost-install-app.md §7): list and Remove, the owner's
own click with no card. Another user's bot or app is a 404, never the row. Fake desk mode: the fake keeper seam."""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}
PASSWORD = "pw-123456"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@asynccontextmanager
async def _signed_in(app, username: str):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        assert (await client.post("/api/auth/login", json={"username": username, "password": PASSWORD},
                                  headers=O)).status_code == 200
        yield client


async def _setup(cfg):
    app = create_app()
    alice = await register_user(cfg, "alice", PASSWORD)
    await register_user(cfg, "bob", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Scout")
    app_row = await app.state.apps.store.add(alice.id, bot.id, "gimp", tainted=False)
    app.state.app_keeper.installed = {bot.id: {"gimp"}}
    return app, alice, bot, app_row


async def test_the_owner_lists_and_removes_an_app(cfg):
    app, _, bot, row = await _setup(cfg)
    async with _signed_in(app, "alice") as client:
        listed = (await client.get(f"/api/bots/{bot.id}/apps")).json()
        assert listed == [{"id": row.id, "package": "gimp", "installed_at": row.installed_at}]
        assert (await client.delete(f"/api/bots/{bot.id}/apps/{row.id}", headers=O)).status_code == 204
        assert (await client.get(f"/api/bots/{bot.id}/apps")).json() == []
        assert (await client.delete(f"/api/bots/{bot.id}/apps/{row.id}", headers=O)).status_code == 404
    assert app.state.app_keeper.installed[bot.id] == set()


async def test_another_users_bot_or_app_is_404(cfg):
    app, _, bot, row = await _setup(cfg)
    async with _signed_in(app, "bob") as client:
        assert (await client.get(f"/api/bots/{bot.id}/apps")).status_code == 404
        assert (await client.delete(f"/api/bots/{bot.id}/apps/{row.id}", headers=O)).status_code == 404
    assert app.state.app_keeper.installed[bot.id] == {"gimp"}
    assert len(await app.state.apps.store.list_for_bot(row.user_id, bot.id)) == 1


async def test_remove_needs_the_origin_header(cfg):
    app, _, bot, row = await _setup(cfg)
    async with _signed_in(app, "alice") as client:
        assert (await client.delete(f"/api/bots/{bot.id}/apps/{row.id}")).status_code == 403


async def test_an_unreachable_computer_keeps_the_row(cfg):
    app, alice, bot, row = await _setup(cfg)
    app.state.app_keeper.fail = True
    async with _signed_in(app, "alice") as client:
        response = await client.delete(f"/api/bots/{bot.id}/apps/{row.id}", headers=O)
    assert response.status_code == 503
    assert len(await app.state.apps.store.list_for_bot(alice.id, bot.id)) == 1
