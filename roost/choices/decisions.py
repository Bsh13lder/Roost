"""Decisions: a choice you made, kept as a memory of the bot, found again by its question."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from datetime import datetime, timedelta, timezone

from roost.constants import (
    CHOICE_QUESTION_MAX_CHARS, DECISION_DANGEROUS_WORDS, DECISION_REUSE_MAX_DAYS, DECISIONS_LIST_MAX,
    MEMORY_TEXT_MAX_CHARS,
)
from roost.memory.models import Memory, MemoryDraft
from roost.memory.service import MemoryService

DECISION_KIND = "decision"
DECISION_SEPARATOR = "\nDecision: "
_STORED_SEPARATOR = " Decision: "  # the memory service folds the newline into a space
_SPACES = re.compile(r"\s+")
_CLOSING = "?.!"


def _fold(text: str) -> str:
    return _SPACES.sub(" ", text).strip().casefold().rstrip(_CLOSING).strip()


def decision_text(question: str, answer: str) -> str:
    """``{"q": question, "a": answer}`` as JSON, so no text either side can pose as the other. Both are cut
    so the whole fits one memory."""
    q = _SPACES.sub(" ", question).strip()[:CHOICE_QUESTION_MAX_CHARS]
    a = _SPACES.sub(" ", answer).strip()
    while True:
        text = json.dumps({"q": q, "a": a}, ensure_ascii=False, separators=(",", ":"))
        if len(text) <= MEMORY_TEXT_MAX_CHARS or not a:
            return text
        a = a[: max(len(a) - max(len(text) - MEMORY_TEXT_MAX_CHARS, 1), 0)].strip()


def _parse_structured(text: str) -> tuple[str, str] | None:
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("q"), str) or not isinstance(data.get("a"), str):
        return None
    return data["q"].strip(), data["a"].strip()


def parse_decision(text: str) -> tuple[str, str] | None:
    """The pair, from the JSON form or from an old ``question Decision: answer`` row."""
    if text.lstrip().startswith("{"):
        pair = _parse_structured(text)
        return pair if pair and pair[0] and pair[1] else None
    question, sep, answer = text.partition(DECISION_SEPARATOR)
    if not sep:
        question, sep, answer = text.partition(_STORED_SEPARATOR)
    if not sep or not question.strip() or not answer.strip():
        return None
    return question.strip(), answer.strip()


_DANGEROUS = re.compile(r"\b(?:" + "|".join(DECISION_DANGEROUS_WORDS) + r")", re.IGNORECASE)


def is_dangerous(question: str) -> bool:
    """A question about deleting, sending, paying and the like is asked every time."""
    return _DANGEROUS.search(question) is not None


def same_question(a: str, b: str) -> bool:
    folded = _fold(a)
    return bool(folded) and folded == _fold(b)


@dataclass(frozen=True)
class Decision:
    memory_id: str
    question: str
    answer: str
    decided_at: str
    tainted: bool

    def reusable(self, *, tainted_run: bool, now: datetime | None = None) -> bool:
        """Answer from it without asking: a clean run, a young decision, a question that isn't dangerous."""
        if tainted_run or is_dangerous(self.question):
            return False
        try:
            decided = datetime.fromisoformat(self.decided_at)
        except ValueError:
            return False
        if decided.tzinfo is None:
            decided = decided.replace(tzinfo=timezone.utc)
        return (now or datetime.now(timezone.utc)) - decided < timedelta(days=DECISION_REUSE_MAX_DAYS)


def _as_decision(memory: Memory) -> Decision | None:
    if memory.kind != DECISION_KIND:
        return None
    parsed = parse_decision(memory.text)
    if parsed is None:
        return None
    return Decision(memory.id, parsed[0], parsed[1], memory.updated_at, memory.tainted)


class DecisionBook:
    def __init__(self, memory: MemoryService) -> None:
        self._memory = memory

    async def record(self, user_id: str, bot_id: str, question: str, answer: str, *, tainted: bool) -> Decision:
        """Save it as this bot's memory. ``MemoryRefused``: the text looks like a secret."""
        draft = MemoryDraft(kind=DECISION_KIND, text=decision_text(question, answer), bot_id=bot_id,
                            source="user", created_by_bot=None, pinned=False, tainted=tainted)
        saved = (await self._memory.save(user_id, draft)).memory
        decision = _as_decision(saved)
        assert decision is not None
        return decision

    async def list(self, user_id: str, bot_id: str) -> tuple[Decision, ...]:
        """This bot's decisions, newest first (About you is never a decision)."""
        memories = await self._memory.list_for_bot(user_id, bot_id, kind=DECISION_KIND, limit=DECISIONS_LIST_MAX)
        found = (_as_decision(m) for m in memories if m.bot_id == bot_id)
        return tuple(d for d in found if d is not None)

    async def find(self, user_id: str, bot_id: str, question: str) -> Decision | None:
        """The user's own earlier answer to this question. A line a bot saved itself never counts, so a bot
        can't invent a decision to skip asking."""
        memories = await self._memory.list_for_bot(user_id, bot_id, kind=DECISION_KIND, limit=DECISIONS_LIST_MAX)
        for memory in memories:
            decision = _as_decision(memory) if memory.bot_id == bot_id and memory.source == "user" else None
            if decision is not None and same_question(decision.question, question):
                return decision
        return None
