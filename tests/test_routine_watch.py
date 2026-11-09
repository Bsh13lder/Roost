"""The page watch on a fake Linux computer: Roost reads the page itself (no model) and runs the routine only when
the watched part changed (owner, 2026-11-04)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from roost.bots.models import BotPatch
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import DeskFactory, PageText
from roost.desk.fake_chats import CHAT_LIST, CHATS_URL, FAKE_CHATS, MESSAGES
from roost.desk.fake_cu import fake_area
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.routines.hooks import RoutineHooks
from roost.routines.launcher import RoutineLauncher
from roost.routines.models import RoutineDraft
from roost.routines.runs import RoutineRunStore
from roost.routines.schedule import parse_schedule
from roost.routines.store import RoutineStore
from roost.routines.watch import WatchChecker
from roost.routines.watch_models import Watch
from roost.routines.watch_store import WatchStore
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from roost.work.models import WorkKind
from team_helpers import make_bot, send, team_model, wait_idle

UTC = timezone.utc
NOW = datetime(2026, 11, 4, 13, 50, tzinfo=UTC)       # 14:50 in Madrid
SCHEDULE = parse_schedule({"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["10:07"]})
NEW_LINE = "Francis: Can we move it to 11:00? The clinic called."


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


async def _no_sleep(_seconds: float) -> None:
    return None


class Rig:
    """A runner with routine hooks and the watch, over the fake desks."""

    def __init__(self, cfg, clock: FakeClock) -> None:
        self.bots, self.talk, self.events, self.desks = BotStore(cfg), TalkStore(cfg), EventHub(cfg), DeskFactory(cfg)
        self.model = team_model({})
        self.routines = RoutineStore(cfg, self.talk, clock=clock)
        self.runs = RoutineRunStore(cfg, clock=clock)
        self.snaps = WatchStore(cfg, clock=clock)
        self.hooks = RoutineHooks(self.talk, self.events, self.runs, self.routines, clock=clock, watches=self.snaps)
        self.runner = TurnRunner(cfg, self.bots, self.talk, self.events, self.desks, self.model, ActivityBoard(),
                                 routines=self.hooks, clock=clock)
        self.hooks.attach(self.runner, None, self.bots)
        launcher = RoutineLauncher(self.talk, self.runner, self.runs, self.events)
        self.checker = WatchChecker(
            config=cfg, bots=self.bots, routines=self.routines, runs=self.runs, snapshots=self.snaps, launcher=launcher, turns=self.runner,
            desks=self.desks, hooks=self.hooks, clock=clock, sleep=_no_sleep, ready_timeout_s=0)
        self.runner.set_watch(self.checker)

    async def check(self, user_id: str, routine) -> None:
        assert await self.checker.queue_check(user_id, routine)
        await wait_idle(self.runner)

    async def notes(self, user_id: str, routine_id: str) -> list[tuple[str, str | None]]:
        return [(r.state, r.note) for r in await self.runs.list_for_routine(user_id, routine_id)]


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture
def clock():
    return FakeClock(NOW)


@pytest.fixture
def rig(cfg, clock):
    return Rig(cfg, clock)


async def _linux_bot(cfg, user_id, name="Gela"):
    bot = await make_bot(cfg, user_id, name)
    return await BotStore(cfg).update(user_id, bot.id, BotPatch(computer="linux"))


async def _watching(rig: Rig, user_id: str, bot, part="Francis Dentist"):
    return await rig.routines.create(user_id, RoutineDraft(
        bot_id=bot.id, name="Watch physio chat", instructions="Tell me what Francis wrote.", schedule=SCHEDULE,
        created_by="user", watch=Watch(url=CHATS_URL, part=part, every_min=5)))


def _chat_screen(extra: str = ""):
    """The fake WhatsApp with the Francis chat open; ``extra`` is a newer message at the end of its pane."""
    messages = fake_area("application", "Messages", MESSAGES.text + (f"\n{extra}" if extra else ""), 400, 60, 880, 560)
    chat = replace(FAKE_CHATS["chat"], areas=(CHAT_LIST, messages))
    return {"chat": chat}


async def test_the_first_check_records_a_baseline_with_no_model_run(cfg, user_id, rig):
    bot = await _linux_bot(cfg, user_id)
    routine = await _watching(rig, user_id, bot)
    desk = rig.desks.for_bot(bot.id, "linux")
    desk.serve_screen(_chat_screen())

    await rig.check(user_id, routine)

    assert rig.model.requests == []
    assert desk.open_page_calls == [CHATS_URL]
    snap = await rig.snaps.get(user_id, routine.id)
    assert snap.fingerprint and "You: thanks, noted 199." in snap.snapshot
    assert await rig.notes(user_id, routine.id) == [("done", "Started watching: saved the page to compare with")]


async def test_no_change_is_one_quiet_line_that_counts_its_checks(cfg, user_id, rig, clock):
    bot = await _linux_bot(cfg, user_id)
    routine = await _watching(rig, user_id, bot)
    rig.desks.for_bot(bot.id, "linux").serve_screen(_chat_screen())
    for _ in range(4):
        await rig.check(user_id, routine)
        clock.now += timedelta(minutes=5)

    assert rig.model.requests == []
    notes = await rig.notes(user_id, routine.id)
    assert notes[0] == ("done", "No change · checked 3 times")
    assert len(notes) == 2
    main = await rig.talk.main_thread(user_id, bot.id)
    assert main is None or not [m for m in await rig.talk.list_messages(user_id, main.id) if m.kind == "report"]


async def test_a_change_runs_the_routine_once_with_the_new_text_as_page_content(cfg, user_id, rig, clock):
    bot = await _linux_bot(cfg, user_id)
    routine = await _watching(rig, user_id, bot)
    desk = rig.desks.for_bot(bot.id, "linux")
    desk.serve_screen(_chat_screen())
    await rig.check(user_id, routine)
    clock.now += timedelta(minutes=5)
    desk.serve_screen(_chat_screen(NEW_LINE))

    await rig.check(user_id, routine)

    assert len(rig.model.requests) >= 1
    system = rig.model.requests[0].system
    assert "<untrusted_page" in system and "Can we move it to 11:00?" in system
    assert "You: thanks, noted 199." not in system          # only what is new, not the whole pane
    snap = await rig.snaps.get(user_id, routine.id)
    assert snap.changed_at == clock.now and NEW_LINE in snap.snapshot
    runs = await rig.runs.list_for_routine(user_id, routine.id)
    assert runs[0].id == snap.change_run_id and runs[0].note == "The page changed"
    item = await rig.runner.queue.get(user_id, runs[0].work_item_id)
    assert item.kind is WorkKind.ROUTINE and CHATS_URL in item.link_scope


async def test_a_change_run_is_tainted_as_page_content(cfg, user_id, rig, clock):
    bot = await _linux_bot(cfg, user_id)
    routine = await _watching(rig, user_id, bot)
    desk = rig.desks.for_bot(bot.id, "linux")
    desk.serve_screen(_chat_screen())
    await rig.check(user_id, routine)
    desk.serve_screen(_chat_screen(NEW_LINE))
    await rig.check(user_id, routine)
    section = await rig.hooks.prompt_section(user_id, (await _routine_item(rig, user_id, routine),))
    assert section.tainted and "What is new" in section.text


async def _routine_item(rig, user_id, routine):
    run = (await rig.runs.list_for_routine(user_id, routine.id))[0]
    return await rig.runner.queue.get(user_id, run.work_item_id)


async def test_a_sign_in_page_runs_the_routine_once_and_then_stays_quiet(cfg, user_id, rig, clock):
    bot = await _linux_bot(cfg, user_id)
    routine = await _watching(rig, user_id, bot)
    desk = rig.desks.for_bot(bot.id, "linux")
    desk.serve(CHATS_URL, PageText(url=CHATS_URL, title="WhatsApp", text="Log in to WhatsApp Web", truncated=False,
                                   password_field=True))
    await rig.check(user_id, routine)
    first = await rig.notes(user_id, routine.id)
    assert first[0][1] == "The page needs a sign-in, so the routine ran as usual once"
    asked = len(rig.model.requests)
    assert asked >= 1
    clock.now += timedelta(minutes=5)
    await rig.check(user_id, routine)
    assert len(rig.model.requests) == asked and len(await rig.notes(user_id, routine.id)) == len(first)
    assert (await rig.snaps.get(user_id, routine.id)).blocked


async def test_no_free_computer_skips_the_check_quietly(cfg, user_id, rig):
    bot = await _linux_bot(cfg, user_id)
    routine = await _watching(rig, user_id, bot)
    desk = rig.desks.for_bot(bot.id, "linux")
    desk.force_busy = True
    await rig.check(user_id, routine)
    assert desk.open_page_calls == [] and await rig.notes(user_id, routine.id) == []
    assert await rig.snaps.get(user_id, routine.id) is None


async def test_a_watch_check_is_no_run_of_the_day(cfg, user_id, rig):
    bot = await _linux_bot(cfg, user_id)
    routine = await _watching(rig, user_id, bot)
    rig.desks.for_bot(bot.id, "linux").serve_screen(_chat_screen())
    await rig.check(user_id, routine)
    assert await rig.runner.runs_today(user_id, bot.id) == 0


async def test_only_one_check_waits_per_routine(cfg, user_id, rig):
    bot = await _linux_bot(cfg, user_id)
    routine = await _watching(rig, user_id, bot)
    await rig.bots.set_off_duty(user_id, bot.id, True)       # nothing drains, so the first check stays queued
    assert await rig.checker.queue_check(user_id, routine) is False   # off duty: no check at all
    await rig.bots.set_off_duty(user_id, bot.id, False)
    rig.desks.for_bot(bot.id, "linux").serve_screen(_chat_screen())
    assert await rig.checker.queue_check(user_id, routine)
    assert await rig.checker.queue_check(user_id, routine) is False
    await wait_idle(rig.runner)


async def test_your_message_is_never_batched_with_a_check(cfg, user_id, rig):
    bot = await _linux_bot(cfg, user_id)
    routine = await _watching(rig, user_id, bot)
    rig.desks.for_bot(bot.id, "linux").serve_screen(_chat_screen())
    thread, _ = await rig.talk.ensure_main_thread(user_id, bot.id)
    await rig.checker.queue_check(user_id, routine)
    await send(rig, user_id, bot.id, thread.id, "hello")
    await wait_idle(rig.runner)
    assert len(rig.model.requests) == 1                  # your message ran; the check ran with no model
    assert (await rig.snaps.get(user_id, routine.id)) is not None


async def test_a_page_part_not_found_falls_back_to_the_whole_page(cfg, user_id, rig):
    bot = await _linux_bot(cfg, user_id)
    routine = await _watching(rig, user_id, bot, part="the price box")
    rig.desks.for_bot(bot.id, "linux").serve_screen(_chat_screen())
    await rig.check(user_id, routine)
    snap = await rig.snaps.get(user_id, routine.id)
    assert "Mum" in snap.snapshot and "Francis" in snap.snapshot


async def test_the_scheduler_queues_a_check_every_interval_and_never_a_model_run(cfg, user_id, rig, clock):
    from roost.routines.scheduler import RoutineScheduler

    bot = await _linux_bot(cfg, user_id)
    routine = await _watching(rig, user_id, bot)
    rig.desks.for_bot(bot.id, "linux").serve_screen(_chat_screen())
    launcher = RoutineLauncher(rig.talk, rig.runner, rig.runs, rig.events)
    scheduler = RoutineScheduler(cfg, clock=clock, launcher=launcher, runs=rig.runs, routines=rig.routines,
                                 turns=rig.runner, bots=rig.bots, hooks=rig.hooks, watch=rig.checker)
    await scheduler.tick()                                     # not due yet
    await wait_idle(rig.runner)
    assert await rig.snaps.get(user_id, routine.id) is None
    clock.now += timedelta(minutes=5)
    await scheduler.tick()
    await wait_idle(rig.runner)
    assert (await rig.snaps.get(user_id, routine.id)).fingerprint
    assert (await rig.routines.get(user_id, routine.id)).next_run_at == clock.now + timedelta(minutes=5)
    clock.now += timedelta(hours=3)                            # slept through many checks: one check, no backlog
    await scheduler.tick()
    await wait_idle(rig.runner)
    assert rig.model.requests == []
    assert [n for _, n in await rig.notes(user_id, routine.id)][0] == "No change"


async def test_a_mac_brave_bot_reads_the_page_text(cfg, user_id, rig, clock):
    bot = await make_bot(cfg, user_id, "Mac")
    routine = await _watching(rig, user_id, bot, part="")
    desk = rig.desks.for_bot(bot.id, "mac_brave")
    desk.serve(CHATS_URL, PageText(url=CHATS_URL, title="Shop", text="Price €24.99 " * 30, truncated=False))
    await rig.check(user_id, routine)
    desk.serve(CHATS_URL, PageText(url=CHATS_URL, title="Shop", text="Price €19.99 " * 30, truncated=False))
    await rig.check(user_id, routine)
    assert len(rig.model.requests) >= 1 and "€19.99" in rig.model.requests[0].system
