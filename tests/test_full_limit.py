"""Use the full limit: per bot, until the reset, routines included, never into the last 10%."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import roost.talk.runner as runner_module
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import DeskFactory
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.routines.hooks import RoutineHooks
from roost.routines.launcher import RoutineLauncher
from roost.routines.models import RoutineDraft
from roost.routines.runs import RoutineRunStore
from roost.routines.schedule import parse_schedule
from roost.routines.scheduler import RoutineScheduler
from roost.routines.store import RoutineStore
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from roost.talk.tool_catalog import CATALOG
from roost.usage.reading import FULL_LIMIT_REFUSAL, UsageReading
from roost.work.models import WorkDraft, WorkKind, WorkState
from money_http import O, two_users
from team_helpers import make_bot, send, team_model, wait_idle

UTC = timezone.utc
NOW = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)               # 10:00 in Madrid
SCHEDULE = parse_schedule({"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["10:07", "15:07"]})


class FakeUsage:
    def __init__(self, reading: UsageReading | None) -> None:
        self.reading = reading

    async def read(self) -> UsageReading | None:
        return self.reading


class Clock:
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
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture
async def bot(cfg, user_id):
    return await make_bot(cfg, user_id, "Scout")


class Rig:
    def __init__(self, cfg, reading, clock):
        self.usage, self.clock = FakeUsage(reading), clock
        self.bots, self.talk, self.events = BotStore(cfg), TalkStore(cfg), EventHub(cfg)
        self.hooks = RoutineHooks(self.talk, self.events, RoutineRunStore(cfg, clock=clock),
                                  RoutineStore(cfg, self.talk, clock=clock), clock=clock)
        self.runner = TurnRunner(cfg, self.bots, self.talk, self.events, DeskFactory(cfg), team_model({}),
                                 ActivityBoard(), usage=self.usage, clock=clock, routines=self.hooks)
        self.runs = RoutineRunStore(cfg, clock=clock)
        self.routines = RoutineStore(cfg, self.talk, clock=clock)
        launcher = RoutineLauncher(self.talk, self.runner, self.runs, self.events)
        self.scheduler = RoutineScheduler(cfg, clock=clock, launcher=launcher, runs=self.runs,
                                          routines=self.routines, turns=self.runner, bots=self.bots,
                                          hooks=self.hooks)

    async def full_limit(self, user_id, bot, hours=4):
        await self.bots.set_full_limit(user_id, bot.id, self.clock.now + timedelta(hours=hours))

    async def message(self, user_id, bot, text):
        thread = await self.talk.ensure_main_thread(user_id, bot.id)
        await send(self, user_id, bot.id, thread[0].id, text)
        await wait_idle(self.runner)

    async def routine(self, user_id, bot):
        return await self.routines.create(user_id, RoutineDraft(
            bot_id=bot.id, name="Morning news", instructions="Read.", schedule=SCHEDULE, created_by="user"))

    async def paused_reports(self, user_id, bot):
        thread = await self.talk.main_thread(user_id, bot.id)
        found = await self.talk.list_messages(user_id, thread.id, limit=100) if thread else []
        return [json.loads(m.body)["text"] for m in found if m.kind == "report"]


@pytest.fixture
def clock():
    return Clock(NOW)


# --- the switch -------------------------------------------------------------------------------------------------


async def test_without_a_reading_the_switch_is_refused():
    async with two_users() as (alice, _bob, app):
        bot = (await alice.post("/api/bots", json={"name": "Scout", "job": "x", "avatar": {
            "shape": "round", "color": "#22c55e", "badge": "none"}}, headers=O)).json()
        reading = (await alice.get("/api/usage")).json()   # it also carries the token usage (2026-11-04)
        assert {k: reading[k] for k in ("readable", "remaining_fraction", "resets_at")} == {
            "readable": False, "remaining_fraction": None, "resets_at": None}
        r = await alice.put(f"/api/bots/{bot['id']}/full-limit", json={"on": True}, headers=O)
        assert r.status_code == 422 and FULL_LIMIT_REFUSAL in r.text
        assert (await alice.put(f"/api/bots/{bot['id']}/full-limit", json={"on": False}, headers=O)
                ).json()["full_limit_until"] is None


async def test_with_a_reading_it_lasts_until_the_reset_or_madrid_midnight():
    async with two_users() as (alice, _bob, app):
        bot = (await alice.post("/api/bots", json={"name": "Scout", "job": "x", "avatar": {
            "shape": "round", "color": "#22c55e", "badge": "none"}}, headers=O)).json()
        reset = datetime.now(UTC) + timedelta(hours=3)
        app.state.usage = FakeUsage(UsageReading(0.6, reset))
        on = (await alice.put(f"/api/bots/{bot['id']}/full-limit", json={"on": True}, headers=O)).json()
        assert datetime.fromisoformat(on["full_limit_until"]) == reset
        assert (await alice.get("/api/usage")).json()["readable"] is True

        app.state.usage = FakeUsage(UsageReading(0.6, None))
        later = (await alice.put(f"/api/bots/{bot['id']}/full-limit", json={"on": True}, headers=O)).json()
        assert datetime.fromisoformat(later["full_limit_until"]) > datetime.now(UTC)
        off = (await alice.put(f"/api/bots/{bot['id']}/full-limit", json={"on": False}, headers=O)).json()
        assert off["full_limit_until"] is None


async def test_another_users_bot_is_404():
    async with two_users() as (alice, bob, app):
        bot = (await alice.post("/api/bots", json={"name": "Scout", "job": "x", "avatar": {
            "shape": "round", "color": "#22c55e", "badge": "none"}}, headers=O)).json()
        app.state.usage = FakeUsage(UsageReading(0.6, None))
        r = await bob.put(f"/api/bots/{bot['id']}/full-limit", json={"on": True}, headers=O)
        assert r.status_code == 404
        assert (await bob.put(f"/api/bots/{bot['id']}/full-limit", json={"on": True})).status_code in (401, 403)


def test_no_tool_can_turn_on_the_full_limit():
    assert not any("full_limit" in json.dumps(tool.spec.__dict__, default=str) for tool in CATALOG.values())
    from pathlib import Path
    root = Path(runner_module.__file__).resolve().parents[1]
    callers = {p.relative_to(root).as_posix() for p in root.rglob("*.py") if "set_full_limit(" in p.read_text()}
    assert callers == {"bots/store.py", "gateway/routes/usage.py"}


# --- the runner -------------------------------------------------------------------------------------------------


async def test_full_limit_lets_a_bot_run_past_its_daily_cap(cfg, clock, monkeypatch, user_id, bot):
    monkeypatch.setattr(runner_module, "DAILY_RUN_CAP", 1)
    rig = Rig(cfg, UsageReading(0.6, None), clock)
    await rig.message(user_id, bot, "one")
    await rig.message(user_id, bot, "two")
    assert await rig.runner.runs_today(user_id, bot.id) == 1           # capped without the full limit

    await rig.full_limit(user_id, bot)
    await rig.runner.kick(user_id, bot.id)
    await wait_idle(rig.runner)
    assert await rig.runner.runs_today(user_id, bot.id) == 2


async def test_full_limit_ends_at_the_reset(cfg, clock, monkeypatch, user_id, bot):
    monkeypatch.setattr(runner_module, "DAILY_RUN_CAP", 1)
    rig = Rig(cfg, UsageReading(0.6, None), clock)
    await rig.message(user_id, bot, "one")
    await rig.full_limit(user_id, bot, hours=1)
    await rig.message(user_id, bot, "two")
    assert await rig.runner.runs_today(user_id, bot.id) == 2

    clock.now = NOW + timedelta(hours=2)                                # past the end
    await rig.message(user_id, bot, "three")
    assert await rig.runner.runs_today(user_id, bot.id) == 2


async def test_your_messages_still_run_inside_the_reserve(cfg, clock, user_id, bot):
    rig = Rig(cfg, UsageReading(0.05, None), clock)
    await rig.full_limit(user_id, bot)
    await rig.message(user_id, bot, "hello")
    assert await rig.runner.runs_today(user_id, bot.id) == 1


async def test_the_reserve_keeps_the_cap_even_with_the_full_limit_on(cfg, clock, monkeypatch, user_id, bot):
    monkeypatch.setattr(runner_module, "DAILY_RUN_CAP", 1)
    rig = Rig(cfg, UsageReading(0.05, None), clock)
    await rig.full_limit(user_id, bot)
    await rig.message(user_id, bot, "one")
    await rig.message(user_id, bot, "two")
    assert await rig.runner.runs_today(user_id, bot.id) == 1


# --- the scheduler ----------------------------------------------------------------------------------------------


async def test_routines_never_start_inside_the_reserve(cfg, clock, user_id, bot):
    rig = Rig(cfg, UsageReading(0.05, NOW + timedelta(hours=5)), clock)
    routine = await rig.routine(user_id, bot)
    clock.now = NOW + timedelta(minutes=9)

    await rig.scheduler.tick()
    await wait_idle(rig.runner)

    runs = await rig.runs.list_for_routine(user_id, routine.id)
    assert [(r.state, r.work_item_id) for r in runs] == [("held", None)]
    assert await rig.runner.runs_today(user_id, bot.id) == 0


async def test_a_queued_routine_item_is_not_claimed_inside_the_reserve(cfg, clock, user_id, bot):
    rig = Rig(cfg, UsageReading(0.6, None), clock)
    routine = await rig.routine(user_id, bot)
    clock.now = NOW + timedelta(minutes=9)
    await rig.scheduler.tick()                                          # queued while there is room
    await wait_idle(rig.runner)
    (run,) = await rig.runs.list_for_routine(user_id, routine.id)
    rig.usage.reading = UsageReading(0.05, None)                        # then the reserve begins
    item = await rig.runner.submit(user_id, WorkDraft(
        bot_id=bot.id, thread_id=routine.thread_id, kind=WorkKind.ROUTINE, origin="routine Morning news",
        body="again"))
    await wait_idle(rig.runner)
    await rig.message(user_id, bot, "you first")

    assert (await rig.runner.queue.get(user_id, item.id)).state is WorkState.QUEUED
    assert run.work_item_id is not None


async def test_the_paused_report_is_posted_once_per_reset_window(cfg, clock, user_id, bot):
    reset = NOW + timedelta(hours=9)                                    # 20:00 Madrid
    rig = Rig(cfg, UsageReading(0.05, reset), clock)
    await rig.routine(user_id, bot)
    clock.now = NOW + timedelta(minutes=9)
    await rig.scheduler.tick()
    clock.now = NOW + timedelta(hours=5, minutes=10)                    # the 15:07 slot, still the same window
    rig.usage.reading = UsageReading(0.05, reset)
    await rig.scheduler.tick()

    texts = await rig.paused_reports(user_id, bot)
    assert len(texts) == 1 and texts[0].startswith("Held: Morning news\n\nPaused my routines: the usage limit is nearly used up")
    assert "Madrid" in texts[0]

    rig.usage.reading = UsageReading(0.05, reset + timedelta(days=1))   # a new reset window
    clock.now = NOW + timedelta(days=1, minutes=9)
    await rig.scheduler.tick()
    assert len(await rig.paused_reports(user_id, bot)) == 2
