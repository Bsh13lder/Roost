"""A Report's body names its bot (mobile SERVER_NEEDS M4): ``bot_id`` is set by ``post_report`` from the bot it
posts for, whatever the body said, and an older body without it still reads."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.routines.models import ReportBody
from roost.routines.reports import post_report
from roost.routines.runs import RoutineRunStore
from roost.talk.store import TalkStore
from team_helpers import make_bot

NOW = datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def test_a_posted_report_carries_its_bot_id(cfg):
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Scout")
    body = ReportBody(source="routine", headline="Morning news", text="Three stories.", routine_id="r1")

    message = await post_report(TalkStore(cfg), EventHub(cfg), user.id, bot.id, body,
                                runs=RoutineRunStore(cfg), now=NOW)

    stored = json.loads(message.body)
    assert stored["bot_id"] == bot.id and stored["routine_id"] == "r1" and stored["headline"] == "Morning news"


async def test_the_bot_posting_wins_over_a_body_that_names_another(cfg):
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Scout")
    body = ReportBody(source="routine", headline="Hi", text="Hi.", bot_id="someone-else")
    message = await post_report(TalkStore(cfg), EventHub(cfg), user.id, bot.id, body,
                                runs=RoutineRunStore(cfg), now=NOW, always=True)
    assert json.loads(message.body)["bot_id"] == bot.id


def test_an_older_report_body_without_a_bot_id_still_reads():
    old = ReportBody.model_validate_json('{"source": "routine", "headline": "Old", "text": "Old one."}')
    assert old.bot_id is None
