"""A routine ends when its job is done (owner, 2026-11-11, docs/plans/2026-11-11-roost-routine-finish.md): in its
own run the bot calls ``finish_routine`` for the routine that started the run, even when tainted; the routine is
paused and marked finished, one chat line offers Resume and Delete now, and the scheduler deletes it after
``ROUTINE_FINISHED_KEEP_DAYS``."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

import httpx
import pytest

from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import ROUTINE_FINISHED_KEEP_DAYS, ROUTINE_FINISHED_REASON_MAX
from roost.db.connection import init_db
from roost.events.hub import EventHub
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.routines.finish import FINISHED_KIND, NOT_ROUTINE_RUN_TEXT, RoutineFinish
from roost.routines.models import RoutineDraft
from roost.routines.runs import RoutineRunStore
from roost.routines.schedule import parse_schedule
from roost.routines.service import RoutineService
from roost.routines.store import RoutineStore
from roost.routines.tool_specs import FINISH_ROUTINE
from roost.routines.watch_models import Watch
from roost.talk.domain_tools import RecordContext
from roost.talk.store import TalkStore
from roost.talk.tool_catalog import CATALOG
from roost.talk.tool_groups import ROUTINE_RUN_GROUP, TOOL_GROUPS
from team_helpers import make_bot, wait_idle

NOW = datetime(2026, 11, 11, 8, 0, tzinfo=timezone.utc)
DAILY = {"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["09:00"]}
ORIGIN = {"Origin": "http://127.0.0.1:18800"}
PASSWORD = "pw-123456"


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class FakeWatches:
    """Only what the service needs: ``reset`` is recorded, ``get`` finds nothing."""

    def __init__(self) -> None:
        self.resets: list[str] = []

    async def reset(self, user_id: str, routine_id: str) -> None:
        self.resets.append(routine_id)

    async def get(self, user_id: str, routine_id: str):
        return None


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
    return await make_bot(cfg, user_id, "Gela")


@pytest.fixture
def clock():
    return FakeClock(NOW)


class Rig:
    def __init__(self, cfg, clock):
        self.talk, self.events, self.bots = TalkStore(cfg), EventHub(cfg), BotStore(cfg)
        self.routines = RoutineStore(cfg, self.talk, clock=clock)
        self.watches = FakeWatches()
        self.service = RoutineService(self.routines, RoutineRunStore(cfg), self.bots, self.talk, self.events,
                                      None, None, clock=clock, watches=self.watches)
        self.tool = RoutineFinish(self.routines, self.service)

    async def routine(self, user_id, bot, name="Watch physio's WhatsApp reply", watch=None):
        return await self.routines.create(user_id, RoutineDraft(
            bot_id=bot.id, name=name, instructions="Tell me when the physio answers.", schedule=parse_schedule(DAILY),
            created_by="user", watch=watch))

    async def finish(self, user_id, bot, thread_id, reason="The appointment is booked", *, tainted=False,
                     from_routine=True):
        ctx = RecordContext(user_id=user_id, bot_id=bot.id, tainted=tainted, thread_id=thread_id,
                            from_routine=from_routine)
        return await self.tool.run(FINISH_ROUTINE, {"reason": reason}, ctx)

    async def lines(self, user_id, bot):
        thread, _ = await self.talk.ensure_main_thread(user_id, bot.id)
        return [m for m in await self.talk.list_messages(user_id, thread.id) if m.kind == FINISHED_KIND]


@pytest.fixture
def rig(cfg, clock):
    return Rig(cfg, clock)


# ---- the catalog, the gate and the groups -------------------------------------------------------------------

def test_finish_routine_only_reduces_what_runs_so_it_is_allowed_when_tainted_with_no_card():
    tool = CATALOG[FINISH_ROUTINE]
    assert tool.kind == "write_change" and tool.allowed_when_tainted and tool.no_ask
    assert FINISH_ROUTINE in TOOL_GROUPS[ROUTINE_RUN_GROUP].names


def test_a_routine_run_starts_with_the_finish_tool_loaded(monkeypatch):
    from roost.talk.run_groups import start_groups
    from roost.work.models import WorkItem, WorkKind

    def item(kind):
        return WorkItem(id="i", user_id="u", bot_id="b", thread_id="t", kind=kind, origin="user", body="Check",
                        tainted=False, depth=0, parent_item_id=None, message_id=None, state="claimed", run_id=None,
                        inflight=None, result=None, result_tainted=False, created_at="", updated_at="")

    monkeypatch.delenv("ROOST_TOOL_GROUPS", raising=False)
    assert ROUTINE_RUN_GROUP in start_groups((item(WorkKind.ROUTINE),), (), stuck_reply=False)
    assert ROUTINE_RUN_GROUP not in start_groups((item(WorkKind.MESSAGE),), (), stuck_reply=False)


# ---- the tool ----------------------------------------------------------------------------------------------

async def test_in_its_own_run_the_bot_finishes_the_routine_and_the_chat_says_so(rig, user_id, bot):
    routine = await rig.routine(user_id, bot)
    outcome = await rig.finish(user_id, bot, routine.thread_id)
    assert not outcome.failed and "Finished" in outcome.text
    after = await rig.routines.get(user_id, routine.id)
    assert after.enabled is False and after.next_run_at is None
    assert after.finished_at == NOW and after.finished_reason == "The appointment is booked"
    (line,) = await rig.lines(user_id, bot)
    body = json.loads(line.body)
    assert body["routine_id"] == routine.id and body["name"] == routine.name
    assert body["reason"] == "The appointment is booked"
    assert body["delete_at"].startswith((NOW + timedelta(days=ROUTINE_FINISHED_KEEP_DAYS)).strftime("%Y-%m-%d"))
    assert "Finished routine · Watch physio's WhatsApp reply: The appointment is booked." in body["text"]
    assert f"{ROUTINE_FINISHED_KEEP_DAYS} days" in body["text"]
    assert line.tainted is False


async def test_a_tainted_change_run_may_finish_and_its_line_wears_the_mark(rig, user_id, bot):
    routine = await rig.routine(user_id, bot)
    outcome = await rig.finish(user_id, bot, routine.thread_id, tainted=True)
    assert not outcome.failed
    (line,) = await rig.lines(user_id, bot)
    assert line.tainted is True


async def test_outside_a_routine_run_it_refuses_and_points_to_the_direct_tools(rig, user_id, bot):
    routine = await rig.routine(user_id, bot)
    thread, _ = await rig.talk.ensure_main_thread(user_id, bot.id)
    outcome = await rig.finish(user_id, bot, thread.id, from_routine=False)
    assert outcome.failed and outcome.text == NOT_ROUTINE_RUN_TEXT
    assert "pause_routine" in outcome.text and "delete_routine" in outcome.text
    assert (await rig.routines.get(user_id, routine.id)).enabled is True


async def test_a_routine_run_can_finish_only_the_routine_that_started_it(rig, cfg, user_id, bot):
    other_bot = await make_bot(cfg, user_id, "Scout")
    theirs = await rig.routine(user_id, other_bot, name="Scout's watch")
    outcome = await rig.finish(user_id, bot, theirs.thread_id)       # another bot's routine thread
    assert outcome.failed and outcome.text == NOT_ROUTINE_RUN_TEXT
    thread, _ = await rig.talk.ensure_main_thread(user_id, bot.id)
    outcome = await rig.finish(user_id, bot, thread.id)               # from_routine, but not a routine's thread
    assert outcome.failed and outcome.text == NOT_ROUTINE_RUN_TEXT
    assert (await rig.routines.get(user_id, theirs.id)).enabled is True


async def test_the_reason_is_one_line_and_capped(rig, user_id, bot):
    routine = await rig.routine(user_id, bot)
    long = "x" * (ROUTINE_FINISHED_REASON_MAX + 50)
    outcome = await rig.finish(user_id, bot, routine.thread_id, reason=long)
    assert outcome.failed       # the argument itself is capped by the tool's schema
    outcome = await rig.finish(user_id, bot, routine.thread_id, reason="booked\n\nfor Monday")
    assert not outcome.failed
    assert (await rig.routines.get(user_id, routine.id)).finished_reason == "booked for Monday"


# ---- resume, delete now and the sweep -----------------------------------------------------------------------

async def test_resume_clears_finished_plans_the_next_run_and_resets_a_watch(rig, user_id, bot):
    watch = Watch(url="https://web.whatsapp.com/", part="the physio chat", every_min=5)
    routine = await rig.routine(user_id, bot, watch=watch)
    await rig.finish(user_id, bot, routine.thread_id)
    resumed = await rig.service.resume_finished(user_id, routine.id)
    assert resumed.enabled is True and resumed.finished_at is None and resumed.finished_reason is None
    assert resumed.next_run_at is not None
    assert rig.watches.resets == [routine.id]


async def test_the_sweep_deletes_a_routine_still_finished_after_the_keep_days(rig, clock, user_id, bot):
    routine = await rig.routine(user_id, bot)
    kept = await rig.routine(user_id, bot, name="Morning news")
    await rig.finish(user_id, bot, routine.thread_id)
    clock.now = NOW + timedelta(days=ROUTINE_FINISHED_KEEP_DAYS) - timedelta(hours=1)
    assert await rig.service.sweep_finished(user_id, clock.now) == 0
    assert await rig.routines.get(user_id, routine.id) is not None
    clock.now = NOW + timedelta(days=ROUTINE_FINISHED_KEEP_DAYS)
    assert await rig.service.sweep_finished(user_id, clock.now) == 1
    assert await rig.routines.get(user_id, routine.id) is None
    assert await rig.routines.get(user_id, kept.id) is not None


async def test_a_resumed_routine_is_not_swept(rig, clock, user_id, bot):
    routine = await rig.routine(user_id, bot)
    await rig.finish(user_id, bot, routine.thread_id)
    await rig.service.resume_finished(user_id, routine.id)
    clock.now = NOW + timedelta(days=ROUTINE_FINISHED_KEEP_DAYS + 1)
    assert await rig.service.sweep_finished(user_id, clock.now) == 0
    assert await rig.routines.get(user_id, routine.id) is not None


async def test_the_scheduler_tick_runs_the_sweep(cfg, clock, user_id, bot):
    from roost.routines.launcher import RoutineLauncher
    from roost.routines.scheduler import RoutineScheduler
    from team_helpers import make_rig, team_model

    rig = make_rig(cfg, team_model({}))
    runs = RoutineRunStore(cfg, clock=clock)
    swept: list[tuple[str, datetime]] = []

    async def sweep(uid: str, now: datetime) -> int:
        swept.append((uid, now))
        return 0

    scheduler = RoutineScheduler(
        cfg, clock=clock, launcher=RoutineLauncher(rig.talk, rig.runner, runs, rig.events), runs=runs,
        routines=RoutineStore(cfg, rig.talk, clock=clock), turns=rig.runner, bots=rig.bots, finished=sweep)
    await scheduler.tick()
    await wait_idle(rig.runner, timeout=5)
    assert swept == [(user_id, NOW)]


# ---- the routes ----------------------------------------------------------------------------------------------

@asynccontextmanager
async def signed_in(app, username: str) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        assert (await client.post("/api/auth/login", json={"username": username, "password": PASSWORD},
                                  headers=ORIGIN)).status_code == 200
        try:
            yield client
        finally:
            await wait_idle(app.state.turns, timeout=8)


async def test_the_routes_show_finished_resume_and_delete_now(cfg, user_id, bot):
    app = create_app(cfg)
    store = RoutineStore(cfg, TalkStore(cfg), clock=lambda: NOW)
    routine = await store.create(user_id, RoutineDraft(
        bot_id=bot.id, name="Watch", instructions="Watch.", schedule=parse_schedule(DAILY), created_by="user"))
    await app.state.routines.finish(user_id, routine.id, "Booked")
    await register_user(cfg, "bob", PASSWORD)
    async with signed_in(app, "alice") as client:
        listed = (await client.get(f"/api/bots/{bot.id}/routines")).json()["routines"]
        assert listed[0]["enabled"] is False
        assert listed[0]["finished"]["reason"] == "Booked" and listed[0]["finished"]["delete_at"]
        resumed = await client.post(f"/api/routines/{routine.id}/resume", headers=ORIGIN)
        assert resumed.status_code == 200
        assert resumed.json()["enabled"] is True and resumed.json()["finished"] is None
        assert (await client.delete(f"/api/routines/{routine.id}", headers=ORIGIN)).status_code == 204
        assert (await client.post(f"/api/routines/{routine.id}/resume", headers=ORIGIN)).status_code == 404
    async with signed_in(app, "bob") as client:
        other = await store.create(user_id, RoutineDraft(
            bot_id=bot.id, name="Alice's", instructions="Hers.", schedule=parse_schedule(DAILY), created_by="user"))
        assert (await client.post(f"/api/routines/{other.id}/resume", headers=ORIGIN)).status_code == 404
