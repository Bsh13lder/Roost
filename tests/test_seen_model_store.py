"""``SeenModelStore``: models the daily check found, and who dismissed the notice."""

from __future__ import annotations

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.models_check.store import SeenModelStore


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def store(cfg):
    return SeenModelStore(cfg)


async def test_seen_models_add_only_new_ids(store):
    assert await store.add_new({"claude-x-1": "X 1", "claude-y-1": "Y 1"}) == ("claude-x-1", "claude-y-1")
    assert await store.add_new({"claude-x-1": "X renamed", "claude-z-1": "Z 1"}) == ("claude-z-1",)
    assert await store.ids() == frozenset({"claude-x-1", "claude-y-1", "claude-z-1"})
    assert (await store.labels())["claude-x-1"] == "X 1"


async def test_a_dismissal_hides_the_notice_for_that_user_only(cfg, store):
    alice = (await register_user(cfg, "alice", "pw-123456")).id
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    assert await store.newest_undismissed(alice) is None
    await store.add_new({"claude-x-1": "X 1"})
    assert await store.newest_undismissed(alice) == ("claude-x-1", "X 1")
    await store.dismiss(alice, "claude-x-1")
    await store.dismiss(alice, "claude-x-1")   # twice is fine
    assert await store.newest_undismissed(alice) is None
    assert await store.newest_undismissed(bob) == ("claude-x-1", "X 1")
