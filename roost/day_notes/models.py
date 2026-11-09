"""Day notes' value types. Frozen: a changed note is a new object."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

AuthorKind = Literal["user", "bot"]


@dataclass(frozen=True)
class DayNoteDraft:
    day: date
    text: str


@dataclass(frozen=True)
class DayNote:
    id: str
    user_id: str
    day: date
    author_kind: AuthorKind
    bot_id: str | None          # None for the user's own notes, and once the writing bot is retired
    text: str
    created_at: str
    tainted: bool               # a bot wrote it after reading web content
