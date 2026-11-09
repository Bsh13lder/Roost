"""``MemoryStore``: raw encrypted CRUD for memories. The rules live in ``MemoryService``.

``text`` is ``enc:v2`` under ``memories:text``. The fingerprint is an HMAC under a key derived from the
user's DEK, unique per ``(user_id, scope, fingerprint)``, so saving the same thing twice refreshes one row.
Every query names ``user_id``."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.constants import MEMORY_FADE_MAX_IMPORTANCE, MEMORY_SCAN_LIMIT
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.memory.fingerprint import fingerprint
from roost.memory.models import SHARED_SCOPE, Memory, MemoryDraft, scope_of
from roost.tags.codec import open_tags, seal_tags

_COLUMNS = ("id", "user_id", "bot_id", "scope", "kind", "text", "source", "created_by_bot", "importance",
            "pinned", "tainted", "created_at", "updated_at", "last_recalled_at", "archived_at", "tags")
_SELECT = ", ".join(_COLUMNS)
_UNSET: Any = object()


class MemoryExists(ValueError):
    """An edit would make a memory the same as another one in its scope."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str) -> bytes:
    return user_aad(user_id, "memories:text")


def _tags_aad(user_id: str) -> bytes:
    return user_aad(user_id, "memories:tags")


def _row_to_memory(row: aiosqlite.Row, dek: bytes) -> Memory:
    return Memory(
        id=row["id"], user_id=row["user_id"], bot_id=row["bot_id"], scope=row["scope"], kind=row["kind"],
        text=decrypt_field(row["text"], dek, _aad(row["user_id"])) or "", source=row["source"],
        created_by_bot=row["created_by_bot"], importance=row["importance"], pinned=bool(row["pinned"]),
        tainted=bool(row["tainted"]), created_at=row["created_at"], updated_at=row["updated_at"],
        last_recalled_at=row["last_recalled_at"], archived_at=row["archived_at"],
        tags=open_tags(row["tags"], dek, _tags_aad(row["user_id"])),
    )


class MemoryStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def upsert(self, user_id: str, draft: MemoryDraft) -> tuple[Memory, bool]:
        """Save, or refresh the same memory in its scope (``created`` False). ``ValueError``: a bot kind with
        no bot id."""
        bot_id, scope = scope_of(draft.kind, draft.bot_id)
        now = _now_iso()
        dek = await get_user_dek(self._config, user_id)
        fp = fingerprint(dek, draft.kind, draft.text)
        async with db_session(self._config) as db:
            await db.execute(
                "INSERT INTO memories (id, user_id, bot_id, scope, kind, text, source, created_by_bot, importance,"
                " pinned, tainted, fingerprint, created_at, updated_at, tags) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(user_id, scope, fingerprint) DO UPDATE SET text = excluded.text, "
                "tags = COALESCE(excluded.tags, memories.tags), "
                "importance = MAX(memories.importance, excluded.importance), "
                "source = CASE WHEN excluded.source = 'user' THEN 'user' ELSE memories.source END, "
                "updated_at = excluded.updated_at, archived_at = NULL",
                (str(uuid4()), user_id, bot_id, scope, draft.kind, encrypt_field(draft.text, dek, _aad(user_id)),
                 draft.source, draft.created_by_bot, draft.importance, int(draft.pinned), int(draft.tainted),
                 fp, now, now, seal_tags(draft.tags, dek, _tags_aad(user_id))),
            )
            await db.commit()
            row = await (await db.execute(
                f"SELECT {_SELECT} FROM memories WHERE user_id = ? AND scope = ? AND fingerprint = ?",
                (user_id, scope, fp))).fetchone()
        memory = _row_to_memory(row, dek)
        return memory, memory.created_at == now

    async def get(self, user_id: str, memory_id: str) -> Memory | None:
        rows = await self._select(user_id, "WHERE id = ? AND user_id = ?", (memory_id, user_id))
        return rows[0] if rows else None

    async def list_scopes(self, user_id: str, bot_id: str, *, faded: bool = False,
                          limit: int = MEMORY_SCAN_LIMIT, kind: str | None = None) -> tuple[Memory, ...]:
        """About you and this bot's memories, pinned first then newest; ``faded`` includes archived ones."""
        live = "" if faded else " AND archived_at IS NULL"
        only = "" if kind is None else " AND kind = ?"
        extra = () if kind is None else (kind,)
        return await self._select(
            user_id, f"WHERE user_id = ? AND scope IN (?, ?){live}{only} "
                     "ORDER BY pinned DESC, updated_at DESC LIMIT ?",
            (user_id, SHARED_SCOPE, bot_id, *extra, limit))

    async def update(self, user_id: str, memory_id: str, *, text: Any = _UNSET, kind: Any = _UNSET,
                     importance: Any = _UNSET, pinned: Any = _UNSET, source: Any = _UNSET, tainted: Any = _UNSET,
                     archived_at: Any = _UNSET) -> Memory | None:
        """Change only the fields given. ``None``: no such memory. ``MemoryExists``: the new text or kind makes
        it the same as another memory in its scope."""
        current = await self.get(user_id, memory_id)
        if current is None:
            return None
        given = {"importance": importance, "pinned": pinned, "source": source, "tainted": tainted,
                 "archived_at": archived_at}
        sets: dict[str, Any] = {name: (int(v) if isinstance(v, bool) else v)
                                for name, v in given.items() if v is not _UNSET}
        dek = await get_user_dek(self._config, user_id)
        new_text = current.text if text is _UNSET else text
        new_kind = current.kind if kind is _UNSET else kind
        if text is not _UNSET or kind is not _UNSET:
            sets.update(text=encrypt_field(new_text, dek, _aad(user_id)), kind=new_kind,
                        fingerprint=fingerprint(dek, new_kind, new_text))
        sets["updated_at"] = _now_iso()
        assignments = ", ".join(f"{name} = ?" for name in sets)
        async with db_session(self._config) as db:
            try:
                await db.execute(f"UPDATE memories SET {assignments} WHERE id = ? AND user_id = ?",
                                 (*sets.values(), memory_id, user_id))
            except aiosqlite.IntegrityError as exc:
                raise MemoryExists("You already have that memory.") from exc
            await db.commit()
        return await self.get(user_id, memory_id)

    async def delete(self, user_id: str, memory_id: str) -> bool:
        async with db_session(self._config) as db:
            cursor = await db.execute("DELETE FROM memories WHERE id = ? AND user_id = ?", (memory_id, user_id))
            await db.commit()
        return cursor.rowcount > 0

    async def touch_recalled(self, user_id: str, ids: list[str] | tuple[str, ...]) -> None:
        if not ids:
            return
        marks = ",".join("?" * len(ids))
        async with db_session(self._config) as db:
            await db.execute(f"UPDATE memories SET last_recalled_at = ? WHERE user_id = ? AND id IN ({marks})",
                             (_now_iso(), user_id, *ids))
            await db.commit()

    async def fade(self, user_id: str, now: str) -> int:
        """Archive the user's old, minor, unpinned bot memories. ``now`` is the cut-off: rows last recalled
        (or updated) before it fade."""
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE memories SET archived_at = ? WHERE user_id = ? AND source = 'bot' AND importance <= ? "
                "AND pinned = 0 AND archived_at IS NULL AND COALESCE(last_recalled_at, updated_at) < ?",
                (_now_iso(), user_id, MEMORY_FADE_MAX_IMPORTANCE, now))
            await db.commit()
        return cursor.rowcount

    async def count_bot_saved_since(self, user_id: str, since_iso: str) -> int:
        async with db_session(self._config) as db:
            row = await (await db.execute(
                "SELECT COUNT(*) FROM memories WHERE user_id = ? AND source = 'bot' AND created_at >= ?",
                (user_id, since_iso))).fetchone()
        return int(row[0])

    async def _select(self, user_id: str, where: str, params: tuple) -> tuple[Memory, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_SELECT} FROM memories {where}", params)).fetchall()
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_memory(row, dek) for row in rows)
