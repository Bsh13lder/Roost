"""Plan value objects: the stored row, and what a prompt slice holds."""

from __future__ import annotations

from dataclasses import dataclass

from roost.plan.grammar import PlanItem


@dataclass(frozen=True)
class Plan:
    id: str
    user_id: str
    bot_id: str
    content: str                 # canonical Markdown (sealed at rest)
    item_taint: frozenset[str]   # ids of items written from a run that read outside content (sealed at rest)
    revision: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class PromptItems:
    """Today's and tomorrow's open items that are clean, and how many tainted ones are left out."""

    items: tuple[PlanItem, ...]
    hidden: int
