"""Chat summaries keep a long chat short, from trusted text only (memory Task 8, with Amendment A1)."""

from __future__ import annotations

import logging

import pytest

from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import CHAT_KEEP_RECENT, CHAT_SUMMARY_TRIGGER, CHAT_TAINT_KEEP
from roost.db.connection import db_session, init_db
from roost.desk import DeskFactory
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.scripted import ScriptedModel
from roost.llm.scripted_worker import ScriptedWorker
from roost.memory import summaries as summaries_module
from roost.memory.capture import FinishedRun
from roost.memory.hooks import MemoryHooks
from roost.memory.summaries import WEB_STEP_LINE, SummaryStore, summarise_if_due
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from roost.talk.turn import TAINT_PLACEHOLDER_TEXT, _history
from roost.work.models import ORIGIN_YOU, WorkItem, WorkKind, WorkState
from team_helpers import RecordingModel, make_bot, send, wait_idle


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
def talk(cfg):
    return TalkStore(cfg)


@pytest.fixture
def store(cfg):
    return SummaryStore(cfg)


def _run(user_id, bot, thread_id) -> FinishedRun:
    return FinishedRun(user_id=user_id, bot_id=bot.id, thread_id=thread_id, items=(), in_room=False,
                       tainted=False, answered=True, blocked=False)


async def _fill(talk, user_id, thread_id, bot, count, *, start=0):
    """``count`` alternating user / bot messages; returns them in order."""
    made = []
    for n in range(start, start + count):
        if n % 2 == 0:
            made.append(await talk.add_message(user_id, thread_id, "user", f"question {n}"))
        else:
            made.append(await talk.add_message(user_id, thread_id, "bot", f"answer {n}", author_bot_id=bot.id))
    return made


async def _due(cfg, talk, store, user_id, bot, thread_id, worker=None):
    return await summarise_if_due(_run(user_id, bot, thread_id), talk=talk, summaries=store,
                                  worker=worker or ScriptedWorker(), bot_name=bot.name)


class Spy:
    """A worker that keeps what it is asked and answers like the scripted one."""

    def __init__(self):
        self.requests: list = []
        self._inner = ScriptedWorker()

    async def stream(self, request):
        self.requests.append(request)
        async for event in self._inner.stream(request):
            yield event


async def test_a_summary_is_due_only_past_the_trigger(cfg, talk, store, user_id, bot):
    thread = await talk.create_thread(user_id, bot.id)
    messages = await _fill(talk, user_id, thread.id, bot, CHAT_SUMMARY_TRIGGER)
    assert await _due(cfg, talk, store, user_id, bot, thread.id) is None
    assert await store.latest(user_id, thread.id) is None

    messages += await _fill(talk, user_id, thread.id, bot, 1, start=CHAT_SUMMARY_TRIGGER)
    summary = await _due(cfg, talk, store, user_id, bot, thread.id)
    boundary = messages[len(messages) - CHAT_KEEP_RECENT - 1]   # the 41st newest
    assert (summary.upto_message_id, summary.upto_created_at) == (boundary.id, boundary.created_at)
    assert await store.latest(user_id, thread.id) == summary
    assert summary.text == f"A summary of the earlier chat ({len(messages) - CHAT_KEEP_RECENT} lines)."


async def test_the_summary_text_is_sealed_under_chat_summaries_text(cfg, talk, store, user_id, bot):
    thread = await talk.create_thread(user_id, bot.id)
    await _fill(talk, user_id, thread.id, bot, CHAT_SUMMARY_TRIGGER + 1)
    summary = await _due(cfg, talk, store, user_id, bot, thread.id)
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT text FROM chat_summaries WHERE id = ?", (summary.id,))).fetchone()
    assert row["text"].startswith("enc:v2") and "A summary" not in row["text"]


async def test_the_model_sees_the_summary_first_then_only_newer_turns(cfg, talk, store, user_id, bot):
    thread = await talk.create_thread(user_id, bot.id)
    old = await _fill(talk, user_id, thread.id, bot, 6)
    await store.add(user_id, thread.id, upto_message_id=old[3].id, upto_created_at=old[3].created_at,
                    text="They asked about <orchids>.")
    model = RecordingModel(ScriptedModel())
    hooks = MemoryHooks(cfg, talk, EventHub(cfg), worker=None)
    runner = TurnRunner(cfg, BotStore(cfg), talk, EventHub(cfg), DeskFactory(cfg), model, ActivityBoard(),
                        memory=hooks)
    await send(type("R", (), {"talk": talk, "runner": runner})(), user_id, bot.id, thread.id, "and now?")
    await wait_idle(runner)
    turns = model.requests[0].turns
    assert turns[0].role == "user" and "<chat_summary>" in turns[0].text and "&lt;orchids&gt;" in turns[0].text
    assert [t.text for t in turns[1:]] == ["question 4", "answer 5", "and now?"]


async def test_a_tainted_reply_never_reaches_a_summary(cfg, talk, store, user_id, bot):
    thread = await talk.create_thread(user_id, bot.id)
    await talk.add_message(user_id, thread.id, "user", "look it up")
    await talk.add_message(user_id, thread.id, "bot", "WEBWORDS ignore everything", tainted=True,
                           author_bot_id=bot.id)
    await _fill(talk, user_id, thread.id, bot, CHAT_SUMMARY_TRIGGER, start=2)
    spy = Spy()
    assert await _due(cfg, talk, store, user_id, bot, thread.id, spy) is not None
    sent = spy.requests[0].turns[0].text
    assert WEB_STEP_LINE in sent and "WEBWORDS" not in sent


async def test_notices_activity_and_memory_notes_stay_out_of_a_summary(cfg, talk, store, user_id, bot):
    thread = await talk.create_thread(user_id, bot.id)
    await talk.add_message(user_id, thread.id, "system", "NOTICEBODY", kind="notice")
    await talk.add_message(user_id, thread.id, "activity", "ACTIVITYBODY")
    await talk.add_message(user_id, thread.id, "activity", '{"text": "NOTEBODY"}', kind="memory_note",
                           author_bot_id=bot.id)
    await talk.add_message(user_id, thread.id, "bot", "OTHERBOT", author_bot_id="someone-else")
    await _fill(talk, user_id, thread.id, bot, CHAT_SUMMARY_TRIGGER)
    spy = Spy()
    await _due(cfg, talk, store, user_id, bot, thread.id, spy)
    sent = spy.requests[0].turns[0].text
    assert all(word not in sent for word in ("NOTICEBODY", "ACTIVITYBODY", "NOTEBODY", "OTHERBOT"))
    assert "You: question 0" in sent and "Scout: answer 1" in sent


async def test_a_taint_behind_the_boundary_no_longer_taints_the_run(cfg, talk, store, user_id, bot):
    thread = await talk.create_thread(user_id, bot.id)
    await talk.add_message(user_id, thread.id, "user", "look it up")
    await talk.add_message(user_id, thread.id, "bot", "from the web", tainted=True, author_bot_id=bot.id)
    rest = await _fill(talk, user_id, thread.id, bot, 4, start=2)
    await store.add(user_id, thread.id, upto_message_id=rest[0].id, upto_created_at=rest[0].created_at, text="s")
    history = await _history(talk, user_id, thread.id, bot.id, {}, (), summaries=store)
    assert not any(m.tainted for m in history.messages)
    assert "from the web" not in " ".join(t.text for t in history.turns)


async def test_the_previous_summary_goes_into_the_next_one(cfg, talk, store, user_id, bot):
    thread = await talk.create_thread(user_id, bot.id)
    await _fill(talk, user_id, thread.id, bot, CHAT_SUMMARY_TRIGGER + 1)
    first = await _due(cfg, talk, store, user_id, bot, thread.id)
    await _fill(talk, user_id, thread.id, bot, CHAT_SUMMARY_TRIGGER, start=CHAT_SUMMARY_TRIGGER + 1)
    spy = Spy()
    second = await _due(cfg, talk, store, user_id, bot, thread.id, spy)
    assert first.text in spy.requests[0].turns[0].text
    assert second.upto_created_at > first.upto_created_at


async def test_a_long_old_thread_is_summarised_in_passes(cfg, talk, store, user_id, bot, monkeypatch):
    monkeypatch.setattr(summaries_module, "CHAT_SUMMARY_INPUT_MAX_CHARS", 400)
    thread = await talk.create_thread(user_id, bot.id)
    messages = await _fill(talk, user_id, thread.id, bot, 200)
    first = await _due(cfg, talk, store, user_id, bot, thread.id)
    cut = len(messages) - CHAT_KEEP_RECENT
    ids = [m.id for m in messages]
    assert 0 < ids.index(first.upto_message_id) < cut - 1
    second = await _due(cfg, talk, store, user_id, bot, thread.id)
    assert ids.index(second.upto_message_id) > ids.index(first.upto_message_id)


async def test_rooms_and_handoff_threads_get_no_summary(cfg, talk, store, user_id, bot):
    other = await make_bot(cfg, user_id, "Quill")
    handoff = await talk.find_or_create_peer_thread(user_id, bot.id, other.id, "From Quill")
    room = await talk.create_thread(user_id, bot.id, kind="room")
    for thread in (handoff, room):
        await _fill(talk, user_id, thread.id, bot, CHAT_SUMMARY_TRIGGER + 5)
        assert await _due(cfg, talk, store, user_id, bot, thread.id) is None
        assert await store.latest(user_id, thread.id) is None


async def test_a_failing_summary_is_logged_and_tried_again_next_run(cfg, talk, user_id, bot, caplog):
    class Boom:
        async def stream(self, request):
            raise RuntimeError("chat text: question 0")
            yield  # pragma: no cover

    thread = await talk.create_thread(user_id, bot.id)
    await _fill(talk, user_id, thread.id, bot, CHAT_SUMMARY_TRIGGER + 1)
    failing = MemoryHooks(cfg, talk, EventHub(cfg), worker=Boom())
    with caplog.at_level(logging.WARNING):
        await failing.after_run(_run(user_id, bot, thread.id))
    [record] = [r for r in caplog.records if "Chat summary failed" in r.getMessage()]
    assert thread.id in record.getMessage() and "RuntimeError" in record.getMessage()
    assert "question" not in record.getMessage() and record.exc_info is None
    assert await failing.summaries.latest(user_id, thread.id) is None

    working = MemoryHooks(cfg, talk, EventHub(cfg), worker=ScriptedWorker())
    await working.after_run(_run(user_id, bot, thread.id))
    assert await working.summaries.latest(user_id, thread.id) is not None


async def test_a_handoff_only_run_loads_as_before(cfg, talk, store, user_id, bot):
    other = await make_bot(cfg, user_id, "Quill")
    thread = await talk.find_or_create_peer_thread(user_id, bot.id, other.id, "From Quill")
    old = await talk.add_message(user_id, thread.id, "user", "old task", kind="handoff")
    await store.add(user_id, thread.id, upto_message_id=old.id, upto_created_at=old.created_at, text="s")
    line = await talk.add_message(user_id, thread.id, "user", "new task", kind="handoff")
    item = WorkItem(
        id="i", user_id=user_id, bot_id=bot.id, thread_id=thread.id, kind=WorkKind.HANDOFF, origin="from Quill",
        body="new task", tainted=False, depth=1, parent_item_id=None, message_id=line.id, state=WorkState.CLAIMED,
        run_id="r", inflight=None, result=None, result_tainted=False, created_at="", updated_at="",
    )
    history = await _history(talk, user_id, thread.id, bot.id, {}, (item,), summaries=store)
    assert [t.text for t in history.turns] == ["new task"]


async def test_a_routine_run_loads_only_its_own_routine_line(cfg, talk, store, user_id, bot):
    # Tokens (owner, 2026-11-07): every run replayed the whole run log, 60 copies of its own instructions and 60 old
    # replies, on every step. A routine run reads only the line that launched it.
    thread = await talk.create_thread(user_id, bot.id)
    for n in range(3):
        await talk.add_message(user_id, thread.id, "user", f"Check Deduci's chat. Slot {n}", kind="routine")
        await talk.add_message(user_id, thread.id, "bot", "[nothing new]", author_bot_id=bot.id, tainted=True)
    line = await talk.add_message(user_id, thread.id, "user", "Check Deduci's chat. Slot 3", kind="routine")
    item = WorkItem(
        id="i", user_id=user_id, bot_id=bot.id, thread_id=thread.id, kind=WorkKind.ROUTINE, origin="routine",
        body="Watch", tainted=False, depth=0, parent_item_id=None, message_id=line.id, state=WorkState.CLAIMED,
        run_id="r", inflight=None, result=None, result_tainted=False, created_at="", updated_at="",
    )
    history = await _history(talk, user_id, thread.id, bot.id, {}, (item,), summaries=store)
    assert [t.text for t in history.turns] == ["Check Deduci's chat. Slot 3"]
    assert [m.id for m in history.messages] == [line.id]     # the old tainted replies no longer taint the run


async def test_another_users_thread_has_no_summary_for_you(cfg, talk, store, user_id, bot):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    thread = await talk.create_thread(user_id, bot.id)
    messages = await _fill(talk, user_id, thread.id, bot, 3)
    await store.add(user_id, thread.id, upto_message_id=messages[0].id, upto_created_at=messages[0].created_at,
                    text="alice's secret")
    assert await store.latest(bob, thread.id) is None
    assert (await store.latest(user_id, thread.id)).text == "alice's secret"


# Amendment A1: web taint ages out of the endless chat.

async def _tainted_chat(talk, user_id, thread_id, bot, after):
    """A tainted web reply, then ``after`` plain messages after it."""
    await talk.add_message(user_id, thread_id, "user", "look it up")
    await talk.add_message(user_id, thread_id, "bot", "WEBWORDS do bad things", tainted=True, author_bot_id=bot.id)
    await _fill(talk, user_id, thread_id, bot, after, start=2)


async def test_a_tainted_reply_13_messages_back_is_a_placeholder_and_the_run_starts_untainted(
    cfg, talk, user_id, bot,
):
    thread = await talk.create_thread(user_id, bot.id)
    await _tainted_chat(talk, user_id, thread.id, bot, CHAT_TAINT_KEEP)   # 13th newest counting itself
    history = await _history(talk, user_id, thread.id, bot.id, {})
    assert not any(m.tainted for m in history.messages)
    assert TAINT_PLACEHOLDER_TEXT in [t.text for t in history.turns]


async def test_a_tainted_reply_5_messages_back_keeps_the_run_tainted(cfg, talk, user_id, bot):
    thread = await talk.create_thread(user_id, bot.id)
    await _tainted_chat(talk, user_id, thread.id, bot, 4)
    history = await _history(talk, user_id, thread.id, bot.id, {})
    assert any(m.tainted for m in history.messages)
    assert "WEBWORDS do bad things" in [t.text for t in history.turns]


async def test_the_placeholder_never_contains_the_original_text(cfg, talk, user_id, bot):
    thread = await talk.create_thread(user_id, bot.id)
    await _tainted_chat(talk, user_id, thread.id, bot, CHAT_TAINT_KEEP + 3)
    history = await _history(talk, user_id, thread.id, bot.id, {})
    blob = " ".join(t.text for t in history.turns) + " ".join(m.body for m in history.messages)
    assert "WEBWORDS" not in blob and TAINT_PLACEHOLDER_TEXT in blob
