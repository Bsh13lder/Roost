"""Pure ordering of memories: by importance, and by how many query words a memory holds."""

from __future__ import annotations

from typing import Iterable

from roost.constants import MEMORY_PINNED_MAX
from roost.memory.models import Memory
from roost.notes.search import query_terms
from roost.notes.text import fold


def by_importance(memories: Iterable[Memory]) -> tuple[Memory, ...]:
    """Newest ``updated_at`` first, then a stable sort by importance, highest first."""
    newest = sorted(memories, key=lambda m: m.updated_at, reverse=True)
    return tuple(sorted(newest, key=lambda m: -m.importance))


def overlap(memory: Memory, terms: tuple[str, ...]) -> int:
    folded = fold(memory.text)
    return sum(1 for term in terms if term in folded)


def by_overlap(memories: Iterable[Memory], terms: tuple[str, ...]) -> tuple[Memory, ...]:
    ordered = by_importance(memories)
    scored = sorted(ordered, key=lambda m: -overlap(m, terms))
    return tuple(m for m in scored if overlap(m, terms) > 0)


def rank_recall(memories: Iterable[Memory], query: str, limit: int) -> tuple[Memory, ...]:
    """No query words: the most important. Otherwise the ones that hold some of them, best first."""
    terms = query_terms(query)
    if not terms:
        return by_importance(memories)[:limit]
    return by_overlap(memories, terms)[:limit]


def pick_for_prompt(memories: Iterable[Memory], query_text: str) -> tuple[Memory, ...]:
    """The order lines are drawn in: the pinned first, then the important and the relevant, alternately."""
    live = [m for m in memories if m.archived_at is None]
    important = by_importance(live)
    pinned = tuple(m for m in important if m.pinned)[:MEMORY_PINNED_MAX]
    relevant = by_overlap(live, query_terms(query_text))
    picked: list[Memory] = list(pinned)
    seen = {m.id for m in picked}
    queues = [list(important), list(relevant)]
    while any(queues):
        for queue in queues:
            while queue and queue[0].id in seen:
                queue.pop(0)
            if queue:
                memory = queue.pop(0)
                seen.add(memory.id)
                picked.append(memory)
    return tuple(picked)
