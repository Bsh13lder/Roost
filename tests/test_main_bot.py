"""S1 D4: the main bot exists from the start; never two, never none."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from roost.bots.main_bot import ensure_main_bot, ensure_main_bots
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from live_shape import counts, main_bot_ids, seed_live_account

O = {"Origin": "http://127.0.0.1:18800"}
AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}


@pytest.fixture
def cfg():
    return load_config()


async def test_an_account_with_an_unstarred_chief_gets_it_starred_and_nothing_else(cfg):
    user_id = await seed_live_account(cfg)
    before = counts(cfg)
    result = await ensure_main_bot(BotStore(cfg), user_id)
    assert (result.bot.name, result.created, result.starred) == ("Chief", False, True)
    assert counts(cfg) == before
    assert main_bot_ids(cfg, user_id) == [result.bot.id]


async def test_running_it_again_changes_nothing(cfg):
    user_id = await seed_live_account(cfg)
    first = await ensure_main_bot(BotStore(cfg), user_id)
    before = counts(cfg)
    again = await ensure_main_bot(BotStore(cfg), user_id)
    assert (again.bot.id, again.created, again.starred) == (first.bot.id, False, False)
    assert counts(cfg) == before


async def test_an_existing_main_bot_keeps_the_star(cfg):
    user_id = await seed_live_account(cfg, star="Life admin")
    before = counts(cfg)
    result = await ensure_main_bot(BotStore(cfg), user_id)
    assert (result.bot.name, result.created, result.starred) == ("Life admin", False, False)
    assert counts(cfg) == before


async def test_a_bot_named_chief_without_the_template_is_starred_not_duplicated(cfg):
    user_id = await seed_live_account(cfg, bots=(("chief", None), ("Scout", None)))
    before = counts(cfg)
    result = await ensure_main_bot(BotStore(cfg), user_id)
    assert (result.bot.name, result.created) == ("chief", False)
    assert counts(cfg) == before


async def test_a_bot_named_chief_with_a_trailing_space_is_starred_not_duplicated(cfg):
    # BOT_NAME_PATTERN allows a trailing space and BotForm.tsx can send one (phone
    # keyboard autocomplete) — `_chief_in` must match it the same way `_name_key`
    # treats it as the same name, or `create("Chief")` 409s as a duplicate.
    user_id = await seed_live_account(cfg, bots=(("Chief ", None), ("Scout", None)))
    before = counts(cfg)
    result = await ensure_main_bot(BotStore(cfg), user_id)
    assert (result.bot.name, result.created, result.starred) == ("Chief ", False, True)
    assert counts(cfg) == before


async def test_an_account_without_a_chief_gets_one_created_and_starred(cfg):
    user_id = await seed_live_account(cfg, bots=(("Life admin", None),))
    before = counts(cfg)
    result = await ensure_main_bot(BotStore(cfg), user_id)
    assert (result.bot.name, result.bot.template_id, result.created, result.starred) == ("Chief", "chief", True, True)
    assert counts(cfg) == {**before, "bots": before["bots"] + 1}
    assert (await ensure_main_bot(BotStore(cfg), user_id)).created is False
    assert counts(cfg)["bots"] == before["bots"] + 1


async def test_boot_gives_every_account_its_own_main_bot(cfg):
    alice = await seed_live_account(cfg, bots=(("Scout", None),))
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    await ensure_main_bots(cfg, BotStore(cfg))
    await ensure_main_bots(cfg, BotStore(cfg))
    assert len(main_bot_ids(cfg, alice)) == 1 and len(main_bot_ids(cfg, bob)) == 1
    [bobs_chief] = await BotStore(cfg).list(bob)
    assert (bobs_chief.name, bobs_chief.is_primary) == ("Chief", True)
    assert {b.name for b in await BotStore(cfg).list(alice)} == {"Scout", "Chief"}


def test_registering_lands_with_the_main_bot_already_pinned():
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    bots = c.get("/api/bots").json()
    assert [(b["name"], b["is_primary"], b["template_id"]) for b in bots] == [("Chief", True, "chief")]


async def test_the_gateway_boot_stars_a_chief_for_an_account_made_before_s1():
    cfg = load_config()
    await init_db(cfg)
    await register_user(cfg, "alice", "pw-123456")           # no bot, no star: the pre-S1 shape
    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
            assert (await client.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"},
                                      headers=O)).status_code == 200
            bots = (await client.get("/api/bots")).json()
    assert [(b["name"], b["is_primary"]) for b in bots] == [("Chief", True)]


def _client_with_scout() -> tuple[TestClient, dict, dict]:
    c = TestClient(create_app())
    c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    scout = c.post("/api/bots", json={"name": "Scout", "job": "finds", "instructions": "", "avatar": AVATAR},
                   headers=O).json()
    chief = next(b for b in c.get("/api/bots").json() if b["is_primary"])
    return c, chief, scout


def test_the_star_moves_but_never_vanishes():
    c, chief, scout = _client_with_scout()
    r = c.delete(f"/api/bots/{chief['id']}/star", headers=O)
    assert r.status_code == 409
    assert r.json()["detail"] == "There is always a main bot. Make another bot the main bot instead."
    assert c.post(f"/api/bots/{scout['id']}/star", headers=O).json()["is_primary"] is True
    assert [b["name"] for b in c.get("/api/bots").json() if b["is_primary"]] == ["Scout"]


def test_the_main_bot_cannot_be_retired_until_the_star_moves():
    c, chief, scout = _client_with_scout()
    r = c.delete(f"/api/bots/{chief['id']}", headers=O)
    assert r.status_code == 409
    assert r.json()["detail"] == "Make another bot the main bot before you retire Chief."
    c.post(f"/api/bots/{scout['id']}/star", headers=O)
    assert c.delete(f"/api/bots/{chief['id']}", headers=O).status_code == 204
