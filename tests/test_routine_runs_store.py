"""RoutineRunStore: the run log, one row per slot and state, sealed notes, pruning, the hourly Report count."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from roost.config import load_config
from roost.constants import RUN_LOG_RETENTION_DAYS
from roost.db.connection import get_db_path, init_db
from roost.gateway.auth import register_user
from roost.routines.models import RoutineDraft
from roost.routines.runs import RoutineRunStore, SlotAlreadyRecorded, retention_cutoff
from roost.routines.schedule import parse_schedule
from roost.routines.store import RoutineStore
from roost.talk.store import TalkStore
from team_helpers import make_bot

UTC = timezone.utc
NOW = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)
SLOT = datetime(2026, 10, 21, 8, 7, tzinfo=UTC)
SCHEDULE = parse_schedule({"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["10:07"]})


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
async def rig(cfg, clock, alice):
    bot = await make_bot(cfg, alice, "Scout")
    routine = await RoutineStore(cfg, TalkStore(cfg), clock=clock).create(
        alice, RoutineDraft(bot_id=bot.id, name="News", instructions="Go.", schedule=SCHEDULE, created_by="user"))
    return RoutineRunStore(cfg, clock=clock), routine, bot


def raw(cfg, sql: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


async def test_record_a_queued_run_then_move_it_through_its_states(rig, alice, clock):
    runs, routine, bot = rig
    run = await runs.record(alice, routine, SLOT, "queued", work_item_id="w1")
    assert (run.state, run.slot_at, run.bot_id, run.routine_id, run.work_item_id) == ("queued", SLOT, bot.id, routine.id, "w1")
    assert run.started_at is None and run.finished_at is None and run.created_at == NOW
    clock.now = NOW + timedelta(minutes=1)
    running = await runs.set_state(alice, run.id, "running", expected={"queued"})
    assert running.started_at == clock.now and running.finished_at is None
    clock.now = NOW + timedelta(minutes=2)
    done = await runs.set_state(alice, run.id, "done", expected={"running"})
    assert done.finished_at == clock.now and done.started_at == running.started_at
    assert await runs.set_state(alice, run.id, "error", expected={"running"}) is None   # it already moved on
    assert (await runs.for_item(alice, "w1")).id == run.id
    assert await runs.for_item(alice, "other") is None


async def test_open_for_routine_sees_queued_and_running(rig, alice):
    runs, routine, _ = rig
    queued = await runs.record(alice, routine, SLOT, "queued")
    running = await runs.record(alice, routine, SLOT + timedelta(hours=5), "running")
    await runs.record(alice, routine, SLOT + timedelta(hours=10), "done")
    await runs.record(alice, routine, SLOT + timedelta(hours=15), "skipped")
    open_rows = await runs.open_for_routine(alice, routine.id)
    assert {r.id for r in open_rows} == {queued.id, running.id}
    assert next(r for r in open_rows if r.id == running.id).started_at is not None


async def test_a_slot_holds_a_missed_row_and_one_run_but_not_two(rig, alice):
    runs, routine, _ = rig
    missed = await runs.record(alice, routine, SLOT, "missed", missed_count=3, note="Missed 3 runs.")
    assert missed.missed_count == 3 and missed.finished_at is not None
    await runs.record(alice, routine, SLOT, "queued")
    with pytest.raises(SlotAlreadyRecorded):
        await runs.record(alice, routine, SLOT, "queued")
    assert len(await runs.list_for_routine(alice, routine.id)) == 2


async def test_a_run_note_is_sealed(cfg, rig, alice):
    runs, routine, _ = rig
    run = await runs.record(alice, routine, SLOT, "skipped", note="Stopped")
    stored = raw(cfg, "SELECT note FROM routine_runs WHERE id = ?", (run.id,))[0][0]
    assert stored.startswith("enc:v2:") and "Stopped" not in stored
    assert (await runs.list_for_routine(alice, routine.id))[0].note == "Stopped"
    changed = await runs.set_state(alice, run.id, "error", expected={"skipped"}, note="It broke")
    assert changed.note == "It broke"
    assert (await runs.record(alice, routine, SLOT + timedelta(days=1), "done")).note is None


async def test_runs_of_another_user_are_not_seen(rig, alice, bob):
    runs, routine, _ = rig
    run = await runs.record(alice, routine, SLOT, "queued", work_item_id="w9")
    assert await runs.list_for_routine(bob, routine.id) == ()
    assert await runs.open_for_routine(bob, routine.id) == ()
    assert await runs.for_item(bob, "w9") is None
    assert await runs.set_state(bob, run.id, "done") is None
    assert await runs.prune(bob, NOW + timedelta(days=1)) == 0
    assert len(await runs.list_for_routine(alice, routine.id)) == 1


async def test_list_for_routine_is_newest_first_with_a_page_limit(rig, alice, clock):
    runs, routine, _ = rig
    for i in range(4):
        clock.now = NOW + timedelta(hours=i)
        await runs.record(alice, routine, SLOT + timedelta(days=i), "done")
    got = await runs.list_for_routine(alice, routine.id, limit=3)
    assert [r.slot_at for r in got] == [SLOT + timedelta(days=i) for i in (3, 2, 1)]


async def test_old_runs_are_pruned(rig, alice, clock):
    runs, routine, _ = rig
    clock.now = NOW - timedelta(days=RUN_LOG_RETENTION_DAYS + 5)
    await runs.record(alice, routine, SLOT - timedelta(days=100), "done")
    clock.now = NOW
    keep = await runs.record(alice, routine, SLOT, "done")
    assert retention_cutoff(NOW) == NOW - timedelta(days=RUN_LOG_RETENTION_DAYS)
    assert await runs.prune(alice, retention_cutoff(NOW)) == 1
    assert [r.id for r in await runs.list_for_routine(alice, routine.id)] == [keep.id]


async def test_recent_reports_counts_only_this_bots_reports_since(cfg, rig, alice, bob, clock):
    runs, routine, bot = rig
    talk = TalkStore(cfg)
    other = await make_bot(cfg, alice, "Other")
    thread = await talk.create_thread(alice, bot.id, "chat")
    other_thread = await talk.create_thread(alice, other.id, "chat")
    await talk.add_message(alice, thread.id, "bot", "{}", kind="report", author_bot_id=bot.id)
    await talk.add_message(alice, thread.id, "bot", "{}", kind="report", author_bot_id=bot.id)
    await talk.add_message(alice, thread.id, "bot", "hello", author_bot_id=bot.id)             # not a report
    await talk.add_message(alice, other_thread.id, "bot", "{}", kind="report", author_bot_id=other.id)
    hour_ago = datetime(2000, 1, 1, tzinfo=UTC)   # the talk store stamps real time, so bound it loosely
    assert await runs.recent_reports(alice, bot.id, hour_ago) == 2
    assert await runs.recent_reports(alice, other.id, hour_ago) == 1
    assert await runs.recent_reports(bob, bot.id, hour_ago) == 0
    assert await runs.recent_reports(alice, bot.id, datetime(2100, 1, 1, tzinfo=UTC)) == 0
