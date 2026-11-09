"""Owner, 2026-11-03: bots work longer before a limit stops them. The screen loop's budgets, the run's steps and time,
the daily cap and skill reads are all raised, a missed control is tried up to four times (with a fresh look before
each try), and helper runs no longer count toward the daily cap. No real model."""

from __future__ import annotations

import pytest

from roost import constants
from roost.computer_use import session as loop
from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.talk.store import TalkStore
from roost.work.runs import RunLog
from team_helpers import make_bot


def test_the_limits_are_raised():
    assert (constants.CU_TRIES_PER_TARGET, constants.CU_MAX_ACTS_PER_RUN, constants.CU_MAX_LOOKS_PER_RUN) == (4, 120, 200)
    assert (constants.CU_MAX_MODEL_STEPS, constants.CU_RUN_DEADLINE_S) == (250, 2700)
    assert constants.DAILY_RUN_CAP == 500 and constants.SKILL_READS_PER_RUN_MAX == 20
    assert constants.MAX_STEPS == 100
    assert constants.MAX_RUN_SECONDS >= constants.CU_RUN_DEADLINE_S        # the run outlives its screen budget
    assert constants.WORK_LEASE_SECONDS > constants.MAX_RUN_SECONDS


def test_a_miss_forces_a_fresh_look_and_the_fourth_is_the_last():
    state = loop.LoopState(run_id="r1", looked_at_version=3)
    for attempt in range(1, constants.CU_TRIES_PER_TARGET + 1):
        state, last = loop.after_miss(state, "click:Send")
        assert state.looked_at_version == -1                              # the next try looks first
        assert last is (attempt == constants.CU_TRIES_PER_TARGET)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def test_helper_runs_are_not_counted_toward_the_daily_cap(cfg):
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Scout")
    thread = await TalkStore(cfg).create_thread(user.id, bot.id)
    runs = RunLog(cfg)
    await runs.start(user.id, bot.id, thread.id, "3f2a6c1e-0000-4000-8000-000000000001")
    for number in (1, 2, 3):
        await runs.start(user.id, bot.id, thread.id, f"3f2a6c1e-0000-4000-8000-000000000001-h{number}")
    assert await runs.count_today(user.id, bot.id) == 1


def test_helpers_may_read_pages_and_search_the_web():
    """Owner, 2026-11-03 (item 10): a helper reads a page and searches; it still shares the parent's taint and links."""
    from roost.talk.tools import EVERY_BOT_TOOLS, HELPER_DENIED, helper_tool_names
    names = helper_tool_names(EVERY_BOT_TOOLS)
    assert {"open_page", "read_page", "web_search"} <= names
    assert "read_page" not in HELPER_DENIED and "web_search" not in HELPER_DENIED
