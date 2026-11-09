"""Message-first claims: your own messages go before routine items, and a kind can be left out."""

from __future__ import annotations

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.talk.store import TalkStore
from roost.work.models import ORIGIN_YOU, WorkDraft, WorkKind, routine_origin
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


def _draft(bot, thread, kind: WorkKind, body: str) -> WorkDraft:
    origin = routine_origin("News") if kind is WorkKind.ROUTINE else ORIGIN_YOU
    return WorkDraft(bot_id=bot.id, thread_id=thread.id, kind=kind, origin=origin, body=body)


async def test_your_message_claims_before_an_older_routine_item(cfg, user_id, bot):
    talk, queue = TalkStore(cfg), WorkQueue(cfg)
    routine_thread = await talk.create_thread(user_id, bot.id, "News", kind="routine")
    chat = await talk.create_thread(user_id, bot.id)
    await queue.enqueue(user_id, _draft(bot, routine_thread, WorkKind.ROUTINE, "older routine"))
    await queue.enqueue(user_id, _draft(bot, chat, WorkKind.MESSAGE, "hello"))

    first = await queue.claim_batch(user_id, bot.id, "run-1")
    second = await queue.claim_batch(user_id, bot.id, "run-2")

    assert [i.body for i in first] == ["hello"]
    assert [i.body for i in second] == ["older routine"]


async def test_card_answers_also_go_first(cfg, user_id, bot):
    talk, queue = TalkStore(cfg), WorkQueue(cfg)
    routine_thread = await talk.create_thread(user_id, bot.id, "News", kind="routine")
    chat = await talk.create_thread(user_id, bot.id)
    await queue.enqueue(user_id, _draft(bot, routine_thread, WorkKind.ROUTINE, "routine"))
    await queue.enqueue(user_id, _draft(bot, chat, WorkKind.CARD_ANSWER, "continue"))

    first = await queue.claim_batch(user_id, bot.id, "run-1")

    assert [i.body for i in first] == ["continue"]


async def test_excluded_kinds_are_never_claimed(cfg, user_id, bot):
    talk, queue = TalkStore(cfg), WorkQueue(cfg)
    routine_thread = await talk.create_thread(user_id, bot.id, "News", kind="routine")
    await queue.enqueue(user_id, _draft(bot, routine_thread, WorkKind.ROUTINE, "routine"))

    assert await queue.claim_batch(user_id, bot.id, "run-1", exclude_kinds=frozenset({WorkKind.ROUTINE})) == ()
    assert [i.body for i in await queue.claim_batch(user_id, bot.id, "run-2")] == ["routine"]


async def test_other_work_sits_between_your_messages_and_routines(cfg, user_id, bot):
    talk, queue = TalkStore(cfg), WorkQueue(cfg)
    routine_thread = await talk.create_thread(user_id, bot.id, "News", kind="routine")
    chat = await talk.create_thread(user_id, bot.id)
    await queue.enqueue(user_id, _draft(bot, routine_thread, WorkKind.ROUTINE, "routine"))
    await queue.enqueue(user_id, _draft(bot, chat, WorkKind.HANDOFF, "handoff"))

    assert [i.body for i in await queue.claim_batch(user_id, bot.id, "run-1")] == ["handoff"]
