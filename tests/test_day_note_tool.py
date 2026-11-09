"""The add_day_note bot tool (Batch F, G7)."""

from __future__ import annotations

from datetime import datetime

import pytest

from roost.config import load_config
from roost.day_notes.service import DayNoteService
from roost.day_notes.store import DayNoteStore
from roost.day_notes.tools import DayNoteTools
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.talk.domain_tools import RecordContext
from tz_helpers import MADRID_TZ
from roost.talk.tool_catalog import CATALOG
from team_helpers import make_bot

# Wed 21 Oct 01:30 in Madrid is still Tue 20 Oct in UTC.
NOW = datetime(2026, 10, 21, 1, 30, tzinfo=MADRID_TZ)


class Events:
    async def publish(self, user_id, event):
        return 1


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def rig(cfg):
    user = (await register_user(cfg, "alice", "pw-123456")).id
    bot = await make_bot(cfg, user, "Planner")
    store = DayNoteStore(cfg)
    tools = DayNoteTools(DayNoteService(store, Events(), today=lambda: NOW.date()), clock=lambda: NOW)
    return tools, store, user, bot


def _all(user, bot):
    return RecordContext(user_id=user, bot_id=bot.id, tainted=False)


async def _notes(store, user):
    from datetime import date
    return await store.list_range(user, date(2026, 1, 1), date(2027, 12, 31), 50)


def test_add_day_note_is_write_create_in_the_catalog():
    assert CATALOG["add_day_note"].kind == "write_create"


async def test_bot_note_carries_bot_and_taint(rig):
    tools, store, user, bot = rig
    out = await tools.run("add_day_note", {"day": "2026-10-21", "text": "dentist at 5"},
                          RecordContext(user_id=user, bot_id=bot.id, tainted=True))
    [note] = await _notes(store, user)
    assert (note.author_kind, note.bot_id, note.tainted, note.text) == ("bot", bot.id, True, "dentist at 5")
    assert out.created is True and out.text == "Added a note for Wed 21 Oct."
    assert tools.activity("add_day_note") == "adding a day note"


async def test_day_words_are_read_in_madrid(rig):
    tools, store, user, bot = rig
    await tools.run("add_day_note", {"day": "tomorrow", "text": "a"}, _all(user, bot))
    await tools.run("add_day_note", {"day": "viernes", "text": "b"}, _all(user, bot))
    days = {n.text: n.day.isoformat() for n in await _notes(store, user)}
    assert days == {"a": "2026-10-22", "b": "2026-10-23"}      # Madrid's Wednesday 21st, not UTC's Tuesday


async def test_result_is_escaped(rig):
    tools, _, user, bot = rig
    out = await tools.run("add_day_note", {"day": "2026-10-21", "text": "<b>x</b>"}, _all(user, bot))
    assert "<" not in out.text


async def test_bad_arguments_are_a_plain_refusal(rig):
    tools, store, user, bot = rig
    for args in ({}, {"day": "2026-10-21"}, {"day": "no idea when", "text": "x"}, {"day": "2026-10-21", "text": "x" * 501},
                 {"day": "2099-01-01", "text": "x"}):
        out = await tools.run("add_day_note", args, _all(user, bot))
        assert out.text.startswith("Refused:") and out.created is False
    assert await _notes(store, user) == ()
