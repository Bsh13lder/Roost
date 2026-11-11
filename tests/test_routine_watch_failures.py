"""A page watch whose check can't read the page is never silent (owner, 2026-11-10, after a 30-minute silence while
bot 1016fb46's tab was frozen; docs/plans/2026-11-10-roost-self-healing.md): a failed check is one folded run-log
line like "No change", ``WATCH_FAILS_STUCK`` failures in a row say so once in the bot's chat, the routine keeps its
last error (kind and time) for the History, and a waiting check older than two intervals is replaced."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from roost.config import load_config
from roost.constants import (
    ROUTINE_ERROR_NO_ANSWER, ROUTINE_ERROR_NO_ROOM, ROUTINE_ERROR_RUN, WATCH_FAILS_STUCK,
    WATCH_STALE_TRIGGER_INTERVALS,
)
from roost.db.connection import init_db
from roost.desk.fake_chats import CHATS_URL
from roost.gateway.auth import register_user
from roost.gateway.routes.routines import routine_out
from roost.routines.service import RoutineView
from roost.work.models import WorkDraft, WorkKind
from team_helpers import wait_idle
from test_routine_watch import NOW, FakeClock, Rig, _chat_screen, _linux_bot, _watching

UTC = timezone.utc


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


async def _chat_lines(rig: Rig, user_id: str, bot_id: str) -> list[str]:
    main = await rig.talk.main_thread(user_id, bot_id)
    if main is None:
        return []
    return [m.body for m in await rig.talk.list_messages(user_id, main.id) if m.kind == "routine_note"]


async def test_failed_checks_fold_into_one_run_log_line_and_keep_the_last_error(cfg, user_id, rig, clock):
    bot = await _linux_bot(cfg, user_id)
    routine = await _watching(rig, user_id, bot)
    desk = rig.desks.for_bot(bot.id, "linux")
    desk.force_unavailable = True

    for _ in range(2):
        await rig.check(user_id, routine)
        clock.now += timedelta(minutes=5)

    assert await rig.notes(user_id, routine.id) == [("error", "Couldn't check: the computer didn't answer · 2 times")]
    kept = await rig.routines.get(user_id, routine.id)
    assert kept.last_error_kind == ROUTINE_ERROR_NO_ANSWER
    assert kept.last_error_at == clock.now - timedelta(minutes=5)
    assert await _chat_lines(rig, user_id, bot.id) == []          # two in a row is not yet worth a chat line
    assert rig.model.requests == []


async def test_three_failures_in_a_row_say_so_once_in_the_chat_and_a_good_read_clears_it(cfg, user_id, rig, clock):
    bot = await _linux_bot(cfg, user_id)
    routine = await _watching(rig, user_id, bot)
    desk = rig.desks.for_bot(bot.id, "linux")
    desk.force_unavailable = True

    for _ in range(WATCH_FAILS_STUCK + 1):
        await rig.check(user_id, routine)
        clock.now += timedelta(minutes=5)

    lines = await _chat_lines(rig, user_id, bot.id)
    assert len(lines) == 1 and routine.watch.host in lines[0] and "didn't answer 3 times in a row" in lines[0]
    assert await rig.notes(user_id, routine.id) == [
        ("error", f"Couldn't check: the computer didn't answer · {WATCH_FAILS_STUCK + 1} times")]

    desk.force_unavailable = False
    desk.serve_screen(_chat_screen())
    await rig.check(user_id, routine)

    notes = await rig.notes(user_id, routine.id)
    assert notes[0] == ("done", "Started watching: saved the page to compare with") and len(notes) == 2
    kept = await rig.routines.get(user_id, routine.id)
    assert kept.last_error_kind is None and kept.last_error_at is None
    snap = await rig.snaps.get(user_id, routine.id)
    assert snap.fail_count == 0 and snap.fail_run_id is None
    assert len(await _chat_lines(rig, user_id, bot.id)) == 1       # nothing more was said


async def test_no_free_computer_twice_in_a_row_writes_the_line(cfg, user_id, rig, clock):
    bot = await _linux_bot(cfg, user_id)
    routine = await _watching(rig, user_id, bot)
    desk = rig.desks.for_bot(bot.id, "linux")
    desk.force_busy = True

    await rig.check(user_id, routine)
    assert await rig.notes(user_id, routine.id) == []              # one skip stays quiet, as before
    clock.now += timedelta(minutes=5)
    await rig.check(user_id, routine)

    assert await rig.notes(user_id, routine.id) == [("error", "Couldn't check: no free computer · 2 times")]
    assert (await rig.routines.get(user_id, routine.id)).last_error_kind == ROUTINE_ERROR_NO_ROOM


async def test_a_waiting_check_older_than_two_intervals_is_replaced(cfg, user_id, rig, clock):
    bot = await _linux_bot(cfg, user_id)
    routine = await _watching(rig, user_id, bot)
    desk = rig.desks.for_bot(bot.id, "linux")
    desk.serve_screen(_chat_screen())
    queue = rig.runner.queue
    stale = await queue.enqueue(user_id, WorkDraft(bot_id=bot.id, thread_id=routine.thread_id, kind=WorkKind.TRIGGER,
                                                  origin="watch", body=routine.id))
    claimed = await queue.claim_batch(user_id, bot.id, "a-dead-drain")      # leased by a drain that died
    assert [item.id for item in claimed] == [stale.id]

    clock.now = datetime.now(UTC) + timedelta(minutes=routine.watch.every_min)
    assert await rig.checker.queue_check(user_id, routine) is False          # one interval old: still its turn

    clock.now = datetime.now(UTC) + timedelta(minutes=routine.watch.every_min * WATCH_STALE_TRIGGER_INTERVALS + 1)
    assert await rig.checker.queue_check(user_id, routine) is True
    await wait_idle(rig.runner)

    assert desk.open_page_calls == [CHATS_URL]
    assert (await queue.get(user_id, stale.id)).state.value == "dropped"


async def test_a_run_that_did_not_finish_is_the_routines_last_error_until_one_finishes(cfg, user_id, rig, clock):
    bot = await _linux_bot(cfg, user_id)
    routine = await _watching(rig, user_id, bot)
    failed = await rig.runs.record(user_id, routine, clock.now, "running")
    await rig.hooks.finish(user_id, failed, "error")
    kept = await rig.routines.get(user_id, routine.id)
    assert (kept.last_error_kind, kept.last_error_at) == (ROUTINE_ERROR_RUN, clock.now)

    clock.now += timedelta(minutes=5)
    fine = await rig.runs.record(user_id, routine, clock.now, "running")
    await rig.hooks.finish(user_id, fine, "done")
    assert (await rig.routines.get(user_id, routine.id)).last_error_kind is None


async def test_the_routine_json_carries_the_last_error(cfg, user_id, rig, clock):
    bot = await _linux_bot(cfg, user_id)
    routine = await _watching(rig, user_id, bot)
    assert routine_out(RoutineView(routine=routine, words="", slot=None, last_state=None))["last_error"] is None
    await rig.routines.set_last_error(user_id, routine.id, ROUTINE_ERROR_NO_ANSWER, clock.now)
    kept = await rig.routines.get(user_id, routine.id)
    out = routine_out(RoutineView(routine=kept, words="", slot=None, last_state=None))
    assert out["last_error"] == {"kind": "no_answer", "at": "2026-11-04T13:50:00+00:00"}
