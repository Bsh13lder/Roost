"""The Skills slice of a bot's instructions: a short, escaped index of the clean skills switched on for it.

Marked skills (*from web content*) are only counted, never named, so the index never taints a run; skills past
``SKILLS_PROMPT_BUDGET_CHARS`` are counted too, and ``search_skills`` finds them. ``read_skill`` loads a skill's steps."""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Iterable

from roost.constants import SKILLS_PROMPT_BUDGET_CHARS
from roost.skills.models import Skill
from roost.skills.names import fold_name
from roost.skills.search import rank_skills
from roost.skills.texts import INDEX_HEAD, INDEX_MORE, INDEX_TAINTED


@dataclass(frozen=True)
class SkillsSection:
    text: str
    shown: tuple[str, ...]          # the names listed, in order
    hidden_tainted: int
    hidden_budget: int


def quote(text: str) -> str:
    return html.escape(text, quote=True)


def index_line(skill: Skill) -> str:
    return f"- {quote(skill.name)} · Use when: {quote(skill.use_when)}"


def _ordered(skills: Iterable[Skill], query: str) -> list[Skill]:
    """By name; with a request, the skills it names come first, best first (skill search, owner 2026-10-31)."""
    every = sorted(skills, key=lambda s: (fold_name(s.name), s.id))
    named = rank_skills(every, query) if query else ()
    first = {s.id for s in named}
    return [*named, *(s for s in every if s.id not in first)]


def skills_section(skills: Iterable[Skill], budget: int = SKILLS_PROMPT_BUDGET_CHARS, *,
                   query: str = "") -> SkillsSection | None:
    """``None`` when the bot has no skill on. ``query``: the run's newest request, whose skills lead the index."""
    every = _ordered(skills, query)
    if not every:
        return None
    clean = [s for s in every if not s.tainted]
    lines: list[str] = []
    used = len(INDEX_HEAD)
    for skill in clean:
        line = index_line(skill)
        if used + 1 + len(line) > budget:
            break
        lines.append(line)
        used += 1 + len(line)
    hidden_budget = len(clean) - len(lines)
    hidden_tainted = len(every) - len(clean)
    tail = [INDEX_MORE.format(n=hidden_budget)] if hidden_budget else []
    tail += [INDEX_TAINTED.format(n=hidden_tainted)] if hidden_tainted else []
    shown = tuple(s.name for s in clean[:len(lines)])
    return SkillsSection(text="\n".join([INDEX_HEAD, *lines, *tail]), shown=shown,
                         hidden_tainted=hidden_tainted, hidden_budget=hidden_budget)
