"""A call's run (contract F): the voice section replaces the chat-feel rules only in a spoken run of the user's own
message outside a room, the call model is Haiku unless the bot has a pickable model of its own, and the time line
holds no seconds so the prompt's prefix stays the same within a run."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from roost.bots.models import Avatar, Bot, BotStatus
from roost.llm.registry import CALL_MODEL, DEFAULT_BOT_MODEL, HAIKU, OPUS, resolve_call_model
from roost.rooms.models import RoomContext, RoomMember
from roost.talk.chat_feel import DONE_RULE, FIRST_LINE_RULE, LENGTH_RULE, LINK_RULE, time_rule
from roost.talk.instructions import build_instructions
from roost.voice.prompt import voice_section

_BOT = Bot(
    id="bot-1", user_id="user-1", name="Scout", job="read the news", instructions="",
    avatar=Avatar("round", "#22c55e", "none"), template_id=None, status=BotStatus.RESTING, model_override=None,
    created_at="2026-10-13T00:00:00+00:00", updated_at="2026-10-13T00:00:00+00:00",
)


def test_the_voice_section_says_how_to_talk():
    text = voice_section()
    for words in ("voice call", "one to three short spoken sentences", "no lists", "name a site",
                  "(Madrid time) with no place name", "first say in one short sentence what you are doing"):
        assert words in text, words


def test_a_spoken_run_swaps_the_chat_rules_for_the_voice_section():
    spoken = build_instructions(_BOT, spoken=True)
    assert voice_section() in spoken
    assert DONE_RULE in spoken and time_rule() in spoken
    for rule in (FIRST_LINE_RULE, LENGTH_RULE, LINK_RULE):
        assert rule not in spoken
    assert "link it" not in spoken


def test_a_typed_run_keeps_the_chat_rules_and_no_voice_section():
    typed = build_instructions(_BOT)
    assert voice_section() not in typed
    assert FIRST_LINE_RULE in typed and LINK_RULE in typed


def test_a_room_never_gets_the_voice_section_even_when_asked():
    room = RoomContext(room_id="r1", name="Desk", members=(RoomMember("bot-1", "Scout", "news"),), coordinator_id=None)
    assert voice_section() not in build_instructions(_BOT, room=room, spoken=True)


def test_the_call_model_is_haiku_unless_the_bot_picked_one():
    assert CALL_MODEL == HAIKU.id
    assert resolve_call_model(None) == CALL_MODEL
    assert resolve_call_model(OPUS.id) == OPUS.id
    assert resolve_call_model("claude-nope-9") == CALL_MODEL
    assert resolve_call_model("claude-new-9", frozenset({"claude-new-9"})) == "claude-new-9"
    assert DEFAULT_BOT_MODEL != CALL_MODEL   # a typed run keeps its own default


def test_the_time_line_has_no_seconds():
    fixed = datetime(2026, 7, 1, 10, 0, 37, 123456, tzinfo=ZoneInfo("UTC"))
    prompt = build_instructions(_BOT, now=fixed)
    assert "12:00:00+02:00" in prompt and "12:00:37" not in prompt
