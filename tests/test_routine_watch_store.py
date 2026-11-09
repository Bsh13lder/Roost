"""A routine's watch: parsed like open_page's addresses, sealed on the routine (schema v40), its snapshot sealed."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from roost.config import load_config
from roost.constants import WATCH_EVERY_MAX_MINUTES, WATCH_EVERY_MIN_MINUTES, WATCH_PART_MAX
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import MIGRATIONS
from roost.gateway.auth import register_user
from roost.routines.models import RoutineDraft, RoutinePatch
from roost.routines.schedule import parse_schedule
from roost.routines.store import RoutineStore
from roost.routines.watch_models import Watch, WatchRefused, next_check, parse_watch, watch_out
from roost.routines.watch_store import WatchStore
from roost.talk.store import TalkStore
from team_helpers import make_bot

UTC = timezone.utc
NOW = datetime(2026, 11, 4, 13, 0, tzinfo=UTC)
SCHEDULE = parse_schedule({"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["10:07"]})
URL = "https://web.whatsapp.com/"
WATCH = Watch(url=URL, part="the physio chat", every_min=5)


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


def _raw(cfg, sql: str, params=()) -> list[tuple]:
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


# --- parsing -------------------------------------------------------------------------------------------------


def test_parse_watch_keeps_a_safe_address_and_plain_words():
    watch = parse_watch({"url": " https://web.whatsapp.com ", "part": "  the physio chat ", "every_min": 10})
    assert watch == Watch(url="https://web.whatsapp.com", part="the physio chat", every_min=10)
    assert watch.host == "web.whatsapp.com"


def test_parse_watch_defaults_and_off():
    assert parse_watch(None) is None
    assert parse_watch({"off": True}) is None
    assert parse_watch({"url": URL}).every_min == WATCH_EVERY_MIN_MINUTES


@pytest.mark.parametrize("raw", [
    {"url": "http://127.0.0.1/"}, {"url": "file:///etc/passwd"}, {"url": "https://user:pw@x.com/"},
    {"url": "https://x.com:8443/"}, {"url": "not a url"}, {"url": ""},
])
def test_parse_watch_refuses_what_open_page_refuses(raw):
    with pytest.raises(WatchRefused):
        parse_watch(raw)


@pytest.mark.parametrize("every", [WATCH_EVERY_MIN_MINUTES - 1, 0, WATCH_EVERY_MAX_MINUTES + 1])
def test_parse_watch_refuses_a_check_too_often_or_too_rare(every):
    with pytest.raises(WatchRefused) as refused:
        parse_watch({"url": URL, "every_min": every})
    assert "minutes" in refused.value.text


def test_parse_watch_refuses_a_long_part_and_odd_keys():
    with pytest.raises(WatchRefused):
        parse_watch({"url": URL, "part": "x" * (WATCH_PART_MAX + 1)})
    with pytest.raises(WatchRefused):
        parse_watch({"url": URL, "script": "x"})


def test_next_check_and_out():
    assert next_check(WATCH, NOW) == NOW + timedelta(minutes=5)
    assert watch_out(WATCH) == {"url": URL, "part": "the physio chat", "every_min": 5, "host": "web.whatsapp.com"}
    assert watch_out(None) is None


# --- the routine's columns -------------------------------------------------------------------------------------


def test_migration_40_adds_the_watch_columns_and_table():
    watch = next(m for m in MIGRATIONS if m.version == 40)
    assert watch.name == "routine watch"


async def test_a_watch_is_sealed_on_the_routine_and_plans_its_first_check(cfg, alice, store):
    bot = await make_bot(cfg, alice, "Gela")
    routine = await store.create(alice, RoutineDraft(
        bot_id=bot.id, name="Watch physio chat", instructions="Tell me what Ana wrote.", schedule=SCHEDULE,
        created_by="user", watch=WATCH))
    assert routine.watch == WATCH
    assert routine.next_run_at == NOW + timedelta(minutes=5)
    url, part, every = _raw(cfg, "SELECT watch_url, watch_part, watch_every_min FROM routines WHERE id = ?",
                            (routine.id,))[0]
    assert url.startswith("enc:v2") and part.startswith("enc:v2") and every == 5
    assert "whatsapp" not in url and "physio" not in part


async def test_patching_the_watch_on_off_and_replanning(cfg, alice, store, clock):
    bot = await make_bot(cfg, alice, "Gela")
    routine = await store.create(alice, RoutineDraft(
        bot_id=bot.id, name="News", instructions="Read.", schedule=SCHEDULE, created_by="user"))
    assert routine.watch is None
    watched = await store.update(alice, routine.id, RoutinePatch({"watch": WATCH}))
    assert watched.watch == WATCH and watched.next_run_at == NOW + timedelta(minutes=5)
    clock.now = NOW + timedelta(hours=1)
    paused = await store.set_enabled(alice, routine.id, False)
    resumed = await store.set_enabled(alice, paused.id, True)
    assert resumed.next_run_at == clock.now + timedelta(minutes=5)
    plain = await store.update(alice, routine.id, RoutinePatch({"watch": None}))
    assert plain.watch is None and plain.next_run_at != clock.now + timedelta(minutes=5)


async def test_a_new_schedule_on_a_watching_routine_keeps_the_check_plan(cfg, alice, store):
    bot = await make_bot(cfg, alice, "Gela")
    routine = await store.create(alice, RoutineDraft(
        bot_id=bot.id, name="W", instructions="Read.", schedule=SCHEDULE, created_by="user", watch=WATCH))
    other = parse_schedule({"kind": "times", "days": [1], "times": ["08:00"]})
    changed = await store.update(alice, routine.id, RoutinePatch({"schedule": other}))
    assert changed.next_run_at == NOW + timedelta(minutes=5)


# --- the snapshot ----------------------------------------------------------------------------------------------


async def test_the_snapshot_is_sealed_scoped_and_reset(cfg, alice, bob, store, clock):
    bot = await make_bot(cfg, alice, "Gela")
    routine = await store.create(alice, RoutineDraft(
        bot_id=bot.id, name="W", instructions="Read.", schedule=SCHEDULE, created_by="user", watch=WATCH))
    snaps = WatchStore(cfg, clock=clock)
    assert await snaps.get(alice, routine.id) is None
    await snaps.save(alice, routine.id, snapshot="Ana: see you at 10", fingerprint="f1", changed=False)
    first = await snaps.get(alice, routine.id)
    assert first.snapshot == "Ana: see you at 10" and first.fingerprint == "f1" and first.changed_at is None
    assert first.checked_at == NOW and not first.blocked
    clock.now = NOW + timedelta(minutes=5)
    await snaps.save(alice, routine.id, snapshot="Ana: moved to 11", fingerprint="f2", changed=True,
                     change_text="Ana: moved to 11", change_run_id="run-1")
    second = await snaps.get(alice, routine.id)
    assert second.changed_at == clock.now and second.change_text == "Ana: moved to 11"
    assert second.change_run_id == "run-1"
    assert await snaps.get(bob, routine.id) is None
    sealed = _raw(cfg, "SELECT snapshot, change_text, fingerprint FROM routine_watches")[0]
    assert all(value.startswith("enc:v2") for value in sealed[:2]) and "moved" not in "".join(sealed)
    await snaps.set_blocked(alice, routine.id, True)
    assert (await snaps.get(alice, routine.id)).blocked
    await snaps.fold_quiet(alice, routine.id, "run-q", 3)
    folded = await snaps.get(alice, routine.id)
    assert folded.quiet_run_id == "run-q" and folded.quiet_count == 3
    await snaps.reset(bob, routine.id)
    assert await snaps.get(alice, routine.id) is not None
    await snaps.reset(alice, routine.id)
    assert await snaps.get(alice, routine.id) is None


async def test_the_snapshot_goes_with_its_routine(cfg, alice, store, clock):
    bot = await make_bot(cfg, alice, "Gela")
    routine = await store.create(alice, RoutineDraft(
        bot_id=bot.id, name="W", instructions="Read.", schedule=SCHEDULE, created_by="user", watch=WATCH))
    snaps = WatchStore(cfg, clock=clock)
    await snaps.set_blocked(alice, routine.id, True)
    await store.delete(alice, routine.id)
    assert _raw(cfg, "SELECT COUNT(*) FROM routine_watches")[0][0] == 0
