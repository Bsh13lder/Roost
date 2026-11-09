"""W1 (docs/plans/2026-10-23-roost-owner-words.md): a typed plain yes or no answers the one Ask card waiting in
the chat, through the card's own Yes/No path (``ApprovalService.answer``: the same audit, line and work item).

Only an ``ask`` card that is not an options card counts; a Proposal, an options card, or two cards at once leave
the message on its usual way."""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Literal

from roost.approvals.models import ApprovalCard, BadAnswer, CardClosed
from roost.approvals.service import ApprovalService
from roost.approvals.store import ApprovalStore
from roost.choices.models import choice_of
from roost.owner_words.constants import (
    OWNER_ANSWER_MAX_CHARS, OWNER_ANSWER_MAX_WORDS, OWNER_NO_WORDS, OWNER_YES_WORDS,
)

logger = logging.getLogger(__name__)

TypedAnswer = Literal["yes", "no"]
_NOT_WORDS = re.compile(r"[^0-9a-z]+")
_APOSTROPHES = ("'", "’")
_YES = frozenset(OWNER_YES_WORDS)
_NO = frozenset(OWNER_NO_WORDS)


def _words(text: str) -> str:
    folded = text.casefold()
    for mark in _APOSTROPHES:
        folded = folded.replace(mark, "")
    bare = "".join(char for char in unicodedata.normalize("NFKD", folded) if not unicodedata.combining(char))
    return _NOT_WORDS.sub(" ", bare).strip()


def typed_answer(text: str) -> TypedAnswer | None:
    """``yes`` or ``no`` when the whole message is a plain yes or no; None for anything else."""
    if len(text) > OWNER_ANSWER_MAX_CHARS:
        return None
    words = _words(text)
    if not words or len(words.split()) > OWNER_ANSWER_MAX_WORDS:
        return None
    if words in _YES:
        return "yes"
    if words in _NO:
        return "no"
    return None


def _answerable(card: ApprovalCard) -> bool:
    return card.kind == "ask" and choice_of(card) is None


async def answer_by_words(store: ApprovalStore, service: ApprovalService, user_id: str, thread_id: str,
                          text: str) -> ApprovalCard | None:
    """The card a plain yes or no answered, or None (not a plain answer, not exactly one Ask card, or it closed)."""
    answer = typed_answer(text)
    if answer is None:
        return None
    waiting = await store.open_in_thread(user_id, thread_id)
    if len(waiting) != 1 or not _answerable(waiting[0]):
        return None
    try:
        return await service.answer(user_id, waiting[0].id, answer)
    except (CardClosed, BadAnswer):
        logger.info("A typed %s found card %s already closed", answer, waiting[0].id)
        return None
