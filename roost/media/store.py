"""``chat_media`` (schema v41): your uploaded pictures and a bot's screenshots, each a re-encoded JPEG sealed under
``chat_media:blob``. Every query names ``user_id``; a picture joins a message once (``attach``)."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Literal
from uuid import uuid4

from roost.config import Config
from roost.crypto.encryption import decrypt_field, encrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.media.process import CleanPicture

MediaSource = Literal["you", "bot"]
_AAD = "chat_media:blob"
_ROW = "id, width, height, source, group_label, message_id"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class StoredMedia:
    """One picture with its bytes, as a run shows it to the model."""
    id: str
    width: int
    height: int
    source: str
    group: str | None
    data: bytes


def media_out(row: Any) -> dict[str, Any]:
    """The wire shape every message's ``media`` list holds."""
    return {"id": row["id"], "width": row["width"], "height": row["height"], "source": row["source"],
            "group": row["group_label"]}


def _marks(n: int) -> str:
    return ",".join("?" * n)


class ChatMediaStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def add(self, user_id: str, thread_id: str, picture: CleanPicture, *, source: MediaSource,
                  group: str | None = None, message_id: str | None = None) -> dict[str, Any]:
        """Seal and keep ``picture``; loose (no message) unless ``message_id`` is given."""
        dek = await get_user_dek(self._config, user_id)
        sealed = encrypt(base64.b64encode(picture.data).decode("ascii"), dek, user_aad(user_id, _AAD))
        media_id = str(uuid4())
        async with db_session(self._config) as db:
            await db.execute(
                "INSERT INTO chat_media (id, user_id, thread_id, message_id, mime, width, height, bytes, source, "
                "group_label, blob, created_at) VALUES (?, ?, ?, ?, 'image/jpeg', ?, ?, ?, ?, ?, ?, ?)",
                (media_id, user_id, thread_id, message_id, picture.width, picture.height, len(picture.data),
                 source, group, sealed, _now().isoformat()))
            await db.commit()
        return {"id": media_id, "width": picture.width, "height": picture.height, "source": source, "group": group}

    async def loose_since(self, user_id: str, thread_id: str, seconds: int) -> int:
        """How many pictures were uploaded to this thread in the last ``seconds`` and not yet sent."""
        since = (_now() - timedelta(seconds=seconds)).isoformat()
        async with db_session(self._config) as db:
            row = await (await db.execute(
                "SELECT COUNT(*) FROM chat_media WHERE user_id = ? AND thread_id = ? AND message_id IS NULL "
                "AND created_at > ?", (user_id, thread_id, since))).fetchone()
        return int(row[0])

    async def attach(self, user_id: str, thread_id: str, message_id: str, ids: Iterable[str]) -> bool:
        """Join every loose picture in ``ids`` (yours, this thread's) to ``message_id``; all or none."""
        wanted = tuple(dict.fromkeys(ids))
        if not wanted:
            return True
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE chat_media SET message_id = ? WHERE user_id = ? AND thread_id = ? AND message_id IS NULL "
                f"AND id IN ({_marks(len(wanted))})", (message_id, user_id, thread_id, *wanted))
            if cursor.rowcount != len(wanted):
                await db.rollback()
                return False
            await db.commit()
        return True

    async def usable(self, user_id: str, thread_id: str, ids: Iterable[str]) -> bool:
        """Whether every id is a loose picture of yours in this thread (checked before the message is stored)."""
        wanted = tuple(dict.fromkeys(ids))
        if not wanted:
            return True
        async with db_session(self._config) as db:
            row = await (await db.execute(
                f"SELECT COUNT(*) FROM chat_media WHERE user_id = ? AND thread_id = ? AND message_id IS NULL "
                f"AND id IN ({_marks(len(wanted))})", (user_id, thread_id, *wanted))).fetchone()
        return int(row[0]) == len(wanted)

    async def for_messages(self, user_id: str, message_ids: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
        """Each message's pictures in the wire shape, in the order they were added."""
        ids = tuple(dict.fromkeys(message_ids))
        if not ids:
            return {}
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {_ROW} FROM chat_media WHERE user_id = ? AND message_id IN ({_marks(len(ids))}) "
                "ORDER BY created_at, rowid", (user_id, *ids))).fetchall()
        found: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            found.setdefault(row["message_id"], []).append(media_out(row))
        return found

    async def jpeg(self, user_id: str, media_id: str) -> bytes | None:
        """One picture's JPEG; ``None`` for an unknown id or another user's."""
        async with db_session(self._config) as db:
            row = await (await db.execute("SELECT blob FROM chat_media WHERE id = ? AND user_id = ?",
                                          (media_id, user_id))).fetchone()
        if row is None:
            return None
        return await self._open(user_id, row["blob"])

    async def with_bytes(self, user_id: str, message_ids: Iterable[str]) -> tuple[StoredMedia, ...]:
        """The pictures of these messages with their JPEGs, oldest first (what a run shows the model)."""
        ids = tuple(dict.fromkeys(message_ids))
        if not ids:
            return ()
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {_ROW}, blob FROM chat_media WHERE user_id = ? AND message_id IN ({_marks(len(ids))}) "
                "ORDER BY created_at, rowid", (user_id, *ids))).fetchall()
        return tuple([StoredMedia(row["id"], row["width"], row["height"], row["source"], row["group_label"],
                                  await self._open(user_id, row["blob"])) for row in rows])

    async def _open(self, user_id: str, sealed: str) -> bytes:
        dek = await get_user_dek(self._config, user_id)
        return base64.b64decode(decrypt_field(sealed, dek, user_aad(user_id, _AAD), fallback="") or "")
