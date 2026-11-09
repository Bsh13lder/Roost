"""``DocumentStore`` — the user's documents: docs, sheets and PDFs, one
encrypted blob per file (M2 D2, D5; spec §4.7).

Documents belong to the USER: every bot with the docs role shares them, scoped
by ``user_id``, each with ``created_by_bot`` and a taint bit. ``payload`` is
the whole Univer snapshot (doc/sheet, JSON) or the PDF's bytes (base64),
``enc:v2`` under its kind's AAD (``docs:payload``, ``sheets:payload``,
``pdf:payload`` — LazyClaw's contexts); ``title`` is ``enc:v2`` under
``documents:title``. Every save is a compare-and-swap on ``revision`` (a stale
one raises ``RevisionConflict`` carrying the stored document). Deleting is soft.

A document may belong to one of the user's projects (``project_id``,
plaintext, projects hub H12). Linking goes through ``set_project`` and keeps
the revision, as ``keep`` does. Every write that sets a project first checks,
in the same session, that the project is the user's (``require_project``)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.constants import MAX_DOCUMENT_BODY_CHARS
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.documents.models import Document, DocumentChange, DocumentDraft, DocumentKind, DocumentMeta
from roost.records.project_link import require_project
from roost.records.revision import RevisionConflict
from roost.tags.codec import open_tags, seal_tags

PAYLOAD_AAD: Mapping[str, str] = MappingProxyType({"doc": "docs:payload", "sheet": "sheets:payload",
                                                    "pdf": "pdf:payload"})
_META = ("id, user_id, kind, title, pages, revision, created_at, updated_at, created_by_bot, tainted, project_id, "
         "tags")
_LIVE = "user_id = ? AND deleted_at IS NULL"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _title_aad(user_id: str) -> bytes:
    return user_aad(user_id, "documents:title")


def _tags_aad(user_id: str) -> bytes:
    return user_aad(user_id, "documents:tags")


def _payload_aad(user_id: str, kind: str) -> bytes:
    return user_aad(user_id, PAYLOAD_AAD[kind])


def _check_body(body: str) -> None:
    if len(body) > MAX_DOCUMENT_BODY_CHARS:
        raise ValueError("That document is too big to keep.")


def _row_to_meta(row: aiosqlite.Row, dek: bytes) -> DocumentMeta:
    return DocumentMeta(
        id=row["id"], user_id=row["user_id"], kind=row["kind"],
        title=decrypt_field(row["title"], dek, _title_aad(row["user_id"])) or "", pages=row["pages"],
        revision=row["revision"], created_at=row["created_at"], updated_at=row["updated_at"],
        created_by_bot=row["created_by_bot"], tainted=bool(row["tainted"]), project_id=row["project_id"],
        tags=open_tags(row["tags"], dek, _tags_aad(row["user_id"])),
    )


def _change_values(meta: DocumentMeta, change: DocumentChange, dek: bytes) -> dict[str, Any]:
    """The columns a save rewrites, encoded. Nothing to change is an error."""
    values: dict[str, Any] = {}
    if change.title is not None:
        values["title"] = encrypt_field(change.title, dek, _title_aad(meta.user_id))
    if change.body is not None:
        _check_body(change.body)
        values["payload"] = encrypt_field(change.body, dek, _payload_aad(meta.user_id, meta.kind))
    if change.pages is not None:
        values["pages"] = change.pages
    if not values:
        raise ValueError("Nothing to save: send a title or a payload.")
    return values


class DocumentStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def create(self, user_id: str, draft: DocumentDraft, *, created_by_bot: str | None,
                     tainted: bool) -> DocumentMeta:
        """``ValueError``: the body is too big, or ``draft.project_id`` is not
        one of the user's projects (nothing is written)."""
        _check_body(draft.body)
        now = _now_iso()
        meta = DocumentMeta(id=str(uuid4()), user_id=user_id, kind=draft.kind, title=draft.title, pages=draft.pages,
                            revision=1, created_at=now, updated_at=now, created_by_bot=created_by_bot,
                            tainted=tainted, project_id=draft.project_id, tags=draft.tags)
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            await require_project(db, user_id, meta.project_id)
            await db.execute(
                "INSERT INTO documents (id, user_id, kind, title, payload, pages, revision, created_at, updated_at, "
                "created_by_bot, tainted, project_id, tags) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (meta.id, user_id, meta.kind, encrypt_field(meta.title, dek, _title_aad(user_id)),
                 encrypt_field(draft.body, dek, _payload_aad(user_id, meta.kind)), meta.pages, 1, now, now,
                 created_by_bot, int(tainted), meta.project_id, seal_tags(meta.tags, dek, _tags_aad(user_id))),
            )
            await db.commit()
        return meta

    async def list(self, user_id: str, kind: DocumentKind | None = None, *,
                   project_id: str | None = None) -> tuple[DocumentMeta, ...]:
        """Newest first. ``kind`` and ``project_id`` filter in SQL, before
        anything is decrypted."""
        where, params = _LIVE, (user_id,)
        if kind:
            where, params = f"{where} AND kind = ?", (*params, kind)
        if project_id is not None:
            where, params = f"{where} AND project_id = ?", (*params, project_id)
        return await self._metas(user_id, f"WHERE {where} ORDER BY updated_at DESC", params)

    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[DocumentMeta, ...]:
        return await self._metas(user_id, f"WHERE {_LIVE} AND created_by_bot = ? ORDER BY updated_at DESC LIMIT ?",
                                 (user_id, bot_id, limit))

    async def for_project(self, user_id: str, project_id: str, limit: int) -> tuple[DocumentMeta, ...]:
        """A project's newest documents (its page, ``get_project``)."""
        return await self._metas(user_id, f"WHERE {_LIVE} AND project_id = ? ORDER BY updated_at DESC LIMIT ?",
                                 (user_id, project_id, limit))

    async def count_for_project(self, user_id: str, project_id: str) -> int:
        """How many live documents a project has (the page's tab count), counted in SQL."""
        rows = await self._rows(f"SELECT COUNT(*) FROM documents WHERE {_LIVE} AND project_id = ?",
                                (user_id, project_id))
        return int(rows[0][0])

    async def get_meta(self, user_id: str, document_id: str) -> DocumentMeta | None:
        rows = await self._rows(f"SELECT {_META} FROM documents WHERE id = ? AND {_LIVE}", (document_id, user_id))
        return _row_to_meta(rows[0], await get_user_dek(self._config, user_id)) if rows else None

    async def get(self, user_id: str, document_id: str) -> Document | None:
        rows = await self._rows(f"SELECT {_META}, payload FROM documents WHERE id = ? AND {_LIVE}",
                                (document_id, user_id))
        if not rows:
            return None
        dek = await get_user_dek(self._config, user_id)
        meta = _row_to_meta(rows[0], dek)
        return Document(meta=meta, body=decrypt_field(rows[0]["payload"], dek, _payload_aad(user_id, meta.kind)) or "")

    async def save(self, user_id: str, document_id: str, change: DocumentChange) -> DocumentMeta | None:
        """``None``: no such document. ``RevisionConflict``: ``change.base_revision``
        is not the stored revision — the UPDATE itself is the compare-and-swap.

        On success the result is built from ``change`` and the ``meta`` this
        call already read — never a re-read after the commit. A second write
        (another save, or a second Board tab) could land in that window and
        its result would then carry THAT write's values while the caller still
        thinks it saved its own, so a later autosave at the borrowed revision
        would silently overwrite it. Since the UPDATE only succeeds when the
        row still has ``change.base_revision``, nothing else can have written
        in between a successful one, so ``meta`` is still current."""
        meta = await self.get_meta(user_id, document_id)
        if meta is None:
            return None
        values = _change_values(meta, change, await get_user_dek(self._config, user_id))
        assignments = ", ".join(f"{column} = ?" for column in values)
        now = _now_iso()
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE documents SET {assignments}, revision = revision + 1, updated_at = ? "
                f"WHERE id = ? AND {_LIVE} AND revision = ?",
                (*values.values(), now, document_id, user_id, change.base_revision),
            )
            await db.commit()
        if cursor.rowcount:
            return replace(meta, title=change.title if change.title is not None else meta.title,
                           pages=change.pages if change.pages is not None else meta.pages,
                           revision=change.base_revision + 1, updated_at=now)
        latest = await self.get(user_id, document_id)
        if latest is None:
            return None
        raise RevisionConflict(latest)

    async def keep(self, user_id: str, document_id: str) -> DocumentMeta | None:
        """The user vouches for a web-made or uploaded document (HTTP only).
        Built from the ``meta`` read before the write, not a re-read after it
        — the same reasoning as ``save``, even though keep never touches
        title/payload/revision itself."""
        meta = await self.get_meta(user_id, document_id)
        if meta is None:
            return None
        now = _now_iso()
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE documents SET tainted = 0, updated_at = ? WHERE id = ? AND {_LIVE}",
                (now, document_id, user_id),
            )
            await db.commit()
        return replace(meta, tainted=False, updated_at=now) if cursor.rowcount else None

    async def set_project(self, user_id: str, document_id: str, project_id: str | None) -> DocumentMeta | None:
        """Link the document to one of the user's projects, or unlink it
        (``None``). This mirrors ``keep``: the revision stays, so an open
        Univer editor's next autosave still lands (H12), and the result is
        built from the ``meta`` read before the write. ``None``: no such
        document. ``ValueError``: not one of the user's projects."""
        meta = await self.get_meta(user_id, document_id)
        if meta is None:
            return None
        now = _now_iso()
        async with db_session(self._config) as db:
            await require_project(db, user_id, project_id)
            cursor = await db.execute(
                f"UPDATE documents SET project_id = ?, updated_at = ? WHERE id = ? AND {_LIVE}",
                (project_id, now, document_id, user_id),
            )
            await db.commit()
        return replace(meta, project_id=project_id, updated_at=now) if cursor.rowcount else None

    async def delete(self, user_id: str, document_id: str) -> bool:
        now = _now_iso()
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE documents SET deleted_at = ?, updated_at = ? WHERE id = ? AND {_LIVE}",
                (now, now, document_id, user_id),
            )
            await db.commit()
        return cursor.rowcount > 0

    async def _metas(self, user_id: str, where: str, params: tuple) -> tuple[DocumentMeta, ...]:
        rows = await self._rows(f"SELECT {_META} FROM documents {where}", params)
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_meta(row, dek) for row in rows)

    async def _rows(self, sql: str, params: tuple) -> list[aiosqlite.Row]:
        async with db_session(self._config) as db:
            return list(await (await db.execute(sql, params)).fetchall())
