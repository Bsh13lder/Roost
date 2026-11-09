"""Note domain model (M2 D1) — frozen dataclasses. Column names and meanings
follow LazyClaw's ``notes`` table (title, content, tags, pinned, title_key) so
M4 can import the user's LazyBrain notes."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

NOTE_PATCHABLE = frozenset({"title", "content", "tags", "pinned"})


@dataclass(frozen=True)
class Note:
    id: str
    user_id: str
    title: str
    content: str                  # markdown; may open with a --- front-matter block
    tags: tuple[str, ...]
    pinned: bool
    revision: int                 # bumped by every content write: the compare-and-swap counter
    created_at: str
    updated_at: str
    created_by_bot: str | None    # NULL: the user, or a retired bot
    tainted: bool                 # written by a run that read outside content
    project_id: str | None = None  # one of the user's projects (H12); linking never bumps the revision


@dataclass(frozen=True)
class NoteDraft:
    title: str
    content: str
    tags: tuple[str, ...] = ()
    pinned: bool = False
    project_id: str | None = None


@dataclass(frozen=True)
class NotePatch:
    changes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unknown = set(self.changes) - NOTE_PATCHABLE
        if unknown:
            raise ValueError(f"Notes can't change {', '.join(sorted(unknown))}.")
        object.__setattr__(self, "changes", MappingProxyType(dict(self.changes)))


@dataclass(frozen=True)
class NoteLink:
    target: str                   # the folded [[target]] (normalize_page)
    title: str                    # the target as written
    note_id: str | None           # the note with that title; None: no such note yet
