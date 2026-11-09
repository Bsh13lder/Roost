"""RoutineStore: sealed text, scoped by user, a compare-and-swap slot claim (fake clock, no sleeping)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.gateway.auth import register_user
from roost.routines.models import RoutineDraft, RoutinePatch
from roost.routines.schedule import jitter_seconds, next_after, parse_schedule
from roost.routines.store import RoutineStore
from roost.talk.store import TalkStore
from roost.timezones import set_local_tz
from team_helpers import make_bot

UTC = timezone.utc
MADRID = ZoneInfo("Europe/Madrid")
NOW = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)   # 10:00 in Madrid
SCHEDULE = parse_schedule({"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["10:07", "15:07"]})


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def alice(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture
async def bob(cfg):
    return (await register_user(cfg, "bob", "pw-123456")).id


@pytest.fixture
def clock():
    return FakeClock(NOW)


@pytest.fixture
def store(cfg, clock):
    return RoutineStore(cfg, TalkStore(cfg), clock=clock)


def draft(bot_id: str, name: str = "Morning news", **kw) -> RoutineDraft:
    return RoutineDraft(bot_id=bot_id, name=name, instructions="Read the headlines.", schedule=SCHEDULE,
                        created_by=kw.pop("created_by", "user"), **kw)


def raw(cfg, sql: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


async def test_create_seals_every_text_column(cfg, store, alice):
    bot = await make_bot(cfg, alice, "Scout")
    routine = await store.create(alice, draft(bot.id))
    row = raw(cfg, "SELECT name, instructions, schedule, builtin, created_by FROM routines WHERE id = ?", (routine.id,))[0]
    assert all(value.startswith("enc:v2:") for value in row[:3])
    assert "Morning news" not in row[0] and "headlines" not in row[1] and "10:07" not in row[2]
    assert row[3:] == (None, "user")
    back = await store.get(alice, routine.id)
    assert (back.name, back.instructions, back.schedule) == ("Morning news", "Read the headlines.", SCHEDULE)
    assert back.enabled and not back.tainted and back.created_by == "user"


async def test_create_sets_the_next_run_with_jitter_from_the_clock(cfg, store, alice):
    bot = await make_bot(cfg, alice, "Scout")
    routine = await store.create(alice, draft(bot.id))
    slot = next_after(SCHEDULE, NOW)
    assert slot == datetime(2026, 10, 21, 8, 7, tzinfo=UTC)
    assert routine.next_run_at == slot + timedelta(seconds=jitter_seconds(routine.id, slot))
    assert routine.last_run_at is None
    off = await store.create(alice, draft(bot.id, "Off one", enabled=False))
    assert off.next_run_at is None and not off.enabled


async def test_create_makes_a_routine_thread(cfg, store, alice):
    bot = await make_bot(cfg, alice, "Scout")
    routine = await store.create(alice, draft(bot.id))
    thread = await TalkStore(cfg).get_thread(alice, routine.thread_id)
    assert thread is not None and thread.kind == "routine" and thread.bot_id == bot.id
    assert thread.title == "Morning news"


async def test_create_for_a_bot_that_is_not_there_leaves_nothing_behind(cfg, store, alice):
    with pytest.raises(ValueError):
        await store.create(alice, draft("no-such-bot"))
    assert raw(cfg, "SELECT count(*) FROM routines") == [(0,)]
    assert raw(cfg, "SELECT count(*) FROM threads WHERE kind = 'routine'") == [(0,)]


async def test_due_is_scoped_by_user(cfg, store, clock, alice, bob):
    a_bot, b_bot = await make_bot(cfg, alice, "Scout"), await make_bot(cfg, bob, "Other")
    mine = await store.create(alice, draft(a_bot.id))
    theirs = await store.create(bob, draft(b_bot.id))
    off = await store.create(alice, draft(a_bot.id, "Off", enabled=False))
    assert await store.due(alice, NOW) == ()
    later = max(mine.next_run_at, theirs.next_run_at) + timedelta(minutes=1)   # both are due, even across a slot edge
    assert [r.id for r in await store.due(alice, later)] == [mine.id]
    assert [r.id for r in await store.due(bob, later)] == [theirs.id]
    assert off.id not in [r.id for r in await store.due(alice, later + timedelta(days=9))]


async def test_due_lists_the_oldest_first_and_honours_a_limit(cfg, store, alice):
    bot = await make_bot(cfg, alice, "Scout")
    first = await store.create(alice, draft(bot.id, "A"))
    second = await store.create(alice, draft(bot.id, "B"))
    future = NOW + timedelta(days=2)
    got = await store.due(alice, future)
    assert [r.next_run_at for r in got] == sorted(r.next_run_at for r in got)
    assert {r.id for r in got} == {first.id, second.id}
    assert len(await store.due(alice, future, limit=1)) == 1


async def test_claim_slot_is_a_compare_and_swap(cfg, store, clock, alice, bob):
    bot = await make_bot(cfg, alice, "Scout")
    routine = await store.create(alice, draft(bot.id))
    new_next = routine.next_run_at + timedelta(hours=5)
    ran_at = routine.next_run_at + timedelta(seconds=3)
    assert await store.claim_slot(bob, routine.id, routine.next_run_at, new_next, ran_at) is False
    assert await store.claim_slot(alice, routine.id, routine.next_run_at - timedelta(minutes=1), new_next, ran_at) is False
    assert await store.claim_slot(alice, routine.id, routine.next_run_at, new_next, ran_at) is True
    assert await store.claim_slot(alice, routine.id, routine.next_run_at, new_next, ran_at) is False   # the loser
    after = await store.get(alice, routine.id)
    assert after.next_run_at == new_next and after.last_run_at == ran_at


async def test_disable_clears_next_run_and_enable_never_replays(cfg, store, clock, alice):
    bot = await make_bot(cfg, alice, "Scout")
    routine = await store.create(alice, draft(bot.id))
    off = await store.set_enabled(alice, routine.id, False)
    assert off.next_run_at is None and not off.enabled
    assert await store.due(alice, NOW + timedelta(days=30)) == ()
    clock.now = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)   # a week of slots passed while it was off
    on = await store.set_enabled(alice, routine.id, True)
    slot = next_after(SCHEDULE, clock.now)
    assert on.enabled and on.next_run_at == slot + timedelta(seconds=jitter_seconds(routine.id, slot))
    assert on.next_run_at > clock.now


async def test_another_users_routine_is_none(cfg, store, alice, bob):
    bot = await make_bot(cfg, alice, "Scout")
    routine = await store.create(alice, draft(bot.id))
    assert await store.get(bob, routine.id) is None
    assert await store.update(bob, routine.id, RoutinePatch({"name": "Mine now"})) is None
    assert await store.set_enabled(bob, routine.id, False) is None
    assert await store.delete(bob, routine.id) is False
    assert await store.list_for_bot(bob, bot.id) == ()
    assert await store.count_for_bot(bob, bot.id) == 0
    assert (await store.get(alice, routine.id)).name == "Morning news"


async def test_update_reseals_and_a_new_schedule_moves_the_next_run(cfg, store, clock, alice):
    bot = await make_bot(cfg, alice, "Scout")
    routine = await store.create(alice, draft(bot.id))
    evening = parse_schedule({"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["22:30"]})
    changed = await store.update(alice, routine.id, RoutinePatch(
        {"name": "Evening", "instructions": "Sum up.", "schedule": evening, "tainted": True}))
    assert (changed.name, changed.instructions, changed.schedule, changed.tainted) == ("Evening", "Sum up.", evening, True)
    slot = next_after(evening, NOW)
    assert changed.next_run_at == slot + timedelta(seconds=jitter_seconds(routine.id, slot))
    assert raw(cfg, "SELECT name FROM routines WHERE id = ?", (routine.id,))[0][0].startswith("enc:v2:")
    with pytest.raises(ValueError):
        await store.update(alice, routine.id, RoutinePatch({"enabled": False}))
    paused = await store.set_enabled(alice, routine.id, False)
    again = await store.update(alice, routine.id, RoutinePatch({"schedule": SCHEDULE}))
    assert paused.next_run_at is None and again.next_run_at is None   # a disabled routine stays unscheduled


async def test_lists_counts_and_builtin_lookup(cfg, store, alice):
    bot = await make_bot(cfg, alice, "Scout")
    other = await make_bot(cfg, alice, "Other")
    first = await store.create(alice, draft(bot.id, "A"))
    await store.create(alice, draft(bot.id, "B"))
    summary = await store.create(alice, draft(other.id, "Day", builtin="day_summary", enabled=False))
    assert [r.name for r in await store.list_for_bot(alice, bot.id)] == ["A", "B"]
    assert await store.count_for_bot(alice, bot.id) == 2
    assert await store.count_for_user(alice) == 3
    assert (await store.builtin_for(alice, other.id, "day_summary")).id == summary.id
    assert await store.builtin_for(alice, bot.id, "day_summary") is None
    assert first.id != summary.id


async def test_delete_removes_the_routine_and_its_thread(cfg, store, alice):
    bot = await make_bot(cfg, alice, "Scout")
    routine = await store.create(alice, draft(bot.id))
    assert await store.delete(alice, routine.id) is True
    assert await store.delete(alice, routine.id) is False
    assert await store.get(alice, routine.id) is None
    assert await TalkStore(cfg).get_thread(alice, routine.thread_id) is None


async def test_replan_after_a_zone_change_keeps_the_local_time(cfg, store, alice, bob):
    eight = parse_schedule({"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["08:00"]})
    bot, other = await make_bot(cfg, alice, "Scout"), await make_bot(cfg, bob, "Other")
    routine = await store.create(alice, RoutineDraft(bot_id=bot.id, name="Eight", instructions="Go.", schedule=eight,
                                                       created_by="user"))
    off = await store.create(alice, draft(bot.id, "Off", enabled=False))
    theirs = await store.create(bob, RoutineDraft(bot_id=other.id, name="Eight", instructions="Go.", schedule=eight,
                                                       created_by="user"))
    assert routine.next_run_at.astimezone(MADRID).hour == 8
    set_local_tz("America/New_York")
    assert await store.replan_all(alice) == 1
    slot = next_after(eight, NOW)
    assert slot == datetime(2026, 10, 21, 12, 0, tzinfo=UTC)          # 08:00 in New York (EDT)
    assert (await store.get(alice, routine.id)).next_run_at == slot + timedelta(seconds=jitter_seconds(routine.id, slot))
    assert (await store.get(alice, off.id)).next_run_at is None
    assert (await store.get(bob, theirs.id)).next_run_at == theirs.next_run_at   # scoped by user
