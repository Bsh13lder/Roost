"""The Stuck flow's words (stuck flow §2, R6, R7): what the bot says in its chat,
and the continue line posted for you. They are user-facing and chat-facing, so
they live in one place. The model-facing tool results are in
``roost/talk/instructions.py``."""

from __future__ import annotations

import json
from types import MappingProxyType
from typing import Mapping

from roost.signin.secret_texts import secret_line
from roost.signin.texts import sign_in_line, sign_in_wait_line
from roost.stuck.models import DEFAULT_CLEAR_HOW, ClearHow, StuckCard

REASON_WORDS: Mapping[str, str] = MappingProxyType({
    "challenge": "a check that I'm human",
    "login": "a sign-in page",
    "code": "a code check",
    "refused": "the site refusing me",
    "asked": "something only you can do",
})
GIVE_UP_LINE = "OK, I stopped that task."
_HAND_BACK = " Take control to clear it, then give it back."
_MAIN_BRAVE_HINT = " I think this needs your main Brave."
NEXT_STEP_TAKE_CONTROL = "Take control to clear it."
NEXT_STEP_BLOCKED = "Take control and do it yourself, or tell me another way."
NEXT_STEP_REPORT = "Open its latest Report to see what happened."


def _clause(text: str) -> str:
    """The bot's own words, ready to end with our full stop (never two)."""
    return text.strip().rstrip(".")


def _sentence(text: str) -> str:
    """The bot's own words as a sentence with one closing mark: ``?`` and ``!`` stay as they are
    ("...for me? Take control..."), anything else ends with a full stop."""
    clause = _clause(text)
    return clause if clause.endswith(("?", "!")) else f"{clause}."


def _opening(card: StuckCard) -> str:
    if card.reason == "asked":
        note = _sentence(card.note)
        return f"I need your help on {card.host}: {note}" if card.host else f"I need your help: {note}"
    return f"I'm stuck on {card.host}: {REASON_WORDS[card.reason]}."


def stuck_line(card: StuckCard) -> str:
    if card.sign_in and card.secret_field:
        return secret_line(card.host, card.secret_field, card.note)
    if card.sign_in:
        return sign_in_line(card.host, card.note)
    hint = _MAIN_BRAVE_HINT if card.suggest_main_browser else ""
    return _opening(card) + _HAND_BACK + hint


def blocked_line(host: str, request: str) -> str:
    return f"Blocked: {host} keeps stopping me. I didn't finish: {_sentence(request)} {NEXT_STEP_BLOCKED}"


def already_waiting_line(host: str, request: str) -> str:
    """A run blocked while another of the bot's cards is open: it opens no card of its own,
    so the bot says which card it is waiting on and what it didn't finish."""
    waiting = f"I'm already waiting on you for {host}" if host else "I'm already waiting on you"
    return f"{waiting}, so I stopped here. I didn't finish: {request}"


def continue_text(card: StuckCard, how: ClearHow = DEFAULT_CLEAR_HOW) -> str:
    """The user's line that a ``card_answer`` item carries to the model (R6).

    - No address: the bot's own note is the bot's words, never the user's, so the line is fixed.
    - A step done in the main Brave (R13) keeps its words whichever button was pressed.
    - Try again and Give it back each have their own words."""
    if not card.host:
        return f"I did what you asked. Carry on with: {card.request}"
    if card.main_opened:
        # R13: the step was done in the user's own Brave, so the bot must not read that page again.
        return (f"I did this step in my own browser on {card.host}. Don't read that page again; "
                f"carry on with the rest of: {_sentence(card.request)} If you can't, tell me exactly what's left.")
    if how == "try_again":
        return f"Try again on {card.host}. Read the page again and carry on with: {card.request}"
    return f"I cleared the block on {card.host}. Read the page again and carry on with: {card.request}"


def stuck_activity(host: str) -> str:
    """The short lead of every Stuck line (and a chat-list preview): where it is stuck, or that it needs you."""
    return f"Stuck on {host}" if host else "Needs your help"


def _status_line(host: str, why: str, next_step: str, *, asked: bool = False) -> str:
    lead = stuck_activity(host) if (host or asked) else "Stuck"
    return f"{lead}: {_sentence(why)} {next_step}"


def stuck_status_line(card: StuckCard) -> str:
    """The one line a Stuck bot shows everywhere (its status frame, ``GET /api/bots``, a notification):
    where, why, and the next step. "Stuck on upwork.com: a sign-in page. Take control to clear it.". A Sign-in
    card's bot is waiting, not stuck: "Waiting for you to sign in to accounts.google.com."."""
    if card.sign_in:
        return sign_in_wait_line(card.host)  # a sign-in is waiting on you, never "Stuck"
    asked = card.reason == "asked"
    why = card.note.strip() if asked and card.note.strip() else REASON_WORDS[card.reason]
    return _status_line(card.host, why, NEXT_STEP_TAKE_CONTROL, asked=asked)


def routine_stuck_line(host: str, routine_name: str) -> str:
    """The same line for an unattended routine run (no card: nobody is there to take control)."""
    why = f"{routine_name} didn't finish" if not host else f"{routine_name} met a wall"
    return _status_line(host, why, NEXT_STEP_REPORT)


def stuck_quote(body: str) -> str:
    """A reply quote of a ``kind="stuck"`` message, in fixed words from its host only: "Stuck on shop.example",
    "Waiting for you to sign in to shop.example". The bot's own note never goes in, so the quote carries no taint."""
    try:
        data = json.loads(body)
    except ValueError:
        return ""
    host = data.get("host") if isinstance(data, dict) else None
    host = host if isinstance(host, str) else ""
    if data.get("sign_in") is True:
        return sign_in_wait_line(host).rstrip(".")
    return stuck_activity(host)


def stuck_message_body(card: StuckCard) -> str:
    """The ``kind="stuck"`` message's body: the card as JSON, like the Created card."""
    return json.dumps({
        "card_id": card.id, "bot_id": card.bot_id, "reason": card.reason, "host": card.host,
        "url": card.url, "note": card.note, "suggest_main_browser": card.suggest_main_browser,
        "line": stuck_line(card), "sign_in": card.sign_in, "secret_field": card.secret_field,
    })
