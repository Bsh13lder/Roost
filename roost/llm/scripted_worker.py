"""The deterministic worker for tests and scripted runs: no network, no tokens.

It answers memory capture and chat summaries from simple text rules, so a
scripted run never consumes a bot's brain script.
"""

from __future__ import annotations

import html
import json
import re
from typing import AsyncIterator

from roost.auto_review.constants import AUTO_REVIEW_AGENT
from roost.constants import MEMORY_CAPTURE_MAX_ITEMS
from roost.create_check.constants import CREATE_CHECK_AGENT
from roost.lessons.constants import LESSON_AGENT
from roost.llm.scripted import SCRIPTED_USAGE
from roost.llm.types import ModelEvent, ModelRequest, TextDelta, TurnDone
from roost.memory.worker import CAPTURE_AGENT, SUMMARY_AGENT
from roost.owner_words.constants import OWNER_CHECK_AGENT
from roost.standing.constants import STANDING_CHECK_AGENT
from roost.voice.constants import VOICE_CORRECT_AGENT

_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_REMEMBER = re.compile(r"^(?:please\s+)?remember(?:\s+that)?\s+(.+)$", re.IGNORECASE)
_PREFER = re.compile(r"^i prefer\s+(.+)$", re.IGNORECASE)
_BLOCK = re.compile(r"<user_messages>\n?(.*?)\n?</user_messages>", re.DOTALL)
_CHAT = re.compile(r"<chat>\n?(.*?)\n?</chat>", re.DOTALL)
_END = ".!?"
_TAG = r"<{0}>(.*?)</{0}>"


def _clean(text: str) -> str:
    return text.strip().rstrip(_END).strip()


def _capture_items(text: str) -> list[dict[str, object]]:
    match = _BLOCK.search(text)
    body = html.unescape(match.group(1)) if match else ""
    items: list[dict[str, object]] = []
    for sentence in _SPLIT.split(body):
        sentence = sentence.strip()
        if remember := _REMEMBER.match(sentence):
            said = _clean(remember.group(1))
            if said:
                items.append({"kind": "about_you", "text": said[0].upper() + said[1:], "importance": 5})
        elif prefer := _PREFER.match(sentence):
            said = _clean(prefer.group(1))
            if said:
                items.append({"kind": "preference", "text": "Prefers " + said, "importance": 3})
    return items[:MEMORY_CAPTURE_MAX_ITEMS]


def _summary(text: str) -> str:
    match = _CHAT.search(text)
    lines = (match.group(1) if match else "").splitlines()
    return f"A summary of the earlier chat ({sum(1 for line in lines if line.startswith('['))} lines)."


def _tag(text: str, name: str) -> str:
    match = re.search(_TAG.format(name), text, re.DOTALL)
    return html.unescape(match.group(1)) if match else ""


def _standing_check(text: str) -> str:
    """The model check's rule here: ``fits`` only when the routine's instructions name the act's host."""
    host = _tag(text, "host").strip().casefold()
    return "fits" if host and host in _tag(text, "instructions").casefold() else "ask"


_WORD = re.compile(r"[a-z0-9]{3,}")


def _owner_words_check(text: str) -> str:
    """W2's rule here: typing fits when your words hold every word of the typed text; a click or key fits when your
    words name one of the control's words."""
    words = set(_WORD.findall(_tag(text, "owner_words").casefold()))
    if "<typed>" in text:
        typed = set(_WORD.findall(_tag(text, "typed").casefold()))
        return "fits" if typed and typed <= words else "ask"
    return "fits" if words & set(_WORD.findall(_tag(text, "button").casefold())) else "ask"


def _auto_review_check(text: str) -> str:
    """Full auto's rule here: a button is safe when your request names one of the control's words."""
    request = set(_WORD.findall(_tag(text, "owner_request").casefold()))
    control = set(_WORD.findall(f"{_tag(text, 'label')} {_tag(text, 'visible_text')}".casefold()))
    return "safe" if request & control else "ask"


def _create_check(text: str) -> str:
    """The create check's rule here: a bot fits when your words name a word of its name or job."""
    words = set(_WORD.findall(_tag(text, "owner_words").casefold()))
    bot = set(_WORD.findall(f"{_tag(text, 'name')} {_tag(text, 'job')}".casefold()))
    return "fits" if words & bot else "ask"


# Correct my English's rule here: a few fixed mistakes are corrected, word by word; anything else is fine as said.
_ENGLISH_FIXES: tuple[tuple[str, str], ...] = (
    ("i has goed", "I went"), ("i has", "I have"), ("goed", "went"), ("more better", "better"), ("dont", "don't"),
    ("teh", "the"),
    # Voice tuning D3: a misheard site, a misheard name and a spoken number (the real worker reads <known_names>).
    ("what's up", "WhatsApp"), ("whats app", "WhatsApp"), ("maka eremadse", "Maka Eremadze"),
    ("thirty six euros", "36 €"), ("twenty euros", "20 €"),
)


def _known_name_fixes(text: str) -> tuple[tuple[str, str], ...]:
    """A known name said with the wrong case ("upwork") is fixed to the name as given ("Upwork")."""
    names = [line.strip() for line in _tag(text, "known_names").splitlines() if line.strip()]
    return tuple((name, name) for name in names)


def _english_correction(text: str) -> str:
    said = _tag(text, "said").strip()
    corrected, fixes = said, []
    for wrong, right in (*_ENGLISH_FIXES, *_known_name_fixes(text)):
        pattern = re.compile(rf"\b{re.escape(wrong)}\b", re.IGNORECASE)
        found = pattern.search(corrected)
        if found is not None and found.group(0) != right:
            corrected = pattern.sub(right, corrected)
            fixes.append({"wrong": found.group(0), "right": right})
    return json.dumps({"corrected": corrected, "fixes": fixes})


# Lessons' rule here: a fixed create lesson when an act left the page as it was, else none.
_LESSON = {"action": "create", "name": "When a click changes nothing",
           "use_when": "a click on a site leaves the page as it was",
           "steps": ["Look at the page again before the next click",
                     "Do not press the same button a third time; read the page's text or ask the user"]}


def _lesson(text: str) -> str:
    return json.dumps({"lesson": _LESSON if "expect_missed" in _tag(text, "signals") else None})


class ScriptedWorker:
    """A ``Model`` that answers the memory agents, the standing check, the owner words check, the auto-review
    check and the English correction by fixed rules."""

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        text = request.turns[-1].text if request.turns else ""
        if request.agent == CAPTURE_AGENT:
            yield TextDelta(json.dumps({"items": _capture_items(text)}))
        elif request.agent == SUMMARY_AGENT:
            yield TextDelta(_summary(text))
        elif request.agent == STANDING_CHECK_AGENT:
            yield TextDelta(_standing_check(text))
        elif request.agent == OWNER_CHECK_AGENT:
            yield TextDelta(_owner_words_check(text))
        elif request.agent == AUTO_REVIEW_AGENT:
            yield TextDelta(_auto_review_check(text))
        elif request.agent == CREATE_CHECK_AGENT:
            yield TextDelta(_create_check(text))
        elif request.agent == VOICE_CORRECT_AGENT:
            yield TextDelta(_english_correction(text))
        elif request.agent == LESSON_AGENT:
            yield TextDelta(_lesson(text))
        yield TurnDone("end_turn", SCRIPTED_USAGE)
