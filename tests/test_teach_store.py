"""The sealed teach step log: one per bot, sealed under teach_sessions:steps, another user's is not there."""

from __future__ import annotations

import sqlite3

import pytest

from roost.config import load_config
from roost.constants import TEACH_STEPS_MAX
from roost.db.connection import get_db_path, init_db
from roost.gateway.auth import register_user
from roost.teach.models import TeachStep
from roost.teach.store import TeachStore
from team_helpers import make_bot

STEP = TeachStep(kind="click", host="shop.example", path="/", title="Shop", role="link", label="Orders")


@pytest.fixture
async def world():
    cfg = load_config()
    await init_db(cfg)
    alice = (await register_user(cfg, "alice", "pw-123456")).id
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bot = await make_bot(cfg, alice, "Scout")
    return cfg, alice, bob, bot.id


def _raw(cfg) -> list[tuple]:
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute("SELECT steps, step_count, capped FROM teach_sessions").fetchall()
    finally:
        con.close()


async def test_begin_append_get_and_delete(world):
    cfg, alice, _, bot = world
    store = TeachStore(cfg)
    first = await store.begin(alice, bot)
    assert first.steps == () and not first.capped
    assert await store.append(alice, bot, STEP) is True
    session = await store.get(alice, bot)
    assert session.steps == (STEP,) and session.id == first.id
    [(sealed, count, capped)] = _raw(cfg)
    assert sealed.startswith("enc:v2:") and "Orders" not in sealed and count == 1 and capped == 0
    await store.delete(alice, bot)
    assert await store.get(alice, bot) is None and _raw(cfg) == []


async def test_begin_again_starts_over(world):
    cfg, alice, _, bot = world
    store = TeachStore(cfg)
    await store.begin(alice, bot)
    await store.append(alice, bot, STEP)
    again = await store.begin(alice, bot)
    assert again.steps == () and len(_raw(cfg)) == 1


async def test_a_repeat_is_kept_once_and_the_cap_holds(world):
    cfg, alice, _, bot = world
    store = TeachStore(cfg)
    await store.begin(alice, bot)
    await store.append(alice, bot, STEP)
    assert await store.append(alice, bot, STEP) is False
    for n in range(TEACH_STEPS_MAX + 3):
        await store.append(alice, bot, TeachStep(kind="click", host="shop.example", label=f"Item {n}"))
    session = await store.get(alice, bot)
    assert len(session.steps) == TEACH_STEPS_MAX and session.capped
    assert _raw(cfg)[0][1:] == (TEACH_STEPS_MAX, 1)


async def test_another_users_session_is_not_there(world):
    cfg, alice, bob, bot = world
    store = TeachStore(cfg)
    await store.begin(alice, bot)
    assert await store.get(bob, bot) is None
    assert await store.append(bob, bot, STEP) is False
    await store.delete(bob, bot)
    assert (await store.get(alice, bot)).steps == ()


async def test_append_without_a_session_does_nothing(world):
    cfg, alice, _, bot = world
    assert await TeachStore(cfg).append(alice, bot, STEP) is False
    assert await TeachStore(cfg).get(alice, bot) is None
