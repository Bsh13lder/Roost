"""Announcing a Stuck card (stuck flow R7): the ``stuck_card`` frame that every
state change publishes, and the bot's own lines in its chat (the card message,
the blocked line, the give-up line)."""

from __future__ import annotations

from roost.events.hub import EventHub
from roost.stuck.models import StuckCard, stuck_card_out
from roost.talk.store import Message, MessageKind, TalkStore, message_out


async def publish_card(events: EventHub, user_id: str, card: StuckCard) -> None:
    """Sent on open, cleared, given_up, blocked and main_opened. Stored encrypted like every frame."""
    await events.publish(user_id, {"type": "stuck_card", "card": stuck_card_out(card).model_dump(mode="json")})


async def post_bot_line(
    talk: TalkStore, events: EventHub, user_id: str, card: StuckCard, body: str, *, kind: MessageKind,
) -> Message:
    """Post ``body`` in the card's chat as the card's bot, with the card's taint, and publish it live."""
    message = await talk.add_message(
        user_id, card.thread_id, role="bot", body=body, tainted=card.tainted,
        kind=kind, author_bot_id=card.bot_id,
    )
    await events.publish(user_id, {"type": "message", "thread_id": card.thread_id, "message": message_out(message)})
    return message
