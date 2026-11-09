"""``GrantStore`` — the folders the user shared (schema v23 ``mac_grants``).

``path`` and ``label`` are user content, ``enc:v2`` under ``mac_grants:path`` and
``mac_grants:label``; ids, access, read policy, the vault flag and times stay plaintext.
Every per-user query has ``user_id`` in its ``WHERE``, so another user's grant reads as
"no such grant". Revoking sets ``revoked_at`` and keeps the row (its marks and audit history
keep their grant). ``all_live`` runs for the keeper push, across users."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence
from uuid import uuid4

import aiosqlite

from roost.config import RoostConfig
from roost.crypto.encryption import decrypt_field, encrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.mac.models import Grant, GrantDraft

_COLUMNS = "id, user_id, bot_id, path, label, access, read_policy, is_vault, created_at, revoked_at"
_UNREADABLE = ""


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"mac_grants:{column}")


def _row_to_grant(row: aiosqlite.Row, dek: bytes) -> Grant:
    user_id = row["user_id"]
    return Grant(
        id=row["id"], user_id=user_id, bot_id=row["bot_id"],
        path=decrypt_field(row["path"], dek, _aad(user_id, "path"), fallback=_UNREADABLE) or _UNREADABLE,
        label=decrypt_field(row["label"], dek, _aad(user_id, "label"), fallback=_UNREADABLE) or _UNREADABLE,
        access=row["access"], read_policy=row["read_policy"], is_vault=bool(row["is_vault"]),
        created_at=row["created_at"], revoked_at=row["revoked_at"],
    )


class GrantStore:
    def __init__(self, config: RoostConfig) -> None:
        self._config = config

    async def create(self, user_id: str, draft: GrantDraft) -> Grant:
        dek = await get_user_dek(self._config, user_id)
        grant = Grant(
            id=str(uuid4()), user_id=user_id, bot_id=draft.bot_id, path=draft.path, label=draft.label,
            access=draft.access, read_policy=draft.read_policy, is_vault=draft.is_vault,
            created_at=datetime.now(timezone.utc).isoformat(), revoked_at=None,
        )
        async with db_session(self._config) as db:
            await db.execute(
                "INSERT INTO mac_grants (id, user_id, bot_id, path, label, access, read_policy, is_vault, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (grant.id, user_id, grant.bot_id, encrypt(grant.path, dek, _aad(user_id, "path")),
                 encrypt(grant.label, dek, _aad(user_id, "label")), grant.access, grant.read_policy,
                 int(grant.is_vault), grant.created_at),
            )
            await db.commit()
        return grant

    async def get(self, user_id: str, grant_id: str) -> Grant | None:
        found = await self._select(user_id, "WHERE id = ? AND user_id = ? AND revoked_at IS NULL", (grant_id, user_id))
        return found[0] if found else None

    async def list_live(self, user_id: str) -> tuple[Grant, ...]:
        return await self._select(user_id, "WHERE user_id = ? AND revoked_at IS NULL ORDER BY created_at, rowid", (user_id,))

    async def list_for_bot(self, user_id: str, bot_id: str) -> tuple[Grant, ...]:
        """This bot's grants and the all-bots ones."""
        return await self._select(
            user_id, "WHERE user_id = ? AND revoked_at IS NULL AND (bot_id = ? OR bot_id IS NULL) "
                     "ORDER BY created_at, rowid", (user_id, bot_id),
        )

    async def update(self, user_id: str, grant_id: str, *, label: str, access: str, read_policy: str) -> Grant | None:
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE mac_grants SET label = ?, access = ?, read_policy = ? "
                f"WHERE id = ? AND user_id = ? AND revoked_at IS NULL RETURNING {_COLUMNS}",
                (encrypt(label, dek, _aad(user_id, "label")), access, read_policy, grant_id, user_id),
            )
            rows = await cursor.fetchall()
            await db.commit()
        return _row_to_grant(rows[0], dek) if rows else None

    async def revoke(self, user_id: str, grant_id: str) -> Grant | None:
        """Set ``revoked_at``; ``None`` when the grant is not the user's or is already revoked."""
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE mac_grants SET revoked_at = ? WHERE id = ? AND user_id = ? AND revoked_at IS NULL "
                f"RETURNING {_COLUMNS}",
                (datetime.now(timezone.utc).isoformat(), grant_id, user_id),
            )
            rows = await cursor.fetchall()
            await db.commit()
        return _row_to_grant(rows[0], dek) if rows else None

    async def all_live(self) -> tuple[Grant, ...]:
        """Every user's live grants, for the keeper push."""
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {_COLUMNS} FROM mac_grants WHERE revoked_at IS NULL ORDER BY created_at, rowid"
            )).fetchall()
        deks: dict[str, bytes] = {}
        grants: list[Grant] = []
        for row in rows:
            user_id = row["user_id"]
            if user_id not in deks:
                deks[user_id] = await get_user_dek(self._config, user_id)
            grant = _row_to_grant(row, deks[user_id])
            if grant.path:   # a path that can't be read can't be pushed
                grants.append(grant)
        return tuple(grants)

    async def _select(self, user_id: str, where: str, params: Sequence) -> tuple[Grant, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_COLUMNS} FROM mac_grants {where}", tuple(params))).fetchall()
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_grant(row, dek) for row in rows)
