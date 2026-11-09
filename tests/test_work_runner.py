"""``TurnRunner`` over the durable work queue (spec §4.2, step 5, D-A)."""

from __future__ import annotations

import asyncio

import pytest

from roost.config import load_config
from roost.constants import STEER_TURN_PREFIX
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.work.models import ORIGIN_YOU, WorkDraft, WorkKind, WorkState
from team_helpers import GatedModel, make_bot, make_rig, send, until, wait_idle


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


async def _bot_replies(rig, user_id, thread_id):
    return [m.body for m in await rig.talk.list_messages(user_id, thread_id) if m.role == "bot"]


async def test_a_busy_bot_accepts_a_message_at_once(cfg, user_id, bot):
    rig = make_rig(cfg, GatedModel(["first", "second"]))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "first")
    await until(lambda: len(rig.model.requests) == 1)

    item = await asyncio.wait_for(send(rig, user_id, bot.id, thread.id, "second"), timeout=1)

    assert item.state is WorkState.QUEUED
    rig.model.release.set()
    await wait_idle(rig.runner)


async def test_messages_sent_while_busy_join_the_running_turn(cfg, user_id, bot):
    """Steer: messages sent while the bot's run for this chat works are read by that run, all at its next
    boundary, and the one reply covers them."""
    rig = make_rig(cfg, GatedModel(["first answer", "one answer for three"]))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "first")
    await until(lambda: len(rig.model.requests) == 1)
    for text in ("two", "three", "four"):
        await send(rig, user_id, bot.id, thread.id, text)

    rig.model.release.set()
    await wait_idle(rig.runner)

    assert await _bot_replies(rig, user_id, thread.id) == ["first answer\n\none answer for three"]
    assert len(rig.model.requests) == 2
    user_turns = [t.text.removeprefix(STEER_TURN_PREFIX) for t in rig.model.requests[1].turns if t.role == "user"]
    assert user_turns[-3:] == ["two", "three", "four"]


async def test_messages_to_two_threads_of_one_busy_bot_are_both_answered(cfg, user_id, bot):
    rig = make_rig(cfg, GatedModel(["a1", "a2", "b1"]))
    thread_a = await rig.talk.create_thread(user_id, bot.id)
    thread_b = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread_a.id, "first in A")
    await until(lambda: len(rig.model.requests) == 1)
    await send(rig, user_id, bot.id, thread_b.id, "only in B")
    await send(rig, user_id, bot.id, thread_a.id, "second in A")

    rig.model.release.set()
    await wait_idle(rig.runner)

    # Steer: the second message in A joins A's run; B waits for its own run.
    assert await _bot_replies(rig, user_id, thread_a.id) == ["a1\n\na2"]
    assert await _bot_replies(rig, user_id, thread_b.id) == ["b1"]


async def test_each_run_tells_the_model_where_it_came_from(cfg, user_id, bot):
    rig = make_rig(cfg, GatedModel(["hi"], hold=()))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "hello")
    await wait_idle(rig.runner)
    assert "This run came from: you, in your chat." in rig.model.requests[0].system


async def test_a_finished_run_is_logged_and_its_items_are_done(cfg, user_id, bot):
    rig = make_rig(cfg, GatedModel(["hi"], hold=()))
    thread = await rig.talk.create_thread(user_id, bot.id)
    item = await send(rig, user_id, bot.id, thread.id, "hello")
    await wait_idle(rig.runner)

    stored = await rig.runner.queue.get(user_id, item.id)
    assert (stored.state, stored.result) == (WorkState.DONE, "hi")
    async with db_session(cfg) as db:
        rows = await (await db.execute(
            "SELECT outcome FROM runs WHERE user_id = ? AND bot_id = ?", (user_id, bot.id),
        )).fetchall()
    assert [r["outcome"] for r in rows] == ["done"]


async def test_the_reply_is_written_by_the_bot(cfg, user_id, bot):
    rig = make_rig(cfg, GatedModel(["hi"], hold=()))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "hello")
    await wait_idle(rig.runner)
    [reply] = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.role == "bot"]
    assert (reply.kind, reply.author_bot_id) == ("text", bot.id)


async def test_boot_recovery_notes_the_interrupted_call_and_reruns_the_item_once(cfg, user_id, bot):
    crashed = make_rig(cfg, GatedModel([], hold=()))
    thread = await crashed.talk.create_thread(user_id, bot.id)
    item = await crashed.runner.queue.enqueue(user_id, WorkDraft(
        bot_id=bot.id, thread_id=thread.id, kind=WorkKind.MESSAGE, origin=ORIGIN_YOU, body="open it",
    ))
    await crashed.runner.queue.claim_batch(user_id, bot.id, "run-before-crash")
    await crashed.runner.queue.set_inflight(user_id, "run-before-crash", "open_page(https://example.com)")

    rebooted = make_rig(cfg, GatedModel(["checked first"], hold=()))
    await rebooted.runner.recover_on_boot()
    await rebooted.runner.resume_all()
    await wait_idle(rebooted.runner)
    await rebooted.runner.resume_all()
    await wait_idle(rebooted.runner)

    notes = [(m.kind, m.body) for m in await rebooted.talk.list_messages(user_id, thread.id) if m.role == "system"]
    assert notes == [("interrupted", "Interrupted, outcome unknown: open_page(https://example.com). "
                                     "The bot will check before repeating it.")]
    assert len(rebooted.model.requests) == 1
    assert "Its outcome is unknown" in rebooted.model.requests[0].system
    assert (await rebooted.runner.queue.get(user_id, item.id)).state is WorkState.DONE


async def test_boot_recovery_taints_the_rerun_since_the_crashed_runs_taint_is_unknown(cfg, user_id, bot):
    """Fix round 1, finding 1: the crashed run's own taint
    (``_ToolRunner.tainted``) lived only in memory and is persisted only
    by a normal ``complete()``. The item's ``inflight`` note survives the
    crash (``recover_on_boot`` keeps it); the re-run must treat that as
    "taint unknown, assume tainted" rather than start clean and risk
    laundering a page-derived call in as trustworthy."""
    crashed = make_rig(cfg, GatedModel([], hold=()))
    thread = await crashed.talk.create_thread(user_id, bot.id)
    item = await crashed.runner.queue.enqueue(user_id, WorkDraft(
        bot_id=bot.id, thread_id=thread.id, kind=WorkKind.MESSAGE, origin=ORIGIN_YOU, body="open it",
    ))
    await crashed.runner.queue.claim_batch(user_id, bot.id, "run-before-crash")
    await crashed.runner.queue.set_inflight(user_id, "run-before-crash", "open_page(https://attacker.example)")

    rebooted = make_rig(cfg, GatedModel(["checked first"], hold=()))
    await rebooted.runner.recover_on_boot()
    await rebooted.runner.resume_all()
    await wait_idle(rebooted.runner)
    await rebooted.runner.resume_all()
    await wait_idle(rebooted.runner)

    [reply] = [m for m in await rebooted.talk.list_messages(user_id, thread.id) if m.role == "bot"]
    assert reply.tainted is True
    stored = await rebooted.runner.queue.get(user_id, item.id)
    assert (stored.state, stored.result_tainted) == (WorkState.DONE, True)


async def test_boot_recovery_posts_one_notice_per_run_not_per_item_in_its_batch(cfg, user_id, bot):
    """Fix round 1, finding 2: ``set_inflight`` writes the SAME note to
    every item of a claimed batch. A 2-item batch interrupted by one
    crash must still produce exactly one "interrupted" notice and
    mention the call exactly once in the re-run's system prompt, not
    once per item."""
    crashed = make_rig(cfg, GatedModel([], hold=()))
    thread = await crashed.talk.create_thread(user_id, bot.id)
    for body in ("open it", "and then?"):
        await crashed.runner.queue.enqueue(user_id, WorkDraft(
            bot_id=bot.id, thread_id=thread.id, kind=WorkKind.MESSAGE, origin=ORIGIN_YOU, body=body,
        ))
    batch = await crashed.runner.queue.claim_batch(user_id, bot.id, "run-before-crash")
    assert len(batch) == 2
    await crashed.runner.queue.set_inflight(user_id, "run-before-crash", "open_page(https://example.com)")

    rebooted = make_rig(cfg, GatedModel(["checked first"], hold=()))
    await rebooted.runner.recover_on_boot()
    await rebooted.runner.resume_all()
    await wait_idle(rebooted.runner)
    await rebooted.runner.resume_all()
    await wait_idle(rebooted.runner)

    interrupted_notes = [m for m in await rebooted.talk.list_messages(user_id, thread.id) if m.kind == "interrupted"]
    assert len(interrupted_notes) == 1
    system_prompt = rebooted.model.requests[0].system
    assert system_prompt.count("open_page(https://example.com)") == 1
