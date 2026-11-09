"""The usage reading: the reserve, when a bot's full limit is active, and when it ends."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from roost.bots.service import bot_out
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.usage.reading import (
    NoUsageSource, UsageReading, full_limit_active, full_limit_end, in_reserve,
)
from team_helpers import make_bot

UTC = timezone.utc
NOW = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)         # 10:00 in Madrid


async def test_no_usage_source_reads_nothing():
    assert await NoUsageSource().read() is None


def test_the_reserve_is_the_last_ten_percent():
    assert in_reserve(UsageReading(0.10, None)) and in_reserve(UsageReading(0.02, None))
    assert not in_reserve(UsageReading(0.11, None)) and not in_reserve(None)


def test_a_full_limit_needs_a_reading_a_future_end_and_a_bot_that_has_it():
    from roost.bots.models import Avatar, Bot, BotStatus
    bot = Bot(id="b", user_id="u", name="n", job="j", instructions="", avatar=Avatar("round", "#22c55e", "none"),
              template_id=None, status=BotStatus.RESTING, model_override=None, created_at="x", updated_at="x",
              full_limit_until=(NOW + timedelta(hours=2)).isoformat())
    reading = UsageReading(0.5, None)
    assert full_limit_active(bot, reading, NOW)
    assert not full_limit_active(bot, None, NOW)                                   # no reading: off
    assert not full_limit_active(bot, reading, NOW + timedelta(hours=3))           # past the reset
    assert not full_limit_active(replace(bot, full_limit_until=None), reading, NOW)
    assert not full_limit_active(replace(bot, full_limit_until="not a time"), reading, NOW)


def test_it_ends_at_the_reading_reset_else_the_next_madrid_midnight():
    reset = NOW + timedelta(hours=3)
    assert full_limit_end(UsageReading(0.5, reset), NOW) == reset
    assert full_limit_end(UsageReading(0.5, None), NOW) == datetime(2026, 10, 21, 22, 0, tzinfo=UTC)   # 00:00 CEST
    assert full_limit_end(UsageReading(0.5, NOW - timedelta(hours=1)), NOW) == datetime(
        2026, 10, 21, 22, 0, tzinfo=UTC)                                           # a stale reset is ignored


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def test_a_bot_keeps_its_full_limit_end_and_shows_it(cfg):
    user_id = (await register_user(cfg, "alice", "pw-123456")).id
    bot = await make_bot(cfg, user_id, "Scout")
    store = BotStore(cfg)
    assert bot.full_limit_until is None and bot_out(bot, None)["full_limit_until"] is None

    on = await store.set_full_limit(user_id, bot.id, NOW + timedelta(hours=2))
    assert on.full_limit_until == (NOW + timedelta(hours=2)).isoformat()
    assert bot_out(on, None)["full_limit_until"] == on.full_limit_until
    assert (await store.set_full_limit(user_id, bot.id, None)).full_limit_until is None
    assert await store.set_full_limit(user_id, "missing", None) is None
