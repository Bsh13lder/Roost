"""What a bot is told in a voice call (docs/plans/2026-10-30-roost-voice.md §3, contract F): the user hears the
reply and does not read it. ``voice_section`` replaces ``chat_feel_section`` in a spoken run of the user's own
message outside a room (``build_instructions(..., spoken=True)``); the done and time rules stay."""

from __future__ import annotations

from roost.timezones import zone_city

VOICE_RULE_TEMPLATE = (
    "You are on a voice call: the user hears you and does not read. Answer in one to three short spoken "
    "sentences in plain words; no lists, headings, links, code or markdown; name a site instead of pasting an "
    "address; say numbers, dates and times the way you would aloud, on the user's own clock ({city} time) with no place name; when you must look something "
    "up, first say in one short sentence what you are doing, then do it."
)

# §4: the user may ask the bot to change its own voice settings; set_my_voice is the way, in a call or in the chat.
VOICE_SETTINGS_RULE = (
    "The user can ask you to speak slower or faster, change your voice or tone, turn reading replies aloud on or "
    "off, turn the correction of what they say on or off, or set the language they speak to you (auto-detect or "
    "one of the listed codes); use set_my_voice for that and confirm in one short sentence."
)


def voice_section() -> str:
    """The voice call rule, one paragraph of the system prompt."""
    return f"{VOICE_RULE_TEMPLATE.format(city=zone_city())} {VOICE_SETTINGS_RULE}"
