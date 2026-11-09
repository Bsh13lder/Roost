"""Announcing an Ask card: the ``approval_card`` frame and the bot's ``approval`` message in its chat.

A live frame carries diff counts but never diff text (``counts_only``): the text is served only by
``GET /api/approvals/{id}``, so file contents never travel through the event stream."""

from __future__ import annotations

import json

from roost.approvals.models import ApprovalCard, approval_card_out
from roost.events.hub import EventHub
from roost.talk.store import Message, MessageKind, TalkStore, message_out


def approval_message_body(card: ApprovalCard) -> str:
    """The ``approval`` message: JSON ``{card_id, kind, steps: [step titles]}``."""
    return json.dumps({"card_id": card.id, "kind": card.kind, "steps": [step.title for step in card.steps]})


async def publish_card(events: EventHub, user_id: str, card: ApprovalCard) -> None:
    """Sent on open and on every close."""
    out = approval_card_out(card, counts_only=True)
    await events.publish(user_id, {"type": "approval_card", "card": out.model_dump(mode="json")})


async def post_card_message(talk: TalkStore, events: EventHub, user_id: str, card: ApprovalCard) -> Message:
    """The bot's message that shows the card in its chat."""
    message = await talk.add_message(
        user_id, card.thread_id, role="bot", body=approval_message_body(card), tainted=card.tainted,
        kind="approval", author_bot_id=card.bot_id)
    await events.publish(user_id, {"type": "message", "thread_id": card.thread_id, "message": message_out(message)})
    return message


async def post_user_line(talk: TalkStore, events: EventHub, user_id: str, card: ApprovalCard, body: str,
                         *, tainted: bool) -> Message:
    """Your answer as a ``card_answer`` line the model reads."""
    line = await talk.add_message(user_id, card.thread_id, role="user", body=body, tainted=tainted,
                                  kind="card_answer")
    await events.publish(user_id, {"type": "message", "thread_id": card.thread_id, "message": message_out(line)})
    return line


async def post_result(talk: TalkStore, user_id: str, card: ApprovalCard, body: str, *, tainted: bool,
                      kind: MessageKind = "approval_result") -> Message:
    """The outcome of an approved step. Stored for the model and the chat history, and never published as
    a live frame: a read's text must not travel through the event stream."""
    return await talk.add_message(user_id, card.thread_id, role="system", body=body, tainted=tainted, kind=kind)
