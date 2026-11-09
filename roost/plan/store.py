"""``PlanStore``: one sealed Plan per bot, scoped by user and bot, saved by compare-and-swap on ``revision``.

``content`` is ``enc:v2`` under ``bot_plans:content`` and ``item_taint`` (a JSON list of item ids) under
``bot_plans:item_taint``. A save that read an older revision raises ``RevisionConflict`` with the stored Plan."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.plan.models import Plan
from roost.records.revision import RevisionConflict

_COLUMNS = "id, user_id, bot_id, content, item_taint, revision, created_at, updated_at"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"bot_plans:{column}")


def _ids(raw: str) -> frozenset[str]:
    try:
        parsed = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return frozenset()
    return frozenset(str(i) for i in parsed) if isinstance(parsed, list) else frozenset()


def _row_to_plan(row: aiosqlite.Row, dek: bytes) -> Plan:
    uid = row["user_id"]
    return Plan(
        id=row["id"], user_id=uid, bot_id=row["bot_id"],
        content=decrypt_field(row["content"], dek, _aad(uid, "content")) or "",
        item_taint=_ids(decrypt_field(row["item_taint"], dek, _aad(uid, "item_taint")) or ""),
        revision=row["revision"], created_at=row["created_at"], updated_at=row["updated_at"],
    )


class PlanStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def get(self, user_id: str, bot_id: str) -> Plan | None:
        async with db_session(self._config) as db:
            row = await (await db.execute(
                f"SELECT {_COLUMNS} FROM bot_plans WHERE user_id = ? AND bot_id = ?", (user_id, bot_id))).fetchone()
        if row is None:
            return None
        return _row_to_plan(row, await get_user_dek(self._config, user_id))

    async def get_or_create(self, user_id: str, bot_id: str) -> Plan:
        """The bot's Plan, made empty on first use. The caller has checked the bot is the user's."""
        found = await self.get(user_id, bot_id)
        if found is not None:
            return found
        dek = await get_user_dek(self._config, user_id)
        now = _now()
        async with db_session(self._config) as db:
            await db.execute(
                "INSERT OR IGNORE INTO bot_plans (id, user_id, bot_id, content, item_taint, revision, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                (str(uuid4()), user_id, bot_id, encrypt_field("", dek, _aad(user_id, "content")),
                 encrypt_field("[]", dek, _aad(user_id, "item_taint")), now, now))
            await db.commit()
        made = await self.get(user_id, bot_id)
        if made is None:
            raise RuntimeError("The Plan could not be created.")
        return made

    async def save(self, user_id: str, bot_id: str, content: str, item_taint: frozenset[str],
                   base_revision: int) -> Plan:
        """Write ``content`` only if the row is still at ``base_revision``; otherwise ``RevisionConflict(current)``."""
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE bot_plans SET content = ?, item_taint = ?, revision = revision + 1, updated_at = ? "
                "WHERE user_id = ? AND bot_id = ? AND revision = ?",
                (encrypt_field(content, dek, _aad(user_id, "content")),
                 encrypt_field(json.dumps(sorted(item_taint)), dek, _aad(user_id, "item_taint")),
                 _now(), user_id, bot_id, base_revision))
            await db.commit()
        latest = await self.get(user_id, bot_id)
        if latest is None:
            raise RuntimeError("The Plan is missing.")
        if cursor.rowcount == 0:
            raise RevisionConflict(latest)
        return latest
