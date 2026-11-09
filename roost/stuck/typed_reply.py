"""Answer a Stuck card by typing (owner, 2026-11-02: "let me reply messages and that's considered reply on message
how grok does").

While a bot shows a Stuck card (a Sign-in card too), your own message in its chat answers the card: "done, carry on"
or a different task altogether. So does a reply quote of the card's message (Reply on the card), which also reaches
a card shown in another chat. The card closes as ``replied`` (one press wins: a card another press closed first
leaves your message an ordinary turn), any control hold is given back with its teach recording, the ``stuck_card``
frame goes out and the status settles, so the bot no longer shows Stuck. No give-up line is posted.

Your message stays your own: it is queued as an ordinary ``message`` item, never tainted, and the card keeps that
item's id as ``answer_item_id``. Rung 4 reads only ``card_answer`` items, so a block met by this run opens a new card.
The run that claims the item gets one trusted line (``stuck_reply_section``): where it was stuck, why in fixed words,
what it was doing (only from a card no web content touched, escaped) and how to read your answer.

Messages to rooms, routines and handoffs, and a message only for other bots (``@Name …``), never reach here."""

from __future__ import annotations

import html
import json
import logging
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Mapping, Protocol, Sequence
from uuid import uuid4

from roost.desk.control import ControlLock
from roost.events.hub import EventHub
from roost.stuck.announce import publish_card
from roost.stuck.models import CardState, StuckCard
from roost.stuck.store import StuckStore
from roost.talk.store import TalkStore, Thread
from roost.work.models import WorkDraft, WorkItem, WorkKind

logger = logging.getLogger(__name__)

CHAT_THREAD_KIND = "chat"
STUCK_MESSAGE_KIND = "stuck"
# The model-facing reason, in fixed words (the card's own words are the bot's, said to you).
REASON_FOR_MODEL: Mapping[str, str] = MappingProxyType({
    "challenge": "a check that you are human",
    "login": "a sign-in page",
    "code": "a code check",
    "refused": "the site refused you",
    "asked": "you asked the user for help",
})
SIGN_IN_REASON = "a sign-in page"
STUCK_REPLY_RULES = (
    "The user's newest message is their answer to that, instead of the card's buttons. If it says the block is "
    "cleared or to carry on, read the page again and carry on with that task. If it gives you a different task, "
    "drop the old one and do the new one."
)


class Turns(Protocol):
    async def submit(self, user_id: str, draft: WorkDraft, *, item_id: str | None = None) -> WorkItem: ...

    async def settle(self, user_id: str, bot_id: str) -> None: ...


class Teaching(Protocol):
    async def end(self, user_id: str, bot_id: str) -> None: ...


@dataclass(frozen=True)
class StuckReplyPorts:
    """What answering a card by typing needs, read off ``app.state`` per request (tests swap ``turns``)."""

    store: StuckStore
    talk: TalkStore
    events: EventHub
    turns: Turns
    control: ControlLock
    teach: Teaching | None = None


def _why(card: StuckCard) -> str:
    return SIGN_IN_REASON if card.sign_in else REASON_FOR_MODEL.get(card.reason, REASON_FOR_MODEL["asked"])


def stuck_reply_section(card: StuckCard) -> str:
    """The run's trusted line about the card your message answered. The bot's note never goes in, and the request
    only from a clean card (a tainted run may have written it), escaped and quoted as data."""
    where = f"You were stuck on {card.host} ({_why(card)})" if card.host else f"You were stuck ({_why(card)})"
    doing = ""
    if not card.tainted and card.request.strip():
        doing = f" You were doing: “{html.escape(card.request.strip(), quote=True)}”."
    return f"{where} before the user's newest message.{doing} {STUCK_REPLY_RULES}"


async def stuck_reply_for(store: StuckStore, user_id: str, items: Sequence[WorkItem]) -> str | None:
    """The trusted line for a run whose claimed messages answered a card, or ``None``."""
    for item in items:
        if item.kind is not WorkKind.MESSAGE:
            continue
        card = await store.card_for_answer(user_id, item.id)
        if card is not None and card.state is CardState.REPLIED:
            return stuck_reply_section(card)
    return None


async def _quotes_card(ports: StuckReplyPorts, user_id: str, thread_id: str, reply_to: str | None,
                       card: StuckCard) -> bool:
    """``reply_to`` is a Stuck card message of this chat that shows ``card``."""
    if reply_to is None:
        return False
    quoted = await ports.talk.get_message(user_id, reply_to)
    if quoted is None or quoted.thread_id != thread_id or quoted.kind != STUCK_MESSAGE_KIND:
        return False
    try:
        shown = json.loads(quoted.body)
    except ValueError:
        return False
    return isinstance(shown, dict) and shown.get("card_id") == card.id


async def _card_to_answer(ports: StuckReplyPorts, user_id: str, thread: Thread,
                          reply_to: str | None) -> StuckCard | None:
    if thread.kind != CHAT_THREAD_KIND:
        return None
    card = await ports.store.open_for_bot(user_id, thread.bot_id)
    if card is None:
        return None
    if card.thread_id == thread.id or await _quotes_card(ports, user_id, thread.id, reply_to, card):
        return card
    return None


async def submit_message(ports: StuckReplyPorts, user_id: str, thread: Thread, draft: WorkDraft, *,
                         reply_to: str | None = None) -> StuckCard | None:
    """Queue your message (``draft``) for the chat's bot. When it answers the bot's open Stuck card, the card closes
    as ``replied`` first and comes back; otherwise ``None`` and the message is an ordinary turn."""
    card = await _card_to_answer(ports, user_id, thread, reply_to)
    item_id = str(uuid4())
    closed = (await ports.store.close(user_id, card.id, CardState.REPLIED, answer_item_id=item_id)
              if card is not None else None)
    if closed is None:
        await ports.turns.submit(user_id, draft)
        return None
    ports.control.give_back(closed.bot_id)
    try:
        if ports.teach is not None:
            await ports.teach.end(user_id, closed.bot_id)
        await ports.turns.submit(user_id, replace(draft, tainted=False), item_id=item_id)
    except Exception:
        logger.exception("Answering Stuck card %s of bot %s in the chat failed after the card was closed",
                         closed.id, closed.bot_id)
        raise
    finally:
        try:
            await publish_card(ports.events, user_id, closed)
        finally:
            await ports.turns.settle(user_id, closed.bot_id)
    return closed
