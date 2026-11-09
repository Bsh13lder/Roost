"""AppStore (docs/plans/2026-10-22-roost-install-app.md §5): schema v32 ``bot_apps``, the package sealed, one row per
bot and package, every query scoped to the user, and the reinstall list read by bot id at a fresh start."""

from __future__ import annotations

import sqlite3

import pytest

from roost.apps.store import AppBotNotFound, AppStore
from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import latest_version
from roost.gateway.auth import register_user
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


async def test_schema_v32_has_bot_apps(cfg):
    assert latest_version() >= 32
    columns = {row[1] for row in _raw(cfg, "PRAGMA table_info(bot_apps)")}
    assert {"id", "user_id", "bot_id", "package", "package_key", "tainted", "installed_at"} <= columns


async def test_the_package_is_sealed_and_unique_per_bot(cfg):
    store = AppStore(cfg)
    user_id, bot_id = await _user_and_bot(cfg)
    first = await store.add(user_id, bot_id, "gimp", tainted=True)
    again = await store.add(user_id, bot_id, "gimp", tainted=False)
    assert again.id == first.id and first.package == "gimp" and first.tainted
    package, key = _raw(cfg, "SELECT package, package_key FROM bot_apps")[0]
    assert package.startswith("enc:v2:") and "gimp" not in package + key
    assert [a.package for a in await store.list_for_bot(user_id, bot_id)] == ["gimp"]
    assert (await store.find(user_id, bot_id, "gimp")).id == first.id
    assert await store.find(user_id, bot_id, "vlc") is None


async def test_another_user_sees_nothing_and_writes_nothing(cfg):
    store = AppStore(cfg)
    alice, bot_id = await _user_and_bot(cfg)
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    app = await store.add(alice, bot_id, "gimp", tainted=False)
    with pytest.raises(AppBotNotFound):
        await store.add(bob, bot_id, "vlc", tainted=False)
    assert await store.list_for_bot(bob, bot_id) == ()
    assert await store.get(bob, bot_id, app.id) is None
    assert await store.delete(bob, bot_id, app.id) is False
    assert await store.get(alice, bot_id, app.id) is not None


async def test_delete_and_the_reinstall_list(cfg):
    store = AppStore(cfg)
    user_id, bot_id = await _user_and_bot(cfg)
    gimp = await store.add(user_id, bot_id, "gimp", tainted=False)
    await store.add(user_id, bot_id, "vlc", tainted=False)
    assert await store.owner_of(bot_id) == user_id
    assert sorted(await store.packages(user_id, bot_id)) == ["gimp", "vlc"]
    assert await store.delete(user_id, bot_id, gimp.id) is True
    assert await store.packages(user_id, bot_id) == ("vlc",)
    assert await store.owner_of("no-such-bot") is None
