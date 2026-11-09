"""Reply quotes (docs/plans/2026-10-22-roost-replies.md, part 1).

A message you send may answer one earlier message of the same chat. The server, never the client, makes the quote:
the first ``REPLY_QUOTE_CHARS`` of the quoted message as words (a Report quotes its headline, never its JSON). The
quote keeps the quoted message's taint, and the model reads it escaped, as data, ahead of your own words."""

from __future__ import annotations

import html

from roost.constants import REPLY_QUOTE_CHARS
from roost.routines.models import ReportBody
from roost.stuck.texts import stuck_quote
from roost.talk.notices import preview
from roost.talk.store import Message, ReplyQuote, TalkStore

# Conversation messages only: cards, notes, tapbacks and quiet lines can't be quoted.
REPLY_KINDS = frozenset({"text", "card_answer", "handoff", "report"})
_REPLY_ROLES = frozenset({"user", "bot"})
STUCK_KIND = "stuck"
REPLY_PREFIX = "(replying to: {quote})"
NO_SUCH_REPLY_TEXT = "That message can't be replied to here."


class NoSuchReply(LookupError):
    """The quoted message is not a conversation message of this thread and user (the route's 404)."""


def _words(message: Message) -> str:
    if message.kind != "report":
        return message.body
    try:
        return ReportBody.model_validate_json(message.body).headline
    except ValueError:
        return ""


def quote_for(message: Message) -> ReplyQuote | None:
    """The quote a reply keeps of ``message``, or ``None`` when it is not a conversation message. A Stuck card
    (Reply on the card, roost/stuck/typed_reply.py) is quoted in fixed words, so its quote is never tainted."""
    if message.kind == STUCK_KIND and message.role == "bot":
        text = stuck_quote(message.body)
        return ReplyQuote(message_id=message.id, text=text, tainted=False) if text else None
    if message.kind not in REPLY_KINDS or message.role not in _REPLY_ROLES:
        return None
    text = preview(_words(message), REPLY_QUOTE_CHARS)
    if not text:
        return None
    return ReplyQuote(message_id=message.id, text=text, tainted=message.tainted)


async def resolve_reply(talk: TalkStore, user_id: str, thread_id: str, message_id: str) -> ReplyQuote:
    """The quote of ``message_id`` for a reply in ``thread_id``; ``NoSuchReply`` for another user's message, one in
    another thread, an unknown id or a message that can't be quoted."""
    message = await talk.get_message(user_id, message_id)
    if message is None or message.thread_id != thread_id:
        raise NoSuchReply(message_id)
    quote = quote_for(message)
    if quote is None:
        raise NoSuchReply(message_id)
    return quote


def reply_turn_text(message: Message) -> str:
    """What the model reads for ``message``: its words, after an escaped ``(replying to: …)`` line when it is a
    reply."""
    if not message.reply_quote:
        return message.body
    quote = REPLY_PREFIX.format(quote=html.escape(message.reply_quote, quote=True))
    return f"{quote}\n{message.body}"
