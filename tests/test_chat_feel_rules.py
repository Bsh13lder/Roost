"""The chat-feel prompt rules reach every run's instructions (plan Task 1)."""

from __future__ import annotations

from roost.bots.models import Avatar, Bot, BotStatus
from roost.rooms.models import RoomContext, RoomMember
from roost.talk.chat_feel import DONE_RULE, FIRST_LINE_RULE, LENGTH_RULE, LINK_RULE, chat_feel_section, time_rule
from roost.talk.instructions import Teammate, build_instructions

_BOT = Bot(
    id="bot-1", user_id="user-1", name="Scout", job="read the news", instructions="",
    avatar=Avatar("round", "#22c55e", "none"), template_id=None, status=BotStatus.RESTING, model_override=None,
    created_at="2026-10-13T00:00:00+00:00", updated_at="2026-10-13T00:00:00+00:00",
)
_RULES = (FIRST_LINE_RULE, LENGTH_RULE, DONE_RULE, time_rule(), LINK_RULE)


def test_every_run_gets_the_chat_feel_rules():
    room = RoomContext(room_id="r1", name="Desk", members=(RoomMember("bot-1", "Scout", "news"),), coordinator_id=None)
    runs = (
        build_instructions(_BOT, origins=("your message",)),
        build_instructions(_BOT, origins=("a handoff from Chief",), teammates=(Teammate("Chief", "lead", False),)),
        build_instructions(_BOT, room=room),
    )
    for prompt in runs:
        for rule in _RULES:
            assert rule in prompt
    assert all(rule in chat_feel_section() for rule in _RULES)


def test_the_answer_style_no_longer_asks_for_raw_urls():
    prompt = build_instructions(_BOT)
    assert "cite the page URL" not in prompt
    assert "Name the page you read" not in prompt   # owner, 2026-11-04: no "I read the … page" sentences
    assert "Answer first" in prompt


def test_replies_are_told_to_stay_short():
    """Owner, 2026-10-25: replies were far too long for a chat."""
    assert "short" in LENGTH_RULE and "unless" in LENGTH_RULE
