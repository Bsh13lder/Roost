"""``RoomStore`` — rooms and their members. ``rooms.name`` is encrypted
(``rooms:name``); ids and times are plaintext. Every query is scoped by
``user_id``. A room's posts live in its room thread (``threads.kind =
'room'``), whose ``bot_id`` is the coordinator's — ``set_coordinator``
moves both together so retiring a coordinator never cascades the thread
away (D-E: "deleting a member keeps the room working")."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.crypto.encryption import decrypt, encrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.rooms.models import Room

_NAME_AAD = "rooms:name"
_COLUMNS = "id, user_id, name, coordinator_bot_id, thread_id, created_at, updated_at"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def room_out(room: Room) -> dict[str, Any]:
    return {
        "id": room.id, "name": room.name, "coordinator_id": room.coordinator_id,
        "member_ids": list(room.member_ids), "thread_id": room.thread_id,
        "created_at": room.created_at, "updated_at": room.updated_at,
    }


class RoomStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def create(
        self, user_id: str, *, name: str, member_ids: tuple[str, ...], coordinator_id: str, thread_id: str,
    ) -> Room:
        dek = await get_user_dek(self._config, user_id)
        room_id, now = str(uuid4()), _now_iso()
        async with db_session(self._config) as db:
            try:
                await db.execute(
                    f"INSERT INTO rooms ({_COLUMNS}) VALUES (?,?,?,?,?,?,?)",
                    (room_id, user_id, encrypt(name, dek, user_aad(user_id, _NAME_AAD)), coordinator_id,
                     thread_id, now, now),
                )
                await db.executemany(
                    "INSERT INTO room_members (room_id, bot_id, user_id, added_at) VALUES (?,?,?,?)",
                    [(room_id, bot_id, user_id, now) for bot_id in member_ids],
                )
                await db.commit()
            except aiosqlite.Error:
                await db.rollback()
                raise
        return Room(id=room_id, user_id=user_id, name=name, coordinator_id=coordinator_id,
                    member_ids=member_ids, thread_id=thread_id, created_at=now, updated_at=now)

    async def get(self, user_id: str, room_id: str) -> Room | None:
        rooms = await self._load(user_id, "id = ?", (room_id,))
        return rooms[0] if rooms else None

    async def list(self, user_id: str) -> list[Room]:
        return await self._load(user_id, "1 = 1", ())

    async def get_by_thread(self, user_id: str, thread_id: str) -> Room | None:
        rooms = await self._load(user_id, "thread_id = ?", (thread_id,))
        return rooms[0] if rooms else None

    async def rooms_coordinated_by(self, user_id: str, bot_id: str) -> list[Room]:
        return await self._load(user_id, "coordinator_bot_id = ?", (bot_id,))

    async def set_coordinator(self, user_id: str, room: Room, bot_id: str) -> None:
        now = _now_iso()
        async with db_session(self._config) as db:
            await db.execute("UPDATE rooms SET coordinator_bot_id = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                             (bot_id, now, room.id, user_id))
            await db.execute("UPDATE threads SET bot_id = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                             (bot_id, now, room.thread_id, user_id))
            await db.commit()

    async def delete(self, user_id: str, room_id: str) -> bool:
        async with db_session(self._config) as db:
            cursor = await db.execute("DELETE FROM rooms WHERE id = ? AND user_id = ?", (room_id, user_id))
            await db.commit()
        return cursor.rowcount > 0

    async def _load(self, user_id: str, condition: str, params: tuple) -> list[Room]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {_COLUMNS} FROM rooms WHERE user_id = ? AND {condition} ORDER BY created_at",
                (user_id, *params),
            )).fetchall()
            if not rows:
                return []
            ids = [row["id"] for row in rows]
            members = await (await db.execute(
                f"SELECT room_id, bot_id FROM room_members WHERE user_id = ? AND room_id IN ({','.join('?' * len(ids))}) "
                "ORDER BY rowid", (user_id, *ids),
            )).fetchall()
        dek = await get_user_dek(self._config, user_id)
        return [self._room(row, members, dek) for row in rows]

    @staticmethod
    def _room(row: aiosqlite.Row, members: Sequence[aiosqlite.Row], dek: bytes) -> Room:
        user_id = row["user_id"]
        return Room(
            id=row["id"], user_id=user_id, name=decrypt(row["name"], dek, user_aad(user_id, _NAME_AAD)),
            coordinator_id=row["coordinator_bot_id"],
            member_ids=tuple(m["bot_id"] for m in members if m["room_id"] == row["id"]),
            thread_id=row["thread_id"], created_at=row["created_at"], updated_at=row["updated_at"],
        )
