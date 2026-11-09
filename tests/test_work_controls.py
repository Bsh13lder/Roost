"""Stop, Off duty, the daily cap and interrupted calls (spec §4.2, step 5, D-A)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

import roost.talk.runner as runner_module
from roost.bots.models import BotStatus
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.llm.scripted import ScriptedModel
from roost.llm.types import TextDelta, ToolCallRequested, TurnDone
from roost.work.models import WorkState
from roost.work.runs import madrid_day_start_utc, madrid_today, seconds_until_madrid_midnight
from team_helpers import GatedModel, frames_so_far, make_bot, make_rig, send, until, wait_idle


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


async def _messages(rig, user_id, thread_id):
    return await rig.talk.list_messages(user_id, thread_id)


async def _outcomes(cfg, user_id, bot_id):
    async with db_session(cfg) as db:
        rows = await (await db.execute(
            "SELECT outcome FROM runs WHERE user_id = ? AND bot_id = ? ORDER BY started_at", (user_id, bot_id),
        )).fetchall()
    return [row["outcome"] for row in rows]


async def test_stop_aborts_the_run_and_lists_the_dropped_messages(cfg, user_id, bot):
    rig = make_rig(cfg, GatedModel(["never sent"]))
    thread = await rig.talk.create_thread(user_id, bot.id)
    sub = rig.events.subscribe(user_id)
    await send(rig, user_id, bot.id, thread.id, "first")
    await until(lambda: len(rig.model.requests) == 1)
    await send(rig, user_id, bot.id, thread.id, "second")
    await send(rig, user_id, bot.id, thread.id, "third")

    report = await rig.runner.stop(user_id, bot.id)
    await wait_idle(rig.runner)

    assert [i.body for i in report.running] == ["first"]
    assert [i.body for i in report.waiting] == ["second", "third"]
    notes = [(m.kind, m.body) for m in await _messages(rig, user_id, thread.id) if m.role == "system"]
    assert notes == [("dropped", "Stopped. Dropped 2 waiting messages: “second”, “third”.")]
    assert (await rig.bots.get(user_id, bot.id)).status is BotStatus.RESTING
    assert len(rig.model.requests) == 1
    assert await _outcomes(cfg, user_id, bot.id) == ["stopped"]
    frames = await frames_so_far(sub)
    placeholder_id = next(f["message"]["id"] for f in frames if f["type"] == "message" and f["message"]["body"] == "")
    assert any(f["type"] == "message_done" and f["message_id"] == placeholder_id for f in frames)
    sub.close()


class _StallsAfterText:
    """Streams ``text``, then waits forever: a reply a Stop cuts short."""

    def __init__(self, text: str):
        self.text = text
        self.streamed = asyncio.Event()

    async def stream(self, request):
        yield TextDelta(self.text)
        self.streamed.set()
        await asyncio.Event().wait()
        yield TurnDone("end_turn")


async def test_stop_keeps_what_streamed_as_a_stored_reply_in_its_thread_slot(cfg, user_id, bot):
    """Task 7 fix round 2: a Stop-shortened reply is stored under its
    placeholder's id and published as a real ``message`` frame (with its
    per-thread ``seq``) before ``message_done`` -- the web never has to
    invent a seq for it, and it survives a reload."""
    model = _StallsAfterText("Dear landl")
    rig = make_rig(cfg, model)
    thread = await rig.talk.create_thread(user_id, bot.id)
    sub = rig.events.subscribe(user_id)
    await send(rig, user_id, bot.id, thread.id, "write to my landlord")
    await asyncio.wait_for(model.streamed.wait(), timeout=2)

    await rig.runner.stop(user_id, bot.id)
    await wait_idle(rig.runner)

    stored = [(m.role, m.body, m.seq) for m in await _messages(rig, user_id, thread.id)]
    assert stored == [("user", "write to my landlord", 1), ("bot", "Dear landl", 2), ("system", "Stopped.", 3)]
    frames = await frames_so_far(sub)
    sub.close()
    placeholder_id = next(f["message"]["id"] for f in frames if f["type"] == "message" and f["message"]["body"] == "")
    kept = [i for i, f in enumerate(frames) if f["type"] == "message" and f["message"]["id"] == placeholder_id
            and f["message"]["body"] == "Dear landl"]
    done = [i for i, f in enumerate(frames) if f["type"] == "message_done" and f["message_id"] == placeholder_id]
    assert len(kept) == 1 and frames[kept[0]]["message"]["seq"] == 2
    assert kept[0] < done[0]


async def test_a_call_running_at_stop_is_recorded_interrupted_outcome_unknown(cfg, user_id, bot):
    rig = make_rig(cfg, ScriptedModel(script=[
        [ToolCallRequested(id="t1", name="open_page", arguments={"url": "https://example.com"})],
    ]))
    entered = asyncio.Event()

    async def _hang(url: str):
        entered.set()
        await asyncio.Event().wait()

    rig.desks.for_bot(bot.id).open_page = _hang
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "read example.com")
    await asyncio.wait_for(entered.wait(), timeout=2)

    report = await rig.runner.stop(user_id, bot.id)

    assert [i.inflight for i in report.interrupted] == ["open_page(https://example.com)"]
    notes = [(m.kind, m.body) for m in await _messages(rig, user_id, thread.id) if m.role == "system"]
    assert notes == [
        ("dropped", "Stopped."),
        ("interrupted", "Interrupted, outcome unknown: open_page(https://example.com). "
                        "The bot will check before repeating it."),
    ]


async def test_stop_during_a_two_item_batch_posts_one_interrupted_note(cfg, user_id, bot):
    """Fix round 1, finding 1: ``set_inflight`` (queue.py) writes the SAME
    note to every claimed item of a run, so a Stop landing mid-call on a
    batch of more than one item (e.g. an Off-duty bot brought back with 2
    queued messages for the same thread) must still report and notice the
    interruption once per run, not once per item — the same dedupe boot
    recovery already has via ``_first_per_run``."""
    rig = make_rig(cfg, ScriptedModel(script=[
        [ToolCallRequested(id="t1", name="open_page", arguments={"url": "https://example.com"})],
    ]))
    entered = asyncio.Event()

    async def _hang(url: str):
        entered.set()
        await asyncio.Event().wait()

    rig.desks.for_bot(bot.id).open_page = _hang
    thread = await rig.talk.create_thread(user_id, bot.id)
    await rig.runner.set_off_duty(user_id, bot.id, True)
    await send(rig, user_id, bot.id, thread.id, "one")
    await send(rig, user_id, bot.id, thread.id, "two")
    await rig.runner.set_off_duty(user_id, bot.id, False)
    await asyncio.wait_for(entered.wait(), timeout=2)

    report = await rig.runner.stop(user_id, bot.id)

    assert len(report.interrupted) == 1
    notes = [m for m in await _messages(rig, user_id, thread.id) if m.kind == "interrupted"]
    assert len(notes) == 1


async def test_off_duty_keeps_messages_with_a_notice_and_runs_them_when_back(cfg, user_id, bot):
    rig = make_rig(cfg, GatedModel(["both at once"], hold=()))
    thread = await rig.talk.create_thread(user_id, bot.id)

    paused = await rig.runner.set_off_duty(user_id, bot.id, True)
    await send(rig, user_id, bot.id, thread.id, "one")
    await send(rig, user_id, bot.id, thread.id, "two")
    await wait_idle(rig.runner)

    assert (paused.off_duty, paused.status) == (True, BotStatus.OFF_DUTY)
    assert rig.model.requests == []
    notices = [m.body for m in await _messages(rig, user_id, thread.id) if m.kind == "notice"]
    assert notices == ["Scout is off duty. This waits until you bring it back."] * 2

    await rig.runner.set_off_duty(user_id, bot.id, False)
    await wait_idle(rig.runner)
    assert [m.body for m in await _messages(rig, user_id, thread.id) if m.role == "bot"] == ["both at once"]


async def test_after_a_restart_an_off_duty_bot_runs_each_queued_item_exactly_once(cfg, user_id, bot):
    before = make_rig(cfg, GatedModel([], hold=()))
    thread_a = await before.talk.create_thread(user_id, bot.id)
    thread_b = await before.talk.create_thread(user_id, bot.id)
    await before.runner.set_off_duty(user_id, bot.id, True)
    await send(before, user_id, bot.id, thread_a.id, "one")
    await send(before, user_id, bot.id, thread_b.id, "two")
    await wait_idle(before.runner)

    after = make_rig(cfg, GatedModel(["answer one", "answer two"], hold=()))
    await after.bots.reset_on_boot(after.events)
    await after.runner.recover_on_boot()
    await after.runner.resume_all()
    await wait_idle(after.runner)
    assert after.model.requests == []  # still Off duty after the restart

    await after.runner.set_off_duty(user_id, bot.id, False)
    await wait_idle(after.runner)
    await after.runner.resume_all()
    await wait_idle(after.runner)

    replies_a = [m.body for m in await _messages(after, user_id, thread_a.id) if m.role == "bot"]
    replies_b = [m.body for m in await _messages(after, user_id, thread_b.id) if m.role == "bot"]
    assert (replies_a, replies_b) == (["answer one"], ["answer two"])
    assert len(after.model.requests) == 2


async def test_off_duty_during_a_run_lets_it_finish_and_ends_off_duty(cfg, user_id, bot):
    rig = make_rig(cfg, GatedModel(["finished", "must not run"]))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "first")
    await until(lambda: len(rig.model.requests) == 1)

    await rig.runner.set_off_duty(user_id, bot.id, True)
    await send(rig, user_id, bot.id, thread.id, "second")
    rig.model.release.set()
    await wait_idle(rig.runner)

    assert [m.body for m in await _messages(rig, user_id, thread.id) if m.role == "bot"] == ["finished"]
    assert (await rig.bots.get(user_id, bot.id)).status is BotStatus.OFF_DUTY
    assert len(rig.model.requests) == 1


async def test_daily_limit_reached_posts_one_notice_and_keeps_the_items(cfg, user_id, bot, monkeypatch):
    monkeypatch.setattr(runner_module, "DAILY_RUN_CAP", 1)
    rig = make_rig(cfg, GatedModel(["first"], hold=()))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "one")
    await wait_idle(rig.runner)
    second = await send(rig, user_id, bot.id, thread.id, "two")
    await wait_idle(rig.runner)
    await send(rig, user_id, bot.id, thread.id, "three")
    await wait_idle(rig.runner)

    limits = [m.body for m in await _messages(rig, user_id, thread.id) if m.kind == "daily_limit"]
    assert limits == ["Daily limit reached: Scout has done 1 run today. "
                      "Waiting messages stay queued and run after midnight."]
    assert (await rig.runner.queue.get(user_id, second.id)).state is WorkState.QUEUED
    assert len(rig.model.requests) == 1


async def test_set_off_duty_publishes_bot_updated(cfg, user_id, bot):
    rig = make_rig(cfg, GatedModel([], hold=()))
    sub = rig.events.subscribe(user_id)
    await rig.runner.set_off_duty(user_id, bot.id, True)
    frames = await frames_so_far(sub)
    sub.close()
    [updated] = [f for f in frames if f["type"] == "bot_updated"]
    assert (updated["bot"]["id"], updated["bot"]["off_duty"], updated["bot"]["status"]) == (bot.id, True, "off_duty")


def test_madrid_day_boundaries():
    evening = datetime(2026, 10, 13, 21, 30, tzinfo=timezone.utc)      # 23:30 in Madrid (CEST)
    after_midnight = datetime(2026, 10, 13, 22, 30, tzinfo=timezone.utc)  # 00:30 next day in Madrid
    assert madrid_day_start_utc(evening) == "2026-10-12T22:00:00+00:00"
    assert madrid_day_start_utc(after_midnight) == "2026-10-13T22:00:00+00:00"
    assert madrid_today(after_midnight) == "2026-10-14"
    assert seconds_until_madrid_midnight(evening) == 30 * 60
