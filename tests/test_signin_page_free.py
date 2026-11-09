"""Owner, 2026-11-03: a sign-in page no longer ends the run with a card at once. The page reaches the bot like any
page, with a short sign-in note, so it may click "Continue with Google" or type the email you gave it; the card opens
only from ask_secret_field, request_sign_in, a human check or a code check. A password is never typed (unchanged)."""

from __future__ import annotations

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import PageText
from roost.desk.fake import FakeDesk
from roost.desk.stuck import Block
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested
from roost.bots.status import ActivityBoard
from roost.talk.gate import Gate
from roost.talk.instructions import SIGN_IN_PAGE_NOTE, build_instructions, stuck_result_text
from roost.talk.tool_catalog import CATALOG
from roost.talk.tool_runner import ToolRunner
from team_helpers import make_bot

_URL = "https://shop.example/login"
_LOGIN = PageText(url=_URL, title="Sign in", text="Sign in to continue. Continue with Google. Email.",
                  truncated=False, status=200, password_field=True)
_CODE = PageText(url=_URL, title="Two-step verification", text="Enter the verification code we sent to your phone.",
                 truncated=False, status=200)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def ids(cfg):
    user_id = (await register_user(cfg, "alice", "pw-123456")).id
    return user_id, (await make_bot(cfg, user_id, "Scout")).id


def _runner(cfg, ids, desk: FakeDesk, *, cards: bool) -> ToolRunner:
    user_id, bot_id = ids
    return ToolRunner(user_id=user_id, bot_id=bot_id, desk=desk, gate=Gate(cfg), activity=ActivityBoard(),
                      events=EventHub(cfg), allowed=frozenset(CATALOG), cards=cards)


def _open() -> ToolCallRequested:
    return ToolCallRequested(id="p", name="open_page", arguments={"url": _URL})


@pytest.mark.parametrize("cards", [True, False])
async def test_a_sign_in_page_is_read_with_a_note_and_no_card(cfg, ids, cards):
    desk = FakeDesk(ids[1])
    desk.serve(_URL, _LOGIN)
    runner = _runner(cfg, ids, desk, cards=cards)
    text = await runner.run(_open())
    assert runner.block is None and runner.wall is None
    assert "Continue with Google" in text and SIGN_IN_PAGE_NOTE in text
    assert runner.tainted is True


async def test_a_code_check_still_opens_the_card(cfg, ids):
    desk = FakeDesk(ids[1])
    desk.serve(_URL, _CODE)
    runner = _runner(cfg, ids, desk, cards=True)
    text = await runner.run(_open())
    assert runner.block == Block(reason="code", url=_URL, host="shop.example")
    assert text == stuck_result_text(runner.block)


def test_the_note_never_lets_a_password_be_typed():
    lowered = SIGN_IN_PAGE_NOTE.casefold()
    assert "continue with google" in lowered and "ask_secret_field" in SIGN_IN_PAGE_NOTE
    assert "never type a password" in lowered


def test_the_instructions_no_longer_stop_at_a_sign_in_page():
    from roost.bots.models import Avatar, Bot, BotStatus
    bot = Bot(id="b", user_id="u", name="Scout", job="j", instructions="", avatar=Avatar("round", "#22c55e", "none"),
              template_id=None, status=BotStatus.RESTING, model_override=None, created_at="", updated_at="")
    text = build_instructions(bot)
    assert "a sign-in page or a code check, your tool result says so" not in text
    assert "Did you log in?" not in text
    assert "never pick Haiku" not in text and "Roost checks it against their words" not in text
    from roost.talk.chat_feel import DO_IT_RULE
    assert DO_IT_RULE in text and "Open card (Open or No), so just" not in text
