"""The words of the Sign-in card's masked field (B3, owner decision 2026-10-23).

User-facing: the bot's card line, your continue line and the plain refusals of ``POST /api/stuck/{id}/secret``.
None of them ever holds what you typed: only its kind."""

from __future__ import annotations

_KIND_WORDS = {"password": "password", "code": "code"}


def kind_words(kind: str | None) -> str:
    return _KIND_WORDS.get(kind or "", "password")


def secret_line(host: str, kind: str | None, note: str = "") -> str:
    """The bot's line on a field card: what to type, where it goes, and that the bot never sees it."""
    why = " ".join(note.split()).rstrip(".")
    because = f" ({why})" if why else ""
    return (f"Type your {host} {kind_words(kind)} here{because}. It goes straight into the box on my computer; "
            f"I never see it. You can also take control and type it yourself.")


def typed_line(kind: str | None) -> str:
    """Your continue line once it is in the box: the bot clicks Next or Sign in itself."""
    return f"I typed your {kind_words(kind)} into the box. Carry on."


NOT_FIELD_CARD_DETAIL = "This card doesn't ask for a password or a code."
HELD_DETAIL = "You have the computer now: type it on the live screen yourself."
BUSY_DETAIL = "The bot's computer is busy with another job. Try again in a moment."
WRONG_PAGE_DETAIL = "The page on the bot's computer is no longer {host}'s sign-in, so nothing was typed."
NO_BOX_DETAIL = "There's no password or code box on the page any more, so nothing was typed."
MANY_BOXES_DETAIL = "There are several boxes on the page. Take control and type it into the right one."
NOT_TYPED_DETAIL = "The bot's computer didn't take it, so nothing was typed. Try again, or take control."
BAD_VALUE_DETAIL = "Type 1 to {limit} characters."
