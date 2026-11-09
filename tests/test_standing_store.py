"""Standing permissions (docs/plans/2026-10-23-roost-full-computer.md Step 2): schema v33 ``routine_permissions``,
the host sealed with a keyed HMAC key, one live permission per routine, host and action, every query scoped to the
user, and the day's count kept by an atomic compare-and-set."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import latest_version
from roost.gateway.auth import register_user
from roost.routines.models import RoutineDraft
from roost.routines.schedule import parse_schedule
from roost.routines.store import RoutineStore
from roost.standing.models import PermissionIn
from roost.standing.store import PermissionStore
from roost.talk.store import TalkStore
from team_helpers import make_bot

TIMES = {"kind": "times", "days": [1], "times": ["10:00"]}
TODAY = "2026-10-23"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


def _raw(cfg, sql, params=()):
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


async def _routine(cfg, name="alice"):
    user = await register_user(cfg, name, "pw-123456")
    bot = await make_bot(cfg, user.id, "Poster")
    routine = await RoutineStore(cfg, TalkStore(cfg)).create(user.id, RoutineDraft(
        bot_id=bot.id, name="Weekly post", instructions="Post the weekly update on x.com.",
        schedule=parse_schedule(TIMES), created_by="user"))
    return user.id, bot.id, routine.id


def _draft(**kw) -> PermissionIn:
    return PermissionIn(**{"host": "x.com", "action": "post", "max_per_day": 2, "until": date(2026, 11, 1), **kw})


async def test_schema_v33_has_routine_permissions(cfg):
    assert latest_version() >= 33
    columns = {row[1] for row in _raw(cfg, "PRAGMA table_info(routine_permissions)")}
    assert {"id", "user_id", "bot_id", "routine_id", "host", "host_key", "action", "max_per_day", "until",
            "created_at", "revoked_at", "used_day", "used_count"} <= columns


async def test_the_host_is_sealed_and_read_back(cfg):
    store = PermissionStore(cfg)
    user_id, bot_id, routine_id = await _routine(cfg)
    made = await store.create(user_id, routine_id, _draft(host="WWW.X.com"))
    assert made.host == "x.com" and made.action == "post" and made.max_per_day == 2 and made.until == "2026-11-01"
    host, key = _raw(cfg, "SELECT host, host_key FROM routine_permissions")[0]
    assert host.startswith("enc:v2:") and "x.com" not in host + key
    assert [p.id for p in await store.list_for_routine(user_id, routine_id, TODAY)] == [made.id]


async def test_the_same_host_and_action_replaces_the_live_one(cfg):
    store = PermissionStore(cfg)
    user_id, bot_id, routine_id = await _routine(cfg)
    first = await store.create(user_id, routine_id, _draft())
    second = await store.create(user_id, routine_id, _draft(max_per_day=5))
    other = await store.create(user_id, routine_id, _draft(action="send"))
    live = await store.list_for_routine(user_id, routine_id, TODAY)
    assert {p.id for p in live} == {second.id, other.id} and first.id not in {p.id for p in live}


async def test_live_permissions_drop_revoked_and_ended_ones(cfg):
    store = PermissionStore(cfg)
    user_id, bot_id, routine_id = await _routine(cfg)
    made = await store.create(user_id, routine_id, _draft())
    live = await store.live_for_routine(user_id, routine_id, TODAY)
    assert [(p.id, p.host, p.action, p.remaining) for p in live] == [(made.id, "x.com", "post", 2)]
    assert await store.live_for_routine(user_id, routine_id, "2026-11-02") == ()
    assert await store.revoke(user_id, routine_id, made.id) is True
    assert await store.live_for_routine(user_id, routine_id, TODAY) == ()
    assert await store.revoke(user_id, routine_id, made.id) is False


async def test_consume_counts_per_madrid_day_and_stops_at_the_cap(cfg):
    store = PermissionStore(cfg)
    user_id, bot_id, routine_id = await _routine(cfg)
    made = await store.create(user_id, routine_id, _draft(max_per_day=2))
    assert await store.consume(user_id, made.id, TODAY) is True
    assert await store.consume(user_id, made.id, TODAY) is True
    assert await store.consume(user_id, made.id, TODAY) is False
    assert await store.is_live(user_id, made.id, TODAY) is False
    assert (await store.live_for_routine(user_id, routine_id, TODAY)) == ()
    assert await store.consume(user_id, made.id, "2026-10-24") is True     # a new day starts again
    assert await store.consume(user_id, made.id, "2026-11-02") is False    # past its end date


async def test_another_user_sees_nothing_and_changes_nothing(cfg):
    store = PermissionStore(cfg)
    alice, bot_id, routine_id = await _routine(cfg)
    bob, _, _ = await _routine(cfg, "bob")
    made = await store.create(alice, routine_id, _draft())
    assert await store.list_for_routine(bob, routine_id, TODAY) == ()
    assert await store.live_for_routine(bob, routine_id, TODAY) == ()
    assert await store.revoke(bob, routine_id, made.id) is False
    assert await store.consume(bob, made.id, TODAY) is False
    assert await store.is_live(bob, made.id, TODAY) is False
    assert await store.is_live(alice, made.id, TODAY) is True


async def test_deleting_the_routine_removes_its_permissions(cfg):
    store = PermissionStore(cfg)
    user_id, bot_id, routine_id = await _routine(cfg)
    await store.create(user_id, routine_id, _draft())
    await RoutineStore(cfg, TalkStore(cfg)).delete(user_id, routine_id)
    assert _raw(cfg, "SELECT COUNT(*) FROM routine_permissions")[0][0] == 0
