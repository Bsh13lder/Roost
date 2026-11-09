"""``MemoryService``: the one door for memories. It cleans the text, refuses secrets, keeps About you
shared, says who may forget, and publishes ``memories_changed``."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from roost.constants import MEMORY_CAPTURE_WINDOW_S, MEMORY_FADE_DAYS, MEMORY_RECALL_LIMIT, MEMORY_TEXT_MAX_CHARS
from roost.events.hub import EventHub
from roost.memory.models import NEEDS_BOT_MESSAGE, Memory, MemoryDraft
from roost.memory.ranking import rank_recall
from roost.memory.secrets import SECRET_REFUSAL_TEXT, looks_secret
from roost.memory.store import MemoryExists, MemoryStore
from roost.records.tool_text import plain

EMPTY_MEMORY_TEXT = "A memory needs some text."
LONG_MEMORY_TEXT = f"A memory is at most {MEMORY_TEXT_MAX_CHARS} characters."
NEEDS_BOT_TEXT = NEEDS_BOT_MESSAGE
ABOUT_YOU_SCOPE_TEXT = ("About you is shared by every bot, so a memory can't move in or out of it. "
                        "Add it again instead.")
DUPLICATE_MEMORY_TEXT = "You already have that memory."
NOT_YOURS_TEXT = "Refused: that memory isn't yours to forget."
_SPACES = re.compile(r"\s+")


class MemoryRefused(ValueError):
    """A plain sentence for the user."""


class MemoryDuplicate(MemoryRefused):
    """An edit would copy another memory (the route's 409)."""


class MemoryNotYours(PermissionError):
    """A bot tried to forget a memory it may not."""


@dataclass(frozen=True)
class SaveResult:
    memory: Memory
    created: bool


@dataclass(frozen=True)
class MemoryPatch:
    text: str | None = None
    kind: str | None = None
    importance: int | None = None
    pinned: bool | None = None
    restore: bool | None = None


def _clean(text: str) -> str:
    """Tidy, then refuse an empty, too long or secret text."""
    cleaned = _SPACES.sub(" ", plain(text)).strip()
    if not cleaned:
        raise MemoryRefused(EMPTY_MEMORY_TEXT)
    if len(cleaned) > MEMORY_TEXT_MAX_CHARS:
        raise MemoryRefused(LONG_MEMORY_TEXT)
    if looks_secret(cleaned):
        raise MemoryRefused(SECRET_REFUSAL_TEXT)
    return cleaned


def _may_forget(memory: Memory, by_bot: str) -> bool:
    if memory.bot_id == by_bot:
        return True
    return memory.bot_id is None and memory.source == "bot" and memory.created_by_bot == by_bot


class MemoryService:
    def __init__(self, store: MemoryStore, events: EventHub) -> None:
        self._store = store
        self._events = events

    async def _publish(self, user_id: str, change: str, memory_id: str | None, bot_id: str | None) -> None:
        await self._events.publish(user_id, {"type": "memories_changed", "change": change,
                                             "memory_id": memory_id, "bot_id": bot_id})

    @staticmethod
    def check_text(text: str) -> str:
        """The text as it would be saved. ``MemoryRefused``: empty, too long or a secret."""
        return _clean(text)

    async def save(self, user_id: str, draft: MemoryDraft) -> SaveResult:
        """``MemoryRefused``: empty, too long, a secret, or a bot kind with no bot."""
        cleaned = _clean(draft.text)
        try:
            memory, created = await self._store.upsert(user_id, replace(draft, text=cleaned))
        except ValueError as exc:
            raise MemoryRefused(str(exc)) from exc
        await self._publish(user_id, "created" if created else "updated", memory.id, memory.bot_id)
        return SaveResult(memory, created)

    async def edit(self, user_id: str, memory_id: str, patch: MemoryPatch) -> Memory | None:
        current = await self._store.get(user_id, memory_id)
        if current is None:
            return None
        fields: dict[str, object] = {}
        if patch.kind is not None and (patch.kind == "about_you") != (current.kind == "about_you"):
            raise MemoryRefused(ABOUT_YOU_SCOPE_TEXT)
        if patch.text is not None:
            fields.update(text=_clean(patch.text), source="user", tainted=False)
        if patch.kind is not None:
            fields["kind"] = patch.kind
        if patch.importance is not None:
            fields["importance"] = patch.importance
        if patch.pinned is not None:
            fields["pinned"] = patch.pinned
        if patch.restore:
            fields["archived_at"] = None
        try:
            updated = await self._store.update(user_id, memory_id, **fields)
        except MemoryExists as exc:
            raise MemoryDuplicate(DUPLICATE_MEMORY_TEXT) from exc
        if updated is not None:
            await self._publish(user_id, "updated", updated.id, updated.bot_id)
        return updated

    async def forget(self, user_id: str, memory_id: str, *, by_bot: str | None = None) -> bool:
        """``False``: no such memory. ``MemoryNotYours``: a bot reaching past what it saved."""
        memory = await self._store.get(user_id, memory_id)
        if memory is None:
            return False
        if by_bot is not None and not _may_forget(memory, by_bot):
            raise MemoryNotYours(NOT_YOURS_TEXT)
        if not await self._store.delete(user_id, memory_id):
            return False
        await self._publish(user_id, "deleted", memory_id, memory.bot_id)
        return True

    async def list_for_bot(self, user_id: str, bot_id: str, *, faded: bool = False, kind: str | None = None,
                           limit: int | None = None) -> tuple[Memory, ...]:
        extra = {} if limit is None else {"limit": limit}
        return await self._store.list_scopes(user_id, bot_id, faded=faded, kind=kind, **extra)

    async def recall(self, user_id: str, bot_id: str, query: str) -> tuple[Memory, ...]:
        hits = rank_recall(await self.list_for_bot(user_id, bot_id), query, MEMORY_RECALL_LIMIT)
        await self._store.touch_recalled(user_id, [m.id for m in hits])
        return hits

    async def touch_recalled(self, user_id: str, ids: tuple[str, ...]) -> None:
        await self._store.touch_recalled(user_id, list(ids))

    async def fade(self, user_id: str) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=MEMORY_FADE_DAYS)
        faded = await self._store.fade(user_id, cutoff.isoformat())
        if faded:
            await self._publish(user_id, "faded", None, None)
        return faded

    async def bot_saved_last_hour(self, user_id: str) -> int:
        since = datetime.now(timezone.utc) - timedelta(seconds=MEMORY_CAPTURE_WINDOW_S)
        return await self._store.count_bot_saved_since(user_id, since.isoformat())
