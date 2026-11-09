"""``PermissionStore``: a routine's standing permissions (schema v33 ``routine_permissions``).

``host`` is ``enc:v2`` under ``routine_permissions:host``; ``host_key`` is a keyed HMAC of it (a sub-key of the DEK),
so a new permission for the same routine, site and action replaces the live one without the host in plaintext.
Every query names ``user_id``: another user's routine or permission reads as none and changes nothing. The day's
count is ``used_day``/``used_count``, moved only by ``consume``'s single compare-and-set UPDATE, so two acts in one
run can never both take the last one, and a revoke or an end date holds at once."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.crypto.encryption import decrypt_field, encrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.standing.constants import STANDING_PER_ROUTINE_MAX
from roost.standing.models import LivePermission, Permission, PermissionIn

_COLUMNS = ("id, user_id, bot_id, routine_id, host, action, max_per_day, until, used_day, used_count, created_at, "
            "revoked_at")
_AAD = "routine_permissions:host"
_KEY_LABEL = b"roost:routine-permission-host:v1"
_LIVE = "revoked_at IS NULL AND until >= ?"


class PermissionRoutineNotFound(LookupError):
    """Not this user's routine."""


def host_key(dek: bytes, host: str) -> str:
    sub = hmac.new(dek, _KEY_LABEL, hashlib.sha256).digest()
    return hmac.new(sub, host.encode("utf-8"), hashlib.sha256).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _permission(row: aiosqlite.Row, dek: bytes) -> Permission:
    user_id = row["user_id"]
    return Permission(
        id=row["id"], user_id=user_id, bot_id=row["bot_id"], routine_id=row["routine_id"],
        host=decrypt_field(row["host"], dek, user_aad(user_id, _AAD), fallback="") or "", action=row["action"],
        max_per_day=int(row["max_per_day"]), until=row["until"], used_day=row["used_day"],
        used_count=int(row["used_count"]), created_at=row["created_at"], revoked_at=row["revoked_at"])


class PermissionStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def create(self, user_id: str, routine_id: str, draft: PermissionIn) -> Permission:
        """Store the permission for this routine's bot; a live one for the same site and action is revoked in the
        same transaction. ``PermissionRoutineNotFound``: not the user's routine."""
        dek = await get_user_dek(self._config, user_id)
        key, now, new_id = host_key(dek, draft.host), _now_iso(), str(uuid4())
        async with db_session(self._config) as db:
            owner = await (await db.execute("SELECT bot_id FROM routines WHERE id = ? AND user_id = ?",
                                            (routine_id, user_id))).fetchone()
            if owner is None:
                raise PermissionRoutineNotFound(routine_id)
            await db.execute(
                "UPDATE routine_permissions SET revoked_at = ? WHERE user_id = ? AND routine_id = ? AND host_key = ? "
                "AND action = ? AND revoked_at IS NULL", (now, user_id, routine_id, key, draft.action))
            await db.execute(
                "INSERT INTO routine_permissions (id, user_id, bot_id, routine_id, host, host_key, action, "
                "max_per_day, until, used_day, used_count, created_at, revoked_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,NULL,0,?,NULL)",
                (new_id, user_id, owner["bot_id"], routine_id, encrypt(draft.host, dek, user_aad(user_id, _AAD)),
                 key, draft.action, draft.max_per_day, draft.until.isoformat(), now))
            await db.commit()
        found = await self._select(user_id, "AND id = ?", (new_id,), dek)
        return found[0]

    async def list_for_routine(self, user_id: str, routine_id: str, today: str) -> tuple[Permission, ...]:
        """The routine's permissions that have not been revoked and have not ended (today's count may be used up)."""
        return await self._select(user_id, f"AND routine_id = ? AND {_LIVE}", (routine_id, today))

    async def count_live(self, user_id: str, routine_id: str, today: str) -> int:
        return len(await self.list_for_routine(user_id, routine_id, today))

    async def live_for_routine(self, user_id: str, routine_id: str, today: str) -> tuple[LivePermission, ...]:
        """What a routine run may use today: live, with some of today's count left."""
        found = await self.list_for_routine(user_id, routine_id, today)
        return tuple(LivePermission(p.id, p.host, p.action, p.max_per_day - p.used_on(today))
                     for p in found if p.max_per_day - p.used_on(today) > 0)

    async def revoke(self, user_id: str, routine_id: str, permission_id: str) -> bool:
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE routine_permissions SET revoked_at = ? WHERE id = ? AND user_id = ? AND routine_id = ? "
                "AND revoked_at IS NULL", (_now_iso(), permission_id, user_id, routine_id))
            await db.commit()
        return cursor.rowcount == 1

    async def is_live(self, user_id: str, permission_id: str, today: str) -> bool:
        """Not revoked, not ended, and some of today's count left."""
        async with db_session(self._config) as db:
            row = await (await db.execute(
                f"SELECT 1 FROM routine_permissions WHERE id = ? AND user_id = ? AND {_LIVE} "
                "AND (used_day IS NULL OR used_day != ? OR used_count < max_per_day)",
                (permission_id, user_id, today, today))).fetchone()
        return row is not None

    async def consume(self, user_id: str, permission_id: str, today: str) -> bool:
        """Take one of today's count. False when it is revoked, ended or used up (nothing changes)."""
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE routine_permissions SET used_count = CASE WHEN used_day = ? THEN used_count + 1 ELSE 1 END, "
                f"used_day = ? WHERE id = ? AND user_id = ? AND {_LIVE} "
                "AND (used_day IS NULL OR used_day != ? OR used_count < max_per_day)",
                (today, today, permission_id, user_id, today, today))
            await db.commit()
        return cursor.rowcount == 1

    async def _select(self, user_id: str, extra: str, params: tuple, dek: bytes | None = None,
                      ) -> tuple[Permission, ...]:
        dek = dek if dek is not None else await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {_COLUMNS} FROM routine_permissions WHERE user_id = ? {extra} "
                "ORDER BY created_at, id LIMIT ?", (user_id, *params, STANDING_PER_ROUTINE_MAX * 4))).fetchall()
        return tuple(_permission(row, dek) for row in rows)
