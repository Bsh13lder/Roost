"""The install's one time zone (owner, 2026-11-09, docs/plans/2026-11-09-roost-time-zone.md): the account's own,
else ``ROOST_TIMEZONE``, else UTC; read at use time, never captured at import."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import aiosqlite
import pytest

from roost.bots.models import Avatar, Bot, BotStatus
from roost.config import load_config
from roost.db.connection import close_pool, get_db_path, init_db
from roost.db.migrations import apply_migrations
from roost.gateway.auth import register_user
from roost.talk.instructions import build_instructions
from roost.tasks.models import Task
from roost.tasks.views import madrid_today, pick
from roost.timezones import (
    TIMEZONE_ENV, is_zone_name, load_local_tz, local_tz, local_tz_name, save_account_timezone, set_local_tz, zone_city,
)

_BOT = Bot(
    id="bot-1", user_id="user-1", name="Gela", job="books trips", instructions="",
    avatar=Avatar("round", "#22c55e", "none"), template_id=None, status=BotStatus.RESTING, model_override=None,
    created_at="2026-10-13T00:00:00+00:00", updated_at="2026-10-13T00:00:00+00:00", computer="mac_brave",
)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


def test_tests_run_on_madrid_by_default():
    assert local_tz_name() == "Europe/Madrid"
    assert local_tz() == ZoneInfo("Europe/Madrid")


def test_env_is_read_when_no_account_zone(monkeypatch):
    monkeypatch.setenv(TIMEZONE_ENV, "Asia/Tokyo")
    assert local_tz_name() == "Asia/Tokyo"


def test_utc_when_neither_is_set(monkeypatch):
    monkeypatch.delenv(TIMEZONE_ENV, raising=False)
    assert local_tz_name() == "UTC"


def test_a_bad_env_name_falls_back_to_utc(monkeypatch):
    monkeypatch.setenv(TIMEZONE_ENV, "Mars/Olympus")
    assert local_tz_name() == "UTC"


def test_the_account_zone_beats_the_env(monkeypatch):
    monkeypatch.setenv(TIMEZONE_ENV, "Asia/Tokyo")
    set_local_tz("America/New_York")
    assert local_tz_name() == "America/New_York"
    set_local_tz(None)
    assert local_tz_name() == "Asia/Tokyo"


@pytest.mark.parametrize("name", ["localtime", "Mars/Olympus", "", "../etc/passwd", "x" * 65, "Europe/Madrid "])
def test_bad_names_are_refused(name):
    assert not is_zone_name(name)
    with pytest.raises(ValueError):
        set_local_tz(name)


@pytest.mark.parametrize("name,city", [
    ("Europe/Madrid", "Madrid"), ("America/New_York", "New York"), ("UTC", "UTC"),
    ("America/Argentina/Buenos_Aires", "Buenos Aires"),
])
def test_zone_city(name, city):
    assert zone_city(name) == city


def test_zone_city_defaults_to_the_effective_zone():
    set_local_tz("America/New_York")
    assert zone_city() == "New York"


async def test_load_reads_the_account_zone_from_the_db(cfg, monkeypatch):
    monkeypatch.setenv(TIMEZONE_ENV, "Asia/Tokyo")
    user = await register_user(cfg, "me", "pw-123456")
    assert await load_local_tz(cfg) == "Asia/Tokyo"          # a new account has none yet
    await save_account_timezone(cfg, user.id, "America/New_York")
    set_local_tz(None)
    assert await load_local_tz(cfg) == "America/New_York"
    assert local_tz_name() == "America/New_York"


async def test_new_accounts_start_with_no_zone(cfg):
    await register_user(cfg, "me", "pw-123456")
    with sqlite3.connect(get_db_path(cfg)) as raw:
        assert raw.execute("PRAGMA user_version").fetchone()[0] >= 45
        assert raw.execute("SELECT timezone FROM users").fetchone()[0] is None


async def test_migration_keeps_madrid_for_an_existing_account(cfg):
    await register_user(cfg, "me", "pw-123456")
    with sqlite3.connect(get_db_path(cfg)) as raw:     # back to v44, as the owner's install was
        raw.execute("ALTER TABLE users DROP COLUMN timezone")
        raw.execute("PRAGMA user_version = 44")
    await close_pool()
    async with aiosqlite.connect(get_db_path(cfg)) as db:
        assert await apply_migrations(db) >= 45
        row = await (await db.execute("SELECT timezone FROM users")).fetchone()
    assert row[0] == "Europe/Madrid"


def test_the_instructions_name_the_zone():
    now = datetime(2026, 11, 9, 13, 0, tzinfo=timezone.utc)
    assert "2026-11-09T14:00:00+01:00 (Europe/Madrid)" in build_instructions(_BOT, now=now)
    set_local_tz("America/New_York")
    prompt = build_instructions(_BOT, now=now)
    assert "2026-11-09T08:00:00-05:00 (America/New_York)" in prompt
    assert "Madrid" not in prompt


def _task(title: str, due: str) -> Task:
    return Task(
        id=title, user_id="u", title=title, description=None, category=None, priority="medium",
        status="todo", owner="user", due_date=due, reminder_at=None, pre_reminders=(), recurring=None,
        recur_until=None, tags=(), steps=(), created_at="2026-11-01T08:00:00+00:00",
        updated_at="2026-11-01T08:00:00+00:00", completed_at=None, created_by_bot=None, tainted=False,
    )


def test_today_and_overdue_follow_the_zone():
    late_evening_new_york = datetime(2026, 11, 10, 3, 0, tzinfo=timezone.utc)   # 22:00 on 9 Nov in New York
    tasks = [_task("ninth", "2026-11-09"), _task("tenth", "2026-11-10")]
    madrid_day = madrid_today(late_evening_new_york)
    assert [t.title for t in pick(tasks, "overdue", today=madrid_day)] == ["ninth"]
    set_local_tz("America/New_York")
    new_york_day = madrid_today(late_evening_new_york)
    assert new_york_day.isoformat() == "2026-11-09"
    assert [t.title for t in pick(tasks, "today", today=new_york_day)] == ["ninth"]
    assert pick(tasks, "overdue", today=new_york_day) == ()
