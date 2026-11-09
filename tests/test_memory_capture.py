"""Automatic capture after a clean run on your own messages (memory Task 6)."""

from __future__ import annotations

import json
import logging
from dataclasses import replace

import pytest

from roost.bots.status import ActivityBoard
from roost.config import load_config
from roost.constants import MEMORY_CAPTURE_MAX_ITEMS, MEMORY_CAPTURE_PER_HOUR
from roost.db.connection import db_session, init_db
from roost.desk import DeskFactory
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.scripted import ScriptedModel
from roost.llm.types import TextDelta, TurnDone
from roost.memory.capture import FinishedRun, parse_capture_reply, should_capture
from roost.memory.hooks import MemoryHooks
from roost.memory.models import MemoryDraft
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from roost.bots.store import BotStore
from roost.work.models import ORIGIN_YOU, WorkDraft, WorkItem, WorkKind, WorkState
from team_helpers import RecordingModel, make_bot, send, wait_idle


class Reply:
    """A worker that answers every call with one fixed text and keeps what it was asked."""

    def __init__(self, text: str):
        self.text = text
        self.requests: list = []

    async def stream(self, request):
        self.requests.append(request)
        yield TextDelta(self.text)
        yield TurnDone("end_turn")


def _json(*items) -> str:
    return json.dumps({"items": list(items)})


ANA = {"kind": "about_you", "text": "Ana's birthday is in May", "importance": 5}
LONG_MESSAGE = "Please remember that my sister Ana has her birthday in May and loves orchids"


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


def _rig(cfg, worker):
    bots, talk, events = BotStore(cfg), TalkStore(cfg), EventHub(cfg)
    hooks = MemoryHooks(cfg, talk, events, worker=worker)
    runner = TurnRunner(cfg, bots, talk, events, DeskFactory(cfg), ScriptedModel(), ActivityBoard(), memory=hooks)
    return runner, talk, events, hooks


def _run(user_id, bot, kind=WorkKind.MESSAGE, body=LONG_MESSAGE, **fields) -> FinishedRun:
    item = WorkItem(
        id="i1", user_id=user_id, bot_id=bot.id, thread_id="t1", kind=kind, origin=ORIGIN_YOU, body=body,
        tainted=False, depth=0, parent_item_id=None, message_id=None, state=WorkState.DONE, run_id="r1",
        inflight=None, result=None, result_tainted=False, created_at="", updated_at="",
    )
    base = dict(user_id=user_id, bot_id=bot.id, thread_id="t1", items=(item,), in_room=False, tainted=False,
                answered=True, blocked=False)
    return FinishedRun(**{**base, **fields})


@pytest.mark.parametrize("text,expected", [
    ("ok thanks", False), ("Remember the plumber", True), ("My sister is Ana", True), ("I prefer mornings", True),
    ("on 12 May", True), ("2026-11-02", True), ("see you, Marta", True), ("x" * 40, True),
])
def test_should_capture_reads_length_and_cues(text, expected):
    assert should_capture(text) is expected


async def _memories(cfg, user_id):
    from roost.memory.store import MemoryStore
    return await MemoryStore(cfg).list_scopes(user_id, (await BotStore(cfg).list(user_id))[0].id)


async def _notes(talk, user_id, thread_id):
    return [m for m in await talk.list_messages(user_id, thread_id) if m.kind == "memory_note"]


async def test_a_long_message_is_captured_and_shown(cfg, user_id, bot):
    runner, talk, events, _ = _rig(cfg, Reply(_json(ANA, {"kind": "fact", "text": "Likes orchids"})))
    thread = await talk.create_thread(user_id, bot.id)
    await send(type("R", (), {"talk": talk, "runner": runner})(), user_id, bot.id, thread.id, LONG_MESSAGE)
    await wait_idle(runner)

    assert sorted(m.text for m in await _memories(cfg, user_id)) == ["Ana's birthday is in May", "Likes orchids"]
    assert len(await _notes(talk, user_id, thread.id)) == 2
    frames = [f for f in await events.since(user_id, 0) if f["type"] == "memories_changed"]
    assert len(frames) == 2
    assert (await BotStore(cfg).get(user_id, bot.id)).status.value == "resting"


async def test_saying_it_again_refreshes_and_shows_again(cfg, user_id, bot):
    runner, talk, _, _ = _rig(cfg, Reply(_json(ANA)))
    thread = await talk.create_thread(user_id, bot.id)
    rig = type("R", (), {"talk": talk, "runner": runner})()
    for _ in range(2):
        await send(rig, user_id, bot.id, thread.id, LONG_MESSAGE)
        await wait_idle(runner)
    assert len(await _memories(cfg, user_id)) == 1
    assert len(await _notes(talk, user_id, thread.id)) == 2


@pytest.mark.parametrize("change", [
    {"tainted": True}, {"in_room": True}, {"blocked": True}, {"answered": False},
])
async def test_no_capture_after_a_tainted_run_a_room_or_a_failed_run(cfg, user_id, bot, change):
    worker = RecordingModel(Reply(_json(ANA)))
    _, _, _, hooks = _rig(cfg, worker)
    await hooks.after_run(_run(user_id, bot, **change))
    assert worker.requests == []


@pytest.mark.parametrize("kind", [WorkKind.HANDOFF, WorkKind.ROUTINE, WorkKind.ROOM_POST, WorkKind.CARD_ANSWER])
async def test_no_capture_after_a_handoff_a_routine_or_a_room_post(cfg, user_id, bot, kind):
    worker = RecordingModel(Reply(_json(ANA)))
    _, _, _, hooks = _rig(cfg, worker)
    await hooks.after_run(_run(user_id, bot, kind=kind))
    assert worker.requests == []


async def test_short_small_talk_is_never_sent_to_the_worker(cfg, user_id, bot):
    worker = RecordingModel(Reply(_json(ANA)))
    _, _, _, hooks = _rig(cfg, worker)
    await hooks.after_run(_run(user_id, bot, body="ok thanks"))
    assert worker.requests == []


async def _bot_rows(hooks, user_id, bot, count):
    for n in range(count):
        await hooks.service.save(user_id, MemoryDraft(
            kind="fact", text=f"Fact number {n} here", bot_id=bot.id, source="bot", created_by_bot=bot.id))


async def test_the_hourly_cap_stops_the_worker_call(cfg, user_id, bot):
    worker = RecordingModel(Reply(_json(ANA)))
    _, _, _, hooks = _rig(cfg, worker)
    await _bot_rows(hooks, user_id, bot, MEMORY_CAPTURE_PER_HOUR)
    await hooks.after_run(_run(user_id, bot))
    assert worker.requests == []


async def test_one_slot_left_keeps_at_most_one_item(cfg, user_id, bot):
    worker = Reply(_json(ANA, {"kind": "fact", "text": "Likes orchids"}))
    _, _, _, hooks = _rig(cfg, worker)
    await _bot_rows(hooks, user_id, bot, MEMORY_CAPTURE_PER_HOUR - 1)
    await hooks.after_run(_run(user_id, bot))
    assert len(worker.requests) == 1
    assert await hooks.service.bot_saved_last_hour(user_id) == MEMORY_CAPTURE_PER_HOUR


@pytest.mark.parametrize("reply", [
    "not json at all",
    _json(*({"kind": "fact", "text": f"Fact {n} is good"} for n in range(10))),
    _json({"kind": "weird", "text": "Unknown kind"}),
    _json({"kind": "lesson", "text": "A lesson"}),
    _json({"kind": "fact", "text": "The password is hunter22 ok"}),
    _json({"kind": "fact", "text": "x" * 600}),
])
async def test_a_hostile_capture_reply_saves_nothing_bad(cfg, user_id, bot, reply):
    _, _, _, hooks = _rig(cfg, Reply(reply))
    await hooks.after_run(_run(user_id, bot))
    saved = await _memories(cfg, user_id)
    assert len(saved) <= MEMORY_CAPTURE_MAX_ITEMS
    assert all(m.kind != "lesson" and "hunter22" not in m.text and len(m.text) <= 500 for m in saved)
    if reply.startswith("not json") or "weird" in reply or "lesson" in reply or "password" in reply or "xxx" in reply:
        assert saved == ()


def test_a_reply_in_a_fence_is_read_and_junk_is_nothing():
    fenced = "```json\n" + _json(ANA) + "\n```"
    assert [i.kind for i in parse_capture_reply(fenced)] == ["about_you"]
    assert parse_capture_reply("{") == ()
    assert parse_capture_reply('{"items": "no"}') == ()


async def test_capture_fades_old_minor_memories_first(cfg, user_id, bot):
    _, _, _, hooks = _rig(cfg, Reply(_json()))
    await hooks.service.save(user_id, MemoryDraft(kind="fact", text="Minor old thing", bot_id=bot.id,
                                                  source="bot", created_by_bot=bot.id, importance=1))
    async with db_session(cfg) as db:
        await db.execute("UPDATE memories SET updated_at = '2020-01-01T00:00:00+00:00'")
        await db.commit()
    await hooks.after_run(_run(user_id, bot))
    assert await _memories(cfg, user_id) == ()


async def test_a_failing_worker_is_logged_by_ids_only_and_the_run_is_fine(cfg, user_id, bot, caplog):
    class Boom:
        async def stream(self, request):
            raise RuntimeError(f"secret user text: {request.turns[0].text}")
            yield  # pragma: no cover

    runner, talk, _, _ = _rig(cfg, Boom())
    thread = await talk.create_thread(user_id, bot.id)
    with caplog.at_level(logging.WARNING):
        await send(type("R", (), {"talk": talk, "runner": runner})(), user_id, bot.id, thread.id, LONG_MESSAGE)
        await wait_idle(runner)
    records = [r for r in caplog.records if "Memory capture failed" in r.getMessage()]
    assert len(records) == 1
    message = records[0].getMessage()
    assert user_id in message and bot.id in message and thread.id in message and "RuntimeError" in message
    assert "orchids" not in message and records[0].exc_info is None
    assert [m.role for m in await talk.list_messages(user_id, thread.id)].count("bot") == 1
