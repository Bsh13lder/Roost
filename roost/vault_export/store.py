"""``VaultExportStore`` — the export's settings, manifest and last result (``vault_exports``), and each
project's "Export to my vault" switch (``money_projects.vault_export``), schema v30.

The manifest (``{path: sha256}`` of every file Roost wrote) is ``enc:v2`` under ``vault_exports:manifest``:
paths hold project, task and note titles. Every statement names ``user_id`` in its ``WHERE``."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Mapping

from roost.config import Config
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session


@dataclass(frozen=True)
class ExportResult:
    code: str              # ok | partial | no_grant | away | failed | off
    written: int = 0       # files created or overwritten
    conflicts: int = 0     # files left alone with a .conflict.md copy beside them
    failed: int = 0        # files the keeper refused (too big, a name it would not take)


@dataclass(frozen=True)
class ExportSettings:
    grant_id: str | None = None
    journals: bool = False
    manifest: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    last_result: str | None = None
    last_written: int = 0
    last_conflicts: int = 0
    last_export_at: str | None = None


def _aad(user_id: str) -> bytes:
    return user_aad(user_id, "vault_exports:manifest")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _manifest(raw: str | None, dek: bytes, user_id: str) -> Mapping[str, str]:
    if raw is None:
        return MappingProxyType({})
    try:
        parsed = json.loads(decrypt_field(raw, dek, _aad(user_id)) or "{}")
    except json.JSONDecodeError:
        return MappingProxyType({})
    if not isinstance(parsed, dict):
        return MappingProxyType({})
    return MappingProxyType({str(k): str(v) for k, v in parsed.items()})


class VaultExportStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def settings(self, user_id: str) -> ExportSettings:
        async with db_session(self._config) as db:
            row = await (await db.execute(
                "SELECT grant_id, journals, manifest, last_result, last_written, last_conflicts, last_export_at "
                "FROM vault_exports WHERE user_id = ?", (user_id,))).fetchone()
        if row is None:
            return ExportSettings()
        dek = await get_user_dek(self._config, user_id)
        return ExportSettings(grant_id=row["grant_id"], journals=bool(row["journals"]),
                              manifest=_manifest(row["manifest"], dek, user_id), last_result=row["last_result"],
                              last_written=row["last_written"], last_conflicts=row["last_conflicts"],
                              last_export_at=row["last_export_at"])

    async def save_settings(self, user_id: str, *, grant_id: str | None, journals: bool) -> ExportSettings:
        async with db_session(self._config) as db:
            await db.execute(
                "INSERT INTO vault_exports (user_id, grant_id, journals, updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET grant_id = excluded.grant_id, journals = excluded.journals, "
                "updated_at = excluded.updated_at", (user_id, grant_id, int(journals), _now_iso()))
            await db.commit()
        return await self.settings(user_id)

    async def save_run(self, user_id: str, manifest: Mapping[str, str], result: ExportResult) -> None:
        dek = await get_user_dek(self._config, user_id)
        sealed = encrypt_field(json.dumps(dict(manifest), sort_keys=True), dek, _aad(user_id))
        now = _now_iso()
        async with db_session(self._config) as db:
            await db.execute(
                "UPDATE vault_exports SET manifest = ?, last_result = ?, last_written = ?, last_conflicts = ?, "
                "last_export_at = ?, updated_at = ? WHERE user_id = ?",
                (sealed, result.code, result.written, result.conflicts, now, now, user_id))
            await db.commit()

    async def set_project(self, user_id: str, project_id: str, on: bool) -> bool:
        """``False``: no such live project of this user's."""
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE money_projects SET vault_export = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (int(on), project_id, user_id))
            await db.commit()
        return cursor.rowcount > 0

    async def exported_projects(self, user_id: str) -> tuple[str, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                "SELECT id FROM money_projects WHERE user_id = ? AND vault_export = 1 AND deleted_at IS NULL "
                "ORDER BY created_at, id", (user_id,))).fetchall()
        return tuple(row["id"] for row in rows)
