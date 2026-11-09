"""Memory domain model: frozen dataclasses and the kind / scope rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, get_args

from roost.constants import MEMORY_IMPORTANCE_DEFAULT

MemoryKind = Literal["about_you", "preference", "fact", "project", "lesson", "decision"]
MemorySource = Literal["user", "bot"]

MEMORY_KINDS: tuple[str, ...] = get_args(MemoryKind)
BOT_KINDS: tuple[str, ...] = tuple(kind for kind in MEMORY_KINDS if kind != "about_you")
CAPTURE_KINDS: tuple[str, ...] = tuple(kind for kind in MEMORY_KINDS if kind not in ("lesson", "decision"))
SHARED_SCOPE = "*"
NEEDS_BOT_MESSAGE = "Say which bot this memory is for."


@dataclass(frozen=True)
class Memory:
    id: str
    user_id: str
    bot_id: str | None            # NULL: About you, shared by every bot
    scope: str                    # the bot's id, or SHARED_SCOPE
    kind: str
    text: str
    source: str
    created_by_bot: str | None
    importance: int
    pinned: bool
    tainted: bool
    created_at: str
    updated_at: str
    last_recalled_at: str | None
    archived_at: str | None
    tags: tuple[str, ...] = ()    # sealed (memories:tags); a bot's memory carries bot:<slug> and its topics


@dataclass(frozen=True)
class MemoryDraft:
    kind: str
    text: str
    bot_id: str | None
    source: str
    created_by_bot: str | None
    importance: int = MEMORY_IMPORTANCE_DEFAULT
    pinned: bool = False
    tainted: bool = False
    tags: tuple[str, ...] = ()


def scope_of(kind: str, bot_id: str | None) -> tuple[str | None, str]:
    """``(bot_id, scope)`` for a memory: About you is shared, every other kind needs its bot."""
    if kind == "about_you":
        return None, SHARED_SCOPE
    if not bot_id:
        raise ValueError(NEEDS_BOT_MESSAGE)
    return bot_id, bot_id


def memory_out(memory: Memory) -> dict[str, Any]:
    """The web's shape: no user id, scope or fingerprint."""
    return {
        "id": memory.id, "bot_id": memory.bot_id, "kind": memory.kind, "text": memory.text,
        "source": memory.source, "importance": memory.importance, "pinned": memory.pinned,
        "tainted": memory.tainted, "created_at": memory.created_at, "updated_at": memory.updated_at,
        "last_recalled_at": memory.last_recalled_at, "archived_at": memory.archived_at,
        "tags": list(memory.tags),
    }
