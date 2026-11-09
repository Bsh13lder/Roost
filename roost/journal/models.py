"""The Bot Journal's value types. Frozen: a changed day is a new object."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class JournalDay:
    id: str
    user_id: str
    bot_id: str
    day: date                 # a local day
    content: str              # Obsidian Markdown: front matter, a heading, one "- HH:MM text" line per entry
    tainted: bool             # an entry was written in a run that read outside content
    revision: int             # the compare-and-swap counter every append bumps
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class JournalHit:
    """A day whose text matches a search."""

    bot_id: str
    day: date
    lines: tuple[str, ...]    # the matching entry lines, at most a few
    tainted: bool
