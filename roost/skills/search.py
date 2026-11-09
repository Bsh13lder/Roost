"""Skill search (owner, 2026-10-31, "like LazyClaw"): which of the user's skills a few words name, best first.

Pure. Words are folded (case, accents) and small words dropped (numbers always count); a query word counts in a field
when it is a word there or one starts with the other (four letters at least, so "proposal" finds "proposals"). A word
in the name counts most, then in Use when, then in the steps (``SKILL_SEARCH_WEIGHTS``); a skill no word names is left out."""

from __future__ import annotations

import re
from typing import Iterable

from roost.constants import SKILL_SEARCH_WEIGHTS
from roost.memory.fingerprint import normalise
from roost.skills.models import Skill
from roost.skills.names import fold_name

_WORD = re.compile(r"[0-9a-z]+")
_MIN_LETTERS = 3
_PREFIX_MIN = 4
_SMALL_WORDS = frozenset({
    "the", "and", "for", "with", "you", "your", "my", "me", "this", "that", "please", "can", "how", "what", "from",
    "los", "las", "del", "con", "por", "para", "que", "una", "uno", "mis", "tus", "esto", "eso",
})


def words_of(text: str) -> frozenset[str]:
    return frozenset(w for w in _WORD.findall(normalise(text))
                     if (len(w) >= _MIN_LETTERS or w.isdigit()) and w not in _SMALL_WORDS)


def _hits(query: frozenset[str], field: frozenset[str]) -> int:
    def found(word: str) -> bool:
        return word in field or (len(word) >= _PREFIX_MIN and any(
            len(other) >= _PREFIX_MIN and (other.startswith(word) or word.startswith(other)) for other in field))
    return sum(1 for word in query if found(word))


def score(skill: Skill, query: frozenset[str]) -> int:
    fields = (skill.name, skill.use_when, skill.body)
    return sum(weight * _hits(query, words_of(text)) for weight, text in zip(SKILL_SEARCH_WEIGHTS, fields))


def rank_skills(skills: Iterable[Skill], query: str) -> tuple[Skill, ...]:
    """The skills ``query`` names, best first (ties by name); empty when it names none."""
    wanted = words_of(query)
    if not wanted:
        return ()
    scored = [(score(s, wanted), s) for s in skills]
    return tuple(s for points, s in sorted(scored, key=lambda p: (-p[0], fold_name(p[1].name), p[1].id)) if points)
