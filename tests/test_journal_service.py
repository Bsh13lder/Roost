"""The Bot Journal's store and service: one sealed day per bot, appends, search, ownership."""

from __future__ import annotations

import asyncio
from datetime import date, datetime

import pytest

from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.journal.service import FULL_DAY_TEXT, NO_BOT_TEXT, JournalService
from roost.journal.store import JournalStore
from tz_helpers import MADRID_TZ
from team_helpers import make_bot

NOW = datetime(2026, 10, 22, 14, 19, tzinfo=MADRID_TZ)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _service(cfg, now=NOW):
    return JournalService(JournalStore(cfg), EventHub(cfg), clock=lambda: now)


async def test_the_first_entry_makes_the_day_and_later_ones_add_lines(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Ana")
    service = _service(cfg)
    first = await service.append(user_id, bot.id, bot.name, "Added a task")
    second = await service.append(user_id, bot.id, bot.name, "Wrote the report", tainted=True)
    assert (first.revision, second.revision, second.tainted) == (1, 2, True)
    assert second.content.endswith("- 14:19 Added a task\n- 14:19 Wrote the report\n")
    assert "# Ana · 2026-10-22" in second.content
    assert (await service.read(user_id, bot.id, date(2026, 10, 22))).content == second.content


async def test_the_content_is_sealed_at_rest(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Ana")
    await _service(cfg).append(user_id, bot.id, bot.name, "secret plan")
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT content FROM bot_journals")).fetchone()
    assert row[0].startswith("enc:v2:") and "secret" not in row[0]


async def test_a_new_day_starts_a_new_note(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Ana")
    await _service(cfg).append(user_id, bot.id, bot.name, "one")
    await _service(cfg, datetime(2026, 10, 23, 8, 0, tzinfo=MADRID_TZ)).append(user_id, bot.id, bot.name, "two")
    days = await _service(cfg).recent(user_id, bot.id)
    assert [d.day.isoformat() for d in days] == ["2026-10-23", "2026-10-22"]


async def test_concurrent_appends_keep_every_line(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Ana")
    service = _service(cfg)
    await asyncio.gather(*(service.append(user_id, bot.id, bot.name, f"entry {n}") for n in range(3)))
    day = await service.read(user_id, bot.id, NOW.date())
    assert sorted(line[-7:] for line in day.content.splitlines() if line.startswith("- ")) == [
        "entry 0", "entry 1", "entry 2"]


async def test_a_full_day_refuses_more(cfg, user_id, monkeypatch):
    bot = await make_bot(cfg, user_id, "Ana")
    monkeypatch.setattr("roost.journal.service.JOURNAL_DAY_MAX_CHARS", 200)
    service = _service(cfg)
    await service.append(user_id, bot.id, bot.name, "x" * 20)
    with pytest.raises(ValueError, match=FULL_DAY_TEXT):
        await service.append(user_id, bot.id, bot.name, "y" * 150)


async def test_another_users_bot_gets_no_journal(cfg, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bobs_bot = await make_bot(cfg, bob, "Bobbot")
    with pytest.raises(ValueError, match=NO_BOT_TEXT):
        await _service(cfg).append(user_id, bobs_bot.id, "x", "sneaky")
    assert await _service(cfg).recent(bob, bobs_bot.id) == ()
    await _service(cfg).append(bob, bobs_bot.id, bobs_bot.name, "mine")
    assert await _service(cfg).read(user_id, bobs_bot.id, NOW.date()) is None


async def test_search_finds_days_by_every_word_newest_first(cfg, user_id):
    ana, joe = await make_bot(cfg, user_id, "Ana"), await make_bot(cfg, user_id, "Joe")
    await _service(cfg).append(user_id, ana.id, ana.name, "Paid the café bill")
    await _service(cfg, datetime(2026, 10, 23, 9, 0, tzinfo=MADRID_TZ)).append(user_id, joe.id, joe.name, "bill sent")
    hits = await _service(cfg).search(user_id, "bill")
    assert [(h.bot_id, h.day.isoformat()) for h in hits] == [(joe.id, "2026-10-23"), (ana.id, "2026-10-22")]
    assert [h.lines for h in await _service(cfg).search(user_id, "cafe bill")] == [("- 14:19 Paid the café bill",)]
    assert await _service(cfg).search(user_id, "bill", bot_id=ana.id) != ()
    assert await _service(cfg).search(user_id, "  ") == ()


async def test_an_append_publishes_the_bot_and_day_only(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Ana")
    events = EventHub(cfg)
    await JournalService(JournalStore(cfg), events, clock=lambda: NOW).append(user_id, bot.id, bot.name, "secret")
    [frame] = [e for e in await events.since(user_id, 0) if e["type"] == "journal_changed"]
    assert {k: frame[k] for k in ("bot_id", "day")} == {"bot_id": bot.id, "day": "2026-10-22"}
    assert "secret" not in str(frame)
