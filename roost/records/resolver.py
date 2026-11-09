# SPDX-License-Identifier: MIT
# Harvested from LazyClaw lazyclaw/budgets/resolver.py @ 21e1002, adapted for Roost

"""Fuzzy resolver for expense capture — turns NL project/task names into
exact entities, never silently picks a wrong target.

Tiers (precision-first):
- ``exact``      casefold name == requested  → resolved (auto).
- ``substring``  query is contained in one name  → resolved (auto-confirm).
- ``fuzzy``      ``difflib`` ratio >= 0.85, single hit  → resolved (suggested).
- ``multi``      >1 hits at any tier  → never auto. Caller asks back.
- ``none``       no hit  → caller falls back to default / asks back.

Stdlib only (``difflib``). No new dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Sequence

FUZZY_MIN_RATIO = 0.85


def _norm(s: str | None) -> str:
    return " ".join((s or "").strip().casefold().split())


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


@dataclass(frozen=True)
class NamedRef:
    id: str
    name: str


@dataclass(frozen=True)
class Resolve:
    resolved: NamedRef | None
    candidates: tuple[NamedRef, ...]
    reason: str  # exact | substring | fuzzy | multi | none


def _tier(hits: list[NamedRef], reason: str) -> Resolve | None:
    if len(hits) == 1:
        return Resolve(hits[0], (hits[0],), reason)
    if len(hits) > 1:
        return Resolve(None, tuple(hits), "multi")
    return None


def resolve(query: str, items: Sequence[NamedRef]) -> Resolve:
    """Match a free-text name, precision first; never silently pick one of several."""
    q = _norm(query)
    named = [item for item in items if item.name]
    if not q:
        return Resolve(None, (), "none")
    for reason, test in (
        ("exact", lambda item: _norm(item.name) == q),
        ("substring", lambda item: q in _norm(item.name)),
        ("fuzzy", lambda item: _ratio(q, _norm(item.name)) >= FUZZY_MIN_RATIO),
    ):
        found = _tier([item for item in named if test(item)], reason)
        if found is not None:
            return found
    return Resolve(None, (), "none")
