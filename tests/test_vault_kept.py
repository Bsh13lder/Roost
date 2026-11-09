"""Vault: site logins and the Sign-in card's "Keep me signed in on this computer?" (schema v27).

A kept login stays (``kept``); a "No, this time" login waits for its continue item to finish, then the site is
cleared and the row goes. Every query names ``user_id``."""

from __future__ import annotations

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.vault.models import site_login_out
from roost.vault.store import VaultStore
from team_helpers import make_bot


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def _user_and_bot(cfg, name="alice"):
    user = await register_user(cfg, name, "pw-123456")
    bot = await make_bot(cfg, user.id, "Scout")
    return user.id, bot.id


async def test_a_login_is_kept_by_default_and_says_so(cfg):
    store = VaultStore(cfg)
    user_id, bot_id = await _user_and_bot(cfg)
    login = await store.remember(user_id, bot_id, "github.com", "work")
    assert login.kept is True and login.clear_after_item_id is None
    assert site_login_out(login).kept is True


async def test_no_this_time_marks_the_login_with_its_continue_item(cfg):
    store = VaultStore(cfg)
    user_id, bot_id = await _user_and_bot(cfg)
    await store.remember(user_id, bot_id, "github.com", "work")
    login = await store.remember(user_id, bot_id, "github.com", "work", kept=False, clear_after_item_id="item-1")
    assert login.kept is False and login.clear_after_item_id == "item-1"
    assert [p.id for p in await store.pending_clears(user_id, bot_id)] == [login.id]
    # Yes later keeps it again and drops the pending clear
    kept = await store.remember(user_id, bot_id, "github.com", "work", kept=True)
    assert kept.kept is True and kept.clear_after_item_id is None
    assert await store.pending_clears(user_id, bot_id) == ()


async def test_pending_clears_are_per_user_and_listed_for_boot(cfg):
    store = VaultStore(cfg)
    alice, alice_bot = await _user_and_bot(cfg)
    bob, bob_bot = await _user_and_bot(cfg, "bob")
    await store.remember(alice, alice_bot, "github.com", "", kept=False, clear_after_item_id="i1")
    await store.remember(bob, bob_bot, "gitlab.com", "", kept=True)
    assert await store.pending_clears(bob, alice_bot) == ()
    assert await store.pending_clears(bob, bob_bot) == ()
    assert await store.pending_bots() == ((alice, alice_bot),)


async def test_get_finds_only_your_own_bots_login(cfg):
    store = VaultStore(cfg)
    alice, bot_id = await _user_and_bot(cfg)
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    login = await store.remember(alice, bot_id, "github.com", "work")
    assert (await store.get(alice, login.id, bot_id)).host == "github.com"
    assert await store.get(bob, login.id, bot_id) is None
    assert await store.get(alice, login.id, "another-bot") is None
