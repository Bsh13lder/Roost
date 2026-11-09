"""``set_my_voice``'s tool spec, apart from its handler so the tool catalog imports no service (§4).

The gate's ``own_settings`` flag says what it is: a change to the calling bot's own settings only. It runs with no
card in a run the user's own message started in their 1:1 chat that has read no outside content (a clean run, or a
site-fresh one); anywhere else it parks on an ordinary Ask card (``roost/talk/gate.py``)."""

from __future__ import annotations

from roost.llm.types import ToolSpec
from roost.talk.tool_def import ToolDef
from roost.voice.constants import (
    SET_MY_VOICE_TOOL, SPEAKERS, SPEEDS, TONES, VOICE_LANGUAGE_AUTO, VOICE_LANGUAGES,
)

SET_MY_VOICE = SET_MY_VOICE_TOOL

SET_MY_VOICE_SPEC = ToolSpec(
    name=SET_MY_VOICE,
    description=(
        "Change your own voice settings when the user asks: your voice, your tone, how fast you speak, whether "
        "your replies are read aloud, whether their spoken words are corrected (Correct what I say) and the language "
        "they speak to you (auto, or a code from the list). Send only "
        "the fields to change (at least one). Only your own settings, never another bot's. In the user's own chat "
        "it just happens; anywhere else the user sees an Ask card first. Confirm in "
        "one short sentence."
    ),
    input_schema={"type": "object", "properties": {
        "speaker": {"type": "string", "enum": [s.id for s in SPEAKERS], "description": "Your voice."},
        "tone": {"type": "string", "enum": list(TONES), "description": "Your tone."},
        "speed": {"type": "number", "enum": list(SPEEDS),
                  "description": "How fast you speak (1.0 is normal; smaller is slower, larger is faster)."},
        "read_aloud": {"type": "boolean", "description": "Read your replies aloud when the chat is open."},
        "correct_speech": {"type": "boolean",
                           "description": "Show the user a corrected copy of what they say (any language), with "
                                          "their mistakes marked."},
        "language": {"type": "string", "enum": [VOICE_LANGUAGE_AUTO, *(lang.id for lang in VOICE_LANGUAGES)],
                     "description": "The language the user speaks to you: auto (detect it), or a code such as en "
                                    "or es."},
    }},
)

VOICE_TOOL_DEFS: tuple[ToolDef, ...] = (ToolDef(SET_MY_VOICE_SPEC, "write_change", own_settings=True),)
