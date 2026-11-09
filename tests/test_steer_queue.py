"""Steer: the queue side. A message taken mid-run is claimed under the running run's id, so it is answered once,
also across a gateway restart; the debounce reads the newest waiting message."""

from __future__ import annotations

import pytest

from roost.config import load_config
from roost.db.connection import init_db
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


def _draft(bot_id: str, thread_id: str, body: str, kind: WorkKind = WorkKind.MESSAGE) -> WorkDraft:
    return WorkDraft(bot_id=bot_id, thread_id=thread_id, kind=kind, origin=ORIGIN_YOU, body=body)


async def test_claim_thread_messages_takes_only_this_chats_waiting_messages(cfg, user_id, bot):
    queue, talk = WorkQueue(cfg), TalkStore(cfg)
    chat, other = await talk.create_thread(user_id, bot.id), await talk.create_thread(user_id, bot.id)
    await queue.enqueue(user_id, _draft(bot.id, chat.id, "first"))
    first = await queue.claim_batch(user_id, bot.id, "run-1")
    await queue.enqueue(user_id, _draft(bot.id, chat.id, "steer me"))
    await queue.enqueue(user_id, _draft(bot.id, other.id, "other chat"))
    await queue.enqueue(user_id, _draft(bot.id, chat.id, "a routine", kind=WorkKind.ROUTINE))
    await queue.enqueue(user_id, _draft(bot.id, chat.id, "a handoff", kind=WorkKind.HANDOFF))

    taken = await queue.claim_thread_messages(user_id, bot.id, chat.id, "run-1")

    assert [i.body for i in taken] == ["steer me"]
    assert all(i.state is WorkState.CLAIMED and i.run_id == "run-1" for i in taken)
    assert await queue.claim_thread_messages(user_id, bot.id, chat.id, "run-1") == ()
    done = await queue.complete(user_id, "run-1", "both answered", False)
    assert set(done) == {first[0].id, taken[0].id}


async def test_claim_thread_messages_is_scoped_by_user(cfg, user_id, bot):
    queue, talk = WorkQueue(cfg), TalkStore(cfg)
    chat = await talk.create_thread(user_id, bot.id)
    await queue.enqueue(user_id, _draft(bot.id, chat.id, "mine"))
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    assert await queue.claim_thread_messages(bob, bot.id, chat.id, "run-x") == ()
    assert (await queue.first_queued(user_id, bot.id)).body == "mine"


async def test_a_taken_message_is_answered_once_after_a_restart(cfg, user_id, bot):
    queue, talk = WorkQueue(cfg), TalkStore(cfg)
    chat = await talk.create_thread(user_id, bot.id)
    await queue.enqueue(user_id, _draft(bot.id, chat.id, "first"))
    await queue.claim_batch(user_id, bot.id, "run-1")
    await queue.enqueue(user_id, _draft(bot.id, chat.id, "steer me"))
    await queue.claim_thread_messages(user_id, bot.id, chat.id, "run-1")

    await queue.recover_on_boot()   # the gateway died mid-run: both go back to queued, for ONE new run

    again = await queue.claim_batch(user_id, bot.id, "run-2")
    assert [i.body for i in again] == ["first", "steer me"]


async def test_newest_queued_message_time(cfg, user_id, bot):
    queue, talk = WorkQueue(cfg), TalkStore(cfg)
    chat = await talk.create_thread(user_id, bot.id)
    assert await queue.newest_queued_message_at(user_id, bot.id) is None
    await queue.enqueue(user_id, _draft(bot.id, chat.id, "routine", kind=WorkKind.ROUTINE))
    assert await queue.newest_queued_message_at(user_id, bot.id) is None
    await queue.enqueue(user_id, _draft(bot.id, chat.id, "a"))
    newest = await queue.enqueue(user_id, _draft(bot.id, chat.id, "b"))
    assert await queue.newest_queued_message_at(user_id, bot.id) == newest.created_at
