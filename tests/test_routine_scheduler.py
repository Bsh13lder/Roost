"""The routine scheduler on a fake clock: one fire per slot, missed runs collapsing, skips, holds and limits."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import roost.routines.scheduler as scheduler_module
import roost.talk.runner as runner_module
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.routines.launcher import RoutineLauncher
from roost.routines.models import RoutineDraft
from roost.routines.runs import RoutineRunStore
from roost.routines.scheduler import RoutineScheduler
from roost.routines.schedule import parse_schedule
from roost.routines.store import RoutineStore
from team_helpers import make_bot, make_rig, team_model, wait_idle

UTC = timezone.utc
NOW = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)            # 10:00 in Madrid
SCHEDULE = parse_schedule({"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["10:07", "15:07"]})
PASSWORD = "pw-123456"


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now = self.now + timedelta(**delta)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", PASSWORD)).id


@pytest.fixture
async def bot(cfg, user_id):
    return await make_bot(cfg, user_id, "Scout")


@pytest.fixture
def clock():
    return FakeClock(NOW)


class Rigged:
    def __init__(self, cfg, clock, launcher_cls=RoutineLauncher):
        self.rig = make_rig(cfg, team_model({}))
        self.routines = RoutineStore(cfg, self.rig.talk, clock=clock)
        self.runs = RoutineRunStore(cfg, clock=clock)
        self.launcher = launcher_cls(self.rig.talk, self.rig.runner, self.runs, self.rig.events)
        self.scheduler = RoutineScheduler(
            cfg, clock=clock, launcher=self.launcher, runs=self.runs, routines=self.routines,
            turns=self.rig.runner, bots=self.rig.bots)

    async def routine(self, user_id, bot, name="Morning news"):
        return await self.routines.create(user_id, RoutineDraft(
            bot_id=bot.id, name=name, instructions="Read the headlines.", schedule=SCHEDULE, created_by="user"))

    async def states(self, user_id, routine_id):
        return sorted((r.state, r.missed_count) for r in await self.runs.list_for_routine(user_id, routine_id))


@pytest.fixture
def rigged(cfg, clock):
    return Rigged(cfg, clock)


async def test_a_due_routine_queues_one_item(rigged, clock, user_id, bot):
    routine = await rigged.routine(user_id, bot)
    clock.advance(minutes=9)        # 10:09, the 10:07 slot is due

    await rigged.scheduler.tick()
    await wait_idle(rigged.rig.runner)

    runs = await rigged.runs.list_for_routine(user_id, routine.id)
    assert [r.state for r in runs] == ["queued"] and runs[0].work_item_id
    item = await rigged.rig.runner.queue.get(user_id, runs[0].work_item_id)
    assert item.origin == "routine Morning news"
    again = await rigged.routines.get(user_id, routine.id)
    assert again.next_run_at > clock.now and again.last_run_at == clock.now


async def test_a_routine_that_is_not_due_does_nothing(rigged, clock, user_id, bot):
    routine = await rigged.routine(user_id, bot)
    clock.advance(minutes=2)

    await rigged.scheduler.tick()

    assert await rigged.runs.list_for_routine(user_id, routine.id) == ()


async def test_two_ticks_at_once_fire_a_slot_once(rigged, clock, user_id, bot):
    routine = await rigged.routine(user_id, bot)
    clock.advance(minutes=9)

    await asyncio.gather(rigged.scheduler.tick(), rigged.scheduler.tick())
    await wait_idle(rigged.rig.runner)

    assert len(await rigged.runs.list_for_routine(user_id, routine.id)) == 1


async def test_sleeping_through_three_slots_gives_one_missed_row_and_one_run(rigged, clock, user_id, bot):
    routine = await rigged.routine(user_id, bot)
    clock.advance(days=2, hours=4)       # the Mac slept: six slots passed

    await rigged.scheduler.tick()
    await wait_idle(rigged.rig.runner)

    states = await rigged.states(user_id, routine.id)
    assert [s for s, _ in states].count("missed") == 1 and [s for s, _ in states].count("queued") == 1
    missed = next(r for r in await rigged.runs.list_for_routine(user_id, routine.id) if r.state == "missed")
    assert missed.missed_count >= 3 and "while Roost was off" in missed.note
    again = await rigged.routines.get(user_id, routine.id)
    assert again.next_run_at > clock.now
    await rigged.scheduler.tick()                      # nothing more is due: no pile-up
    assert len(await rigged.runs.list_for_routine(user_id, routine.id)) == 2


async def test_a_long_sleep_counts_only_the_lookback_window(rigged, clock, user_id, bot):
    routine = await rigged.routine(user_id, bot)
    clock.advance(days=90)

    await rigged.scheduler.tick()
    await wait_idle(rigged.rig.runner)

    runs = await rigged.runs.list_for_routine(user_id, routine.id)
    assert len(runs) == 2 and max(r.missed_count for r in runs) <= scheduler_module.ROUTINE_SLOT_SCAN_MAX


async def test_off_duty_records_skipped_and_queues_nothing(rigged, clock, cfg, user_id, bot):
    routine = await rigged.routine(user_id, bot)
    await BotStore(cfg).set_off_duty(user_id, bot.id, True)
    clock.advance(minutes=9)

    await rigged.scheduler.tick()

    runs = await rigged.runs.list_for_routine(user_id, routine.id)
    assert [(r.state, r.note, r.work_item_id) for r in runs] == [("skipped", "Off duty", None)]
    assert await rigged.rig.runner.queue.first_queued(user_id, bot.id) is None


async def test_a_slot_is_skipped_while_the_last_run_is_going(rigged, clock, user_id, bot):
    routine = await rigged.routine(user_id, bot)
    clock.advance(minutes=9)
    await rigged.scheduler.tick()
    await wait_idle(rigged.rig.runner)            # the queued row stays open: nothing finished it
    clock.advance(hours=5)                        # 15:09, the next slot

    await rigged.scheduler.tick()

    runs = await rigged.runs.list_for_routine(user_id, routine.id)
    assert sorted(r.state for r in runs) == ["queued", "skipped"]
    assert next(r for r in runs if r.state == "skipped").note == "the last run was still going"


async def test_held_at_the_daily_cap(rigged, clock, monkeypatch, user_id, bot):
    routine = await rigged.routine(user_id, bot)
    monkeypatch.setattr(runner_module, "DAILY_RUN_CAP", 1)
    await rigged.rig.runner._runs.start(user_id, bot.id, "thread", "run-1")
    clock.advance(minutes=9)

    await rigged.scheduler.tick()

    runs = await rigged.runs.list_for_routine(user_id, routine.id)
    assert [(r.state, r.work_item_id) for r in runs] == [("held", None)]


async def test_a_tick_fires_at_most_the_cap(rigged, clock, monkeypatch, user_id, bot):
    monkeypatch.setattr(scheduler_module, "ROUTINE_TICK_MAX_FIRES", 2)
    made = [await rigged.routine(user_id, bot, name=f"Routine {n}") for n in range(4)]
    clock.advance(minutes=9)

    async def count() -> int:
        return sum([len(await rigged.runs.list_for_routine(user_id, r.id)) for r in made])

    await rigged.scheduler.tick()
    assert await count() == 2
    await rigged.scheduler.tick()
    assert await count() == 4
    await wait_idle(rigged.rig.runner)


class _BrokenFirst(RoutineLauncher):
    async def launch(self, user_id, routine, slot_at, *, late, now):
        if routine.name == "Broken":
            raise RuntimeError("secret detail that must not be logged")
        return await super().launch(user_id, routine, slot_at, late=late, now=now)


async def test_one_broken_routine_never_stops_the_others(cfg, clock, caplog, user_id, bot):
    rigged = Rigged(cfg, clock, _BrokenFirst)
    broken = await rigged.routine(user_id, bot, name="Broken")
    fine = await rigged.routine(user_id, bot, name="Fine")
    clock.advance(minutes=9)

    with caplog.at_level(logging.WARNING):
        await rigged.scheduler.tick()
    await wait_idle(rigged.rig.runner)

    assert [r.state for r in await rigged.runs.list_for_routine(user_id, fine.id)] == ["queued"]
    assert [r.state for r in await rigged.runs.list_for_routine(user_id, broken.id)] == ["error"]
    assert "RuntimeError" in caplog.text and "secret detail" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


class _HangsOnce(RoutineLauncher):
    hung = False

    async def launch(self, user_id, routine, slot_at, *, late, now):
        if routine.name == "Slow" and not self.hung:
            type(self).hung = True
            await asyncio.sleep(30)
        return await super().launch(user_id, routine, slot_at, late=late, now=now)


async def test_a_slow_tick_is_cut_and_the_next_one_runs(cfg, clock, monkeypatch, user_id, bot):
    _HangsOnce.hung = False
    monkeypatch.setattr(scheduler_module, "SCHEDULER_TICK_TIMEOUT_SECONDS", 0.2)
    rigged = Rigged(cfg, clock, _HangsOnce)
    slow = await rigged.routine(user_id, bot, name="Slow")
    other = await rigged.routine(user_id, bot, name="Other")
    clock.advance(minutes=9)

    await asyncio.wait_for(rigged.scheduler.tick(), timeout=5)      # cut, not raised
    monkeypatch.setattr(scheduler_module, "SCHEDULER_TICK_TIMEOUT_SECONDS", 15)
    await asyncio.wait_for(rigged.scheduler.tick(), timeout=5)      # the next one runs
    await wait_idle(rigged.rig.runner)

    assert len(await rigged.runs.list_for_routine(user_id, other.id)) == 1


async def test_a_disabled_then_enabled_routine_replays_nothing(rigged, clock, user_id, bot):
    routine = await rigged.routine(user_id, bot)
    await rigged.routines.set_enabled(user_id, routine.id, False)
    clock.advance(days=3)
    await rigged.routines.set_enabled(user_id, routine.id, True)

    await rigged.scheduler.tick()

    assert await rigged.runs.list_for_routine(user_id, routine.id) == ()


def test_the_gateway_starts_and_stops_the_scheduler():
    app = create_app(load_config())
    with TestClient(app):
        task = app.state.scheduler_task
        assert task is not None and not task.done()
    assert task.done()
