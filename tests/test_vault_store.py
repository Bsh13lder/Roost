"""VaultStore (Computers 2.0, C2, Task 13): one sealed row per bot and site."""

from __future__ import annotations

import sqlite3

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.gateway.auth import register_user
from roost.vault.models import VaultBotNotFound, normalise_host
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


def _raw(cfg, sql, params=()):
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


async def test_remember_upserts_one_row_per_bot_and_host(cfg):
    store = VaultStore(cfg)
    user_id, bot_id = await _user_and_bot(cfg)
    first = await store.remember(user_id, bot_id, "https://www.GitHub.com/login", "work email")
    again = await store.remember(user_id, bot_id, "github.com", "personal")
    assert again.id == first.id and again.label == "personal" and again.host == "github.com"
    assert len(await store.list_for_bot(user_id, bot_id)) == 1


async def test_host_and_label_are_stored_sealed(cfg):
    store = VaultStore(cfg)
    user_id, bot_id = await _user_and_bot(cfg)
    await store.remember(user_id, bot_id, "github.com", "work email")
    host, label, key = _raw(cfg, "SELECT host, label, host_key FROM site_logins")[0]
    assert host.startswith("enc:v2:") and label.startswith("enc:v2:")
    assert "github" not in host + label + key and "work" not in label


async def test_another_users_bot_cannot_be_written_or_read(cfg):
    store = VaultStore(cfg)
    alice, bot_id = await _user_and_bot(cfg)
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    with pytest.raises(VaultBotNotFound):
        await store.remember(bob, bot_id, "github.com", "x")
    login = await store.remember(alice, bot_id, "github.com", "mine")
    assert await store.list_for_bot(bob, bot_id) == () and await store.list_all(bob) == ()
    assert await store.forget(bob, login.id) is False
    assert await store.forget(alice, login.id) is True


def test_normalise_host():
    assert normalise_host("https://www.Example.com:8443/a?b") == "example.com"
    assert normalise_host("mail.google.com") == "mail.google.com"
    assert normalise_host("about:blank") == "" and normalise_host("") == ""
