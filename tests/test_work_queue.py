"""``WorkQueue`` — the durable per-bot work queue (spec §4.2, step 5)."""

from __future__ import annotations

import pytest

from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.talk.store import TalkStore
from roost.work.models import ORIGIN_YOU, WorkDraft, WorkKind, WorkState
from roost.work.queue import WorkQueue
from team_helpers import make_bot


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


@pytest.fixture
def queue(cfg):
    return WorkQueue(cfg)


def _draft(bot_id: str, thread_id: str, body: str, **extra) -> WorkDraft:
    return WorkDraft(bot_id=bot_id, thread_id=thread_id, kind=extra.pop("kind", WorkKind.MESSAGE),
                     origin=ORIGIN_YOU, body=body, **extra)


async def test_enqueue_stores_body_and_origin_encrypted(cfg, queue, user_id, bot):
    thread = await TalkStore(cfg).create_thread(user_id, bot.id)
    item = await queue.enqueue(user_id, _draft(bot.id, thread.id, "buy milk"))

    async with db_session(cfg) as db:
        row = await (await db.execute(
            "SELECT body, origin, state, tainted FROM work_items WHERE id = ?", (item.id,),
        )).fetchone()
    assert row["body"].startswith("enc:") and "buy milk" not in row["body"]
    assert row["origin"].startswith("enc:")
    assert (row["state"], row["tainted"]) == ("queued", 0)
    assert (await queue.get(user_id, item.id)).body == "buy milk"


async def test_items_in_a_row_for_one_thread_are_claimed_as_one_batch(cfg, queue, user_id, bot):
    talk = TalkStore(cfg)
    t1 = await talk.create_thread(user_id, bot.id)
    t2 = await talk.create_thread(user_id, bot.id)
    for thread_id, body in ((t1.id, "a"), (t1.id, "b"), (t2.id, "c"), (t1.id, "d")):
        await queue.enqueue(user_id, _draft(bot.id, thread_id, body))

    first = await queue.claim_batch(user_id, bot.id, "run-1")
    assert [i.body for i in first] == ["a", "b"]
    assert all(i.state is WorkState.CLAIMED and i.run_id == "run-1" for i in first)
    assert [i.body for i in await queue.claim_batch(user_id, bot.id, "run-2")] == ["c"]
    assert [i.body for i in await queue.claim_batch(user_id, bot.id, "run-3")] == ["d"]
    assert await queue.claim_batch(user_id, bot.id, "run-4") == ()


async def test_claim_never_takes_another_bots_items(cfg, queue, user_id, bot):
    other = await make_bot(cfg, user_id, "Quill")
    thread = await TalkStore(cfg).create_thread(user_id, other.id)
    await queue.enqueue(user_id, _draft(other.id, thread.id, "for Quill"))
    assert await queue.claim_batch(user_id, bot.id, "run-1") == ()


async def test_another_users_id_never_sees_an_item(cfg, queue, user_id, bot):
    other_user = (await register_user(cfg, "bob", "pw-123456")).id
    thread = await TalkStore(cfg).create_thread(user_id, bot.id)
    item = await queue.enqueue(user_id, _draft(bot.id, thread.id, "private"))
    assert await queue.get(other_user, item.id) is None
    assert await queue.claim_batch(other_user, bot.id, "run-x") == ()


async def test_complete_marks_the_runs_items_done_with_an_encrypted_result(cfg, queue, user_id, bot):
    thread = await TalkStore(cfg).create_thread(user_id, bot.id)
    item = await queue.enqueue(user_id, _draft(bot.id, thread.id, "q"))
    await queue.claim_batch(user_id, bot.id, "run-1")

    done_ids = await queue.complete(user_id, "run-1", "the answer", True)

    assert done_ids == (item.id,)
    stored = await queue.get(user_id, item.id)
    assert (stored.state, stored.result, stored.result_tainted) == (WorkState.DONE, "the answer", True)


async def test_drop_for_bot_reports_waiting_and_running_items(cfg, queue, user_id, bot):
    thread = await TalkStore(cfg).create_thread(user_id, bot.id)
    running = await queue.enqueue(user_id, _draft(bot.id, thread.id, "running"))
    await queue.claim_batch(user_id, bot.id, "run-1")
    waiting = await queue.enqueue(user_id, _draft(bot.id, thread.id, "waiting"))

    report = await queue.drop_for_bot(user_id, bot.id)

    assert [i.id for i in report.running] == [running.id]
    assert [i.id for i in report.waiting] == [waiting.id]
    assert report.run_ids == ("run-1",)
    assert (await queue.get(user_id, waiting.id)).state is WorkState.DROPPED


async def test_recover_on_boot_requeues_claimed_items_and_keeps_their_inflight_note(cfg, queue, user_id, bot):
    thread = await TalkStore(cfg).create_thread(user_id, bot.id)
    item = await queue.enqueue(user_id, _draft(bot.id, thread.id, "open it"))
    await queue.claim_batch(user_id, bot.id, "run-1")
    await queue.set_inflight(user_id, "run-1", "open_page(https://example.com)")

    report = await queue.recover_on_boot()

    assert [i.id for i in report.interrupted] == [item.id]
    [again] = await queue.claim_batch(user_id, bot.id, "run-2")
    assert again.inflight == "open_page(https://example.com)"     # the run that re-takes it is told
    assert (await queue.get(user_id, item.id)).inflight is None    # and the claim clears it


async def test_recover_on_boot_drops_open_handoffs(cfg, queue, user_id, bot):
    thread = await TalkStore(cfg).create_thread(user_id, bot.id)
    handoff = await queue.enqueue(user_id, _draft(bot.id, thread.id, "check prices", kind=WorkKind.HANDOFF, depth=1))

    report = await queue.recover_on_boot()

    assert [i.id for i in report.dropped_handoffs] == [handoff.id]
    assert (await queue.get(user_id, handoff.id)).state is WorkState.DROPPED


async def test_bots_with_queued_lists_each_bot_once(cfg, queue, user_id, bot):
    thread = await TalkStore(cfg).create_thread(user_id, bot.id)
    await queue.enqueue(user_id, _draft(bot.id, thread.id, "one"))
    await queue.enqueue(user_id, _draft(bot.id, thread.id, "two"))
    assert await queue.bots_with_queued() == ((user_id, bot.id),)


async def test_a_handoffs_link_scope_is_stored_encrypted_and_read_back(cfg, queue, user_id, bot):
    thread = await TalkStore(cfg).create_thread(user_id, bot.id)
    item = await queue.enqueue(user_id, _draft(bot.id, thread.id, "check", kind=WorkKind.HANDOFF,
                                               link_scope=("https://a.example/x",)))
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT link_scope FROM work_items WHERE id = ?", (item.id,))).fetchone()
    assert row["link_scope"].startswith("enc:v2:") and "a.example" not in row["link_scope"]
    assert (await queue.get(user_id, item.id)).link_scope == ("https://a.example/x",)
    plain = await queue.enqueue(user_id, _draft(bot.id, thread.id, "hi"))
    assert (await queue.get(user_id, plain.id)).link_scope == ()
