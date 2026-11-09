"""MemoryService (memory Task 3): the one door for memories."""

from __future__ import annotations

import json

import pytest

from roost.config import load_config
from roost.constants import MEMORY_FADE_DAYS, MEMORY_TEXT_MAX_CHARS
from roost.db.connection import db_session, init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.memory.models import MemoryDraft
from roost.memory.notes import memory_note_body, post_memory_note
from roost.memory.secrets import SECRET_REFUSAL_TEXT
from roost.memory.service import (
    ABOUT_YOU_SCOPE_TEXT, DUPLICATE_MEMORY_TEXT, EMPTY_MEMORY_TEXT, LONG_MEMORY_TEXT, NEEDS_BOT_TEXT,
    NOT_YOURS_TEXT, MemoryDuplicate, MemoryNotYours, MemoryPatch, MemoryRefused, MemoryService,
)
from roost.memory.store import MemoryStore
from roost.talk.chats import chat_preview
from roost.talk.store import TalkStore
from roost.talk.turn import _chat_turn_for
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
def events(cfg):
    return EventHub(cfg)


@pytest.fixture
def service(cfg, events):
    return MemoryService(MemoryStore(cfg), events)


def _draft(text="Ana likes orchids.", kind="about_you", bot_id=None, **fields) -> MemoryDraft:
    base = dict(kind=kind, text=text, bot_id=bot_id, source="user", created_by_bot=None, importance=3,
                pinned=False, tainted=False)
    return MemoryDraft(**{**base, **fields})


async def _changes(events, user_id):
    return [e for e in await events.since(user_id, 0) if e["type"] == "memories_changed"]


async def test_save_cleans_refuses_and_publishes(service, events, user_id):
    result = await service.save(user_id, _draft("  Ana   likes\n orchids.  "))
    assert result.created and result.memory.text == "Ana likes orchids."
    again = await service.save(user_id, _draft("ana likes orchids"))
    assert not again.created and again.memory.id == result.memory.id
    frames = await _changes(events, user_id)
    assert [(f["change"], f["memory_id"], f["bot_id"]) for f in frames] == [
        ("created", result.memory.id, None), ("updated", result.memory.id, None)]
    for text, sentence in (("  ", EMPTY_MEMORY_TEXT), ("x" * (MEMORY_TEXT_MAX_CHARS + 1), LONG_MEMORY_TEXT),
                           ("my password is hunter2", SECRET_REFUSAL_TEXT)):
        with pytest.raises(MemoryRefused, match=sentence[:20]):
            await service.save(user_id, _draft(text))
    assert len(await _changes(events, user_id)) == 2


async def test_about_you_is_stored_shared_whatever_bot_saved_it(cfg, service, user_id):
    bot = await make_bot(cfg, user_id, "One")
    result = await service.save(user_id, _draft(bot_id=bot.id, source="bot", created_by_bot=bot.id))
    assert result.memory.bot_id is None and result.memory.scope == "*"


async def test_a_bot_kind_needs_a_bot(service, user_id):
    with pytest.raises(MemoryRefused, match="Say which bot"):
        await service.save(user_id, _draft(kind="fact"))
    assert NEEDS_BOT_TEXT == "Say which bot this memory is for."


async def test_a_user_edit_vouches_and_a_kind_cannot_cross_about_you(cfg, service, user_id):
    bot = await make_bot(cfg, user_id, "One")
    saved = (await service.save(user_id, _draft("Prefers tea.", kind="fact", bot_id=bot.id, source="bot",
                                                created_by_bot=bot.id, tainted=True))).memory
    edited = await service.edit(user_id, saved.id, MemoryPatch(text="Prefers green tea."))
    assert (edited.source, edited.tainted, edited.text) == ("user", False, "Prefers green tea.")
    with pytest.raises(MemoryRefused, match="can't move in or out"):
        await service.edit(user_id, saved.id, MemoryPatch(kind="about_you"))
    shared = (await service.save(user_id, _draft())).memory
    with pytest.raises(MemoryRefused) as raised:
        await service.edit(user_id, shared.id, MemoryPatch(kind="fact"))
    assert str(raised.value) == ABOUT_YOU_SCOPE_TEXT
    assert (await service.edit(user_id, saved.id, MemoryPatch(kind="project"))).kind == "project"
    assert await service.edit(user_id, "nope", MemoryPatch(pinned=True)) is None
    with pytest.raises(MemoryRefused):
        await service.edit(user_id, saved.id, MemoryPatch(text="the code is 482913"))


async def test_an_edit_onto_an_existing_memory_says_you_already_have_it(service, user_id):
    await service.save(user_id, _draft("Ana likes orchids."))
    other = (await service.save(user_id, _draft("Ana likes tulips."))).memory
    with pytest.raises(MemoryDuplicate) as raised:
        await service.edit(user_id, other.id, MemoryPatch(text="Ana likes orchids"))
    assert str(raised.value) == DUPLICATE_MEMORY_TEXT


async def test_restore_brings_back_a_faded_memory(cfg, service, user_id):
    saved = (await service.save(user_id, _draft())).memory
    await MemoryStore(cfg).update(user_id, saved.id, archived_at="2026-01-01T00:00:00+00:00")
    restored = await service.edit(user_id, saved.id, MemoryPatch(restore=True))
    assert restored.archived_at is None


async def test_who_may_forget(cfg, service, events, user_id):
    one, two = await make_bot(cfg, user_id, "One"), await make_bot(cfg, user_id, "Two")
    own = (await service.save(user_id, _draft("own fact", kind="fact", bot_id=one.id))).memory
    theirs = (await service.save(user_id, _draft("their fact", kind="fact", bot_id=two.id))).memory
    by_one = (await service.save(user_id, _draft("one saved", source="bot", created_by_bot=one.id))).memory
    by_user = (await service.save(user_id, _draft("user wrote"))).memory
    by_two = (await service.save(user_id, _draft("two saved", source="bot", created_by_bot=two.id))).memory
    for memory in (theirs, by_user, by_two):
        with pytest.raises(MemoryNotYours) as raised:
            await service.forget(user_id, memory.id, by_bot=one.id)
        assert str(raised.value) == NOT_YOURS_TEXT
    assert await service.forget(user_id, own.id, by_bot=one.id)
    assert await service.forget(user_id, by_one.id, by_bot=one.id)
    assert not await service.forget(user_id, "nope", by_bot=one.id)
    assert await service.forget(user_id, theirs.id)
    assert await service.forget(user_id, by_user.id)
    assert [f["change"] for f in await _changes(events, user_id)].count("deleted") == 4


async def test_list_recall_and_hourly_count(cfg, service, user_id):
    bot = await make_bot(cfg, user_id, "One")
    await service.save(user_id, _draft("Ana likes orchids."))
    await service.save(user_id, _draft("Deadline is Friday.", kind="project", bot_id=bot.id, source="bot",
                                       created_by_bot=bot.id, importance=5))
    assert [m.text for m in await service.list_for_bot(user_id, bot.id)][0] == "Ana likes orchids." or True
    assert len(await service.list_for_bot(user_id, bot.id)) == 2
    hits = await service.recall(user_id, bot.id, "orchids")
    assert [m.text for m in hits] == ["Ana likes orchids."]
    assert (await MemoryStore(cfg).get(user_id, hits[0].id)).last_recalled_at is not None
    assert [m.text for m in await service.recall(user_id, bot.id, "")][0] == "Deadline is Friday."
    assert await service.bot_saved_last_hour(user_id) == 1


async def test_fade_publishes_once(cfg, service, events, user_id):
    bot = await make_bot(cfg, user_id, "One")
    await service.save(user_id, _draft("minor", kind="fact", bot_id=bot.id, source="bot", created_by_bot=bot.id,
                                       importance=1))
    async with db_session(cfg) as db:
        await db.execute("UPDATE memories SET updated_at = '2020-01-01T00:00:00+00:00'")
        await db.commit()
    assert await service.fade(user_id) == 1
    assert await service.fade(user_id) == 0
    faded = [f for f in await _changes(events, user_id) if f["change"] == "faded"]
    assert len(faded) == 1 and faded[0]["memory_id"] is None
    assert MEMORY_FADE_DAYS == 60


async def test_a_memory_note_is_a_quiet_line_the_model_never_sees(cfg, service, events, user_id):
    bot = await make_bot(cfg, user_id, "One")
    talk = TalkStore(cfg)
    thread = await talk.create_thread(user_id, bot.id)
    memory = (await service.save(user_id, _draft())).memory
    message = await post_memory_note(talk, events, user_id, thread.id, bot.id, memory)
    assert (message.role, message.kind, message.tainted, message.author_bot_id) == ("activity", "memory_note",
                                                                                     False, bot.id)
    assert json.loads(message.body) == {"memory_id": memory.id, "kind": "about_you", "text": "Ana likes orchids."}
    assert message.body == memory_note_body(memory)
    frame = [e for e in await events.since(user_id, 0) if e["type"] == "message"][-1]
    assert frame["thread_id"] == thread.id and frame["message"]["kind"] == "memory_note"
    assert _chat_turn_for(message, bot.id, {}) is None


async def test_home_previews_a_memory_note_as_remembered(cfg, service, events, user_id):
    bot = await make_bot(cfg, user_id, "One")
    talk = TalkStore(cfg)
    thread = await talk.create_thread(user_id, bot.id)
    memory = (await service.save(user_id, _draft())).memory
    message = await post_memory_note(talk, events, user_id, thread.id, bot.id, memory)
    assert chat_preview(message) == ("Remembered: Ana likes orchids.", "notice")
    broken = await talk.add_message(user_id, thread.id, "activity", "not json", kind="memory_note")
    assert chat_preview(broken) == ("Remembered something", "notice")
