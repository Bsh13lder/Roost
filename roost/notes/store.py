"""``NoteStore`` — the user's notes, encrypted (M2 D1, D5).

Notes belong to the USER: every bot holding the notes role reads and writes the
same rows, scoped by ``user_id`` only, each with ``created_by_bot`` and a taint
bit (M1's provenance). Title, content and tags are ``enc:v2`` under
``notes:<column>``; ``title_key`` is HMAC(dek, folded title), so an exact title
or a ``[[wikilink]]`` is found without the title ever being stored in plaintext.
Every content write bumps ``revision`` and is a compare-and-swap on the revision
it read: a write that lost a race raises ``RevisionConflict`` with the stored
note instead of clobbering it. Deleting is soft (``deleted_at``).

A note may belong to one of the user's projects (``project_id``, plaintext,
projects hub H12). Linking goes through ``set_project`` and keeps the revision,
as ``keep`` does. Every write that sets a project first checks, in the same
session, that the project is the user's (``require_project``)."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.constants import NOTE_SCAN_LIMIT
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.notes.models import Note, NoteDraft, NotePatch
from roost.notes.wikilinks import normalize_page
from roost.records.project_link import require_project
from roost.records.revision import RevisionConflict

_COLUMNS = ("id", "user_id", "title", "title_key", "content", "tags", "pinned", "revision",
            "created_at", "updated_at", "created_by_bot", "tainted", "project_id")
_SELECT = ", ".join(_COLUMNS)
_LIVE = "user_id = ? AND deleted_at IS NULL"
# A patched field and the columns it rewrites (a new title needs a new title_key).
_PATCH_COLUMNS = {"title": ("title", "title_key"), "content": ("content",), "tags": ("tags",), "pinned": ("pinned",)}
# What linking a note to a project rewrites: no content, so no new revision (H12).
_LINK_COLUMNS = ("project_id", "updated_at")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"notes:{column}")


def title_key(dek: bytes, title: str) -> str:
    return hmac.new(dek, normalize_page(title).encode("utf-8"), hashlib.sha256).hexdigest()


def _encode(note: Note, column: str, dek: bytes) -> Any:
    if column in ("title", "content"):
        return encrypt_field(getattr(note, column), dek, _aad(note.user_id, column))
    if column == "tags":
        return encrypt_field(json.dumps(list(note.tags)), dek, _aad(note.user_id, column))
    if column == "title_key":
        return title_key(dek, note.title)
    if column in ("pinned", "tainted"):
        return int(getattr(note, column))
    return getattr(note, column)


def _tags(raw: str) -> tuple[str, ...]:
    try:
        parsed = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return ()
    return tuple(str(tag) for tag in parsed) if isinstance(parsed, list) else ()


def _row_to_note(row: aiosqlite.Row, dek: bytes) -> Note:
    user_id = row["user_id"]

    def text(column: str) -> str:
        return decrypt_field(row[column], dek, _aad(user_id, column)) or ""

    return Note(
        id=row["id"], user_id=user_id, title=text("title"), content=text("content"), tags=_tags(text("tags")),
        pinned=bool(row["pinned"]), revision=row["revision"], created_at=row["created_at"],
        updated_at=row["updated_at"], created_by_bot=row["created_by_bot"], tainted=bool(row["tainted"]),
        project_id=row["project_id"],
    )


class NoteStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def create(self, user_id: str, draft: NoteDraft, *, created_by_bot: str | None, tainted: bool) -> Note:
        """``ValueError``: ``draft.project_id`` is not one of the user's projects (nothing is written)."""
        now = _now_iso()
        note = Note(id=str(uuid4()), user_id=user_id, title=draft.title, content=draft.content, tags=draft.tags,
                    pinned=draft.pinned, revision=1, created_at=now, updated_at=now,
                    created_by_bot=created_by_bot, tainted=tainted, project_id=draft.project_id)
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            await require_project(db, user_id, note.project_id)
            await db.execute(f"INSERT INTO notes ({_SELECT}) VALUES ({','.join('?' * len(_COLUMNS))})",
                             tuple(_encode(note, column, dek) for column in _COLUMNS))
            await db.commit()
        return note

    async def get(self, user_id: str, note_id: str) -> Note | None:
        found = await self._select(user_id, f"WHERE id = ? AND {_LIVE}", (note_id, user_id))
        return found[0] if found else None

    async def list(self, user_id: str, *, limit: int = NOTE_SCAN_LIMIT,
                   project_id: str | None = None) -> tuple[Note, ...]:
        """Pinned first, then newest first — the order search ties break on.
        ``project_id`` keeps only that project's notes. It filters in SQL,
        before the limit and before anything is decrypted."""
        where, params = _LIVE, (user_id,)
        if project_id is not None:
            where, params = f"{_LIVE} AND project_id = ?", (user_id, project_id)
        return await self._select(user_id, f"WHERE {where} ORDER BY pinned DESC, updated_at DESC LIMIT ?",
                                  (*params, limit))

    async def with_title(self, user_id: str, title: str) -> tuple[Note, ...]:
        """Notes whose title folds to the same page key (newest first)."""
        dek = await get_user_dek(self._config, user_id)
        return await self._select(user_id, f"WHERE {_LIVE} AND title_key = ? ORDER BY updated_at DESC",
                                  (user_id, title_key(dek, title)))

    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[Note, ...]:
        return await self._select(user_id, f"WHERE {_LIVE} AND created_by_bot = ? ORDER BY updated_at DESC LIMIT ?",
                                  (user_id, bot_id, limit))

    async def for_project(self, user_id: str, project_id: str, limit: int) -> tuple[Note, ...]:
        """A project's notes (its page, ``get_project``), in the Notes tab's order."""
        return await self.list(user_id, limit=limit, project_id=project_id)

    async def count_for_project(self, user_id: str, project_id: str) -> int:
        """How many live notes a project has (the page's tab count), counted in SQL."""
        async with db_session(self._config) as db:
            row = await (await db.execute(
                f"SELECT COUNT(*) FROM notes WHERE {_LIVE} AND project_id = ?", (user_id, project_id))).fetchone()
        return int(row[0])

    async def update(
        self, user_id: str, note_id: str, patch: NotePatch, *, base_revision: int | None = None,
    ) -> Note | None:
        """``None``: no such note. ``RevisionConflict``: ``base_revision`` (what
        the caller read) is stale, or another write landed between this read
        and this write — the stored note rides on the exception."""
        current = await self.get(user_id, note_id)
        if current is None:
            return None
        if base_revision is not None and base_revision != current.revision:
            raise RevisionConflict(current)
        updated = replace(current, **dict(patch.changes), revision=current.revision + 1, updated_at=_now_iso())
        columns = tuple(c for name in patch.changes for c in _PATCH_COLUMNS[name]) + ("revision", "updated_at")
        return await self._swap(current, updated, columns)

    async def keep(self, user_id: str, note_id: str) -> Note | None:
        """The user vouches for a web-made note (HTTP only, never a tool). Taint
        isn't content, so the revision stays and an open editor isn't disturbed."""
        current = await self.get(user_id, note_id)
        if current is None:
            return None
        return await self._swap(current, replace(current, tainted=False, updated_at=_now_iso()),
                                ("tainted", "updated_at"))

    async def set_project(self, user_id: str, note_id: str, project_id: str | None) -> Note | None:
        """Link the note to one of the user's projects, or unlink it (``None``).
        The link isn't content, so the revision stays and an open editor's
        next save still lands (H12). A save that lands between this read and
        this write is no reason to refuse: the link goes onto the newer copy.
        ``None``: no such note. ``ValueError``: not one of the user's projects."""
        current = await self.get(user_id, note_id)
        if current is None:
            return None
        try:
            return await self._link(current, project_id)
        except RevisionConflict as conflict:
            return await self._link(conflict.current, project_id)

    async def _link(self, current: Note, project_id: str | None) -> Note | None:
        return await self._swap(current, replace(current, project_id=project_id, updated_at=_now_iso()),
                                _LINK_COLUMNS)

    async def delete(self, user_id: str, note_id: str) -> bool:
        now = _now_iso()
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE notes SET deleted_at = ?, updated_at = ? WHERE id = ? AND {_LIVE}",
                (now, now, note_id, user_id),
            )
            await db.commit()
        return cursor.rowcount > 0

    async def _swap(self, current: Note, updated: Note, columns: tuple[str, ...]) -> Note | None:
        """Write ``columns`` only if the row still has ``current.revision``. A
        new ``project_id`` among them must be the user's. It is checked in the
        same session as the write (``ValueError`` otherwise, and nothing is
        written)."""
        dek = await get_user_dek(self._config, current.user_id)
        assignments = ", ".join(f"{column} = ?" for column in columns)
        async with db_session(self._config) as db:
            if "project_id" in columns:
                await require_project(db, current.user_id, updated.project_id)
            cursor = await db.execute(
                f"UPDATE notes SET {assignments} WHERE id = ? AND {_LIVE} AND revision = ?",
                (*(_encode(updated, column, dek) for column in columns), current.id, current.user_id,
                 current.revision),
            )
            await db.commit()
        if cursor.rowcount:
            return updated
        latest = await self.get(current.user_id, current.id)
        if latest is None:
            return None
        raise RevisionConflict(latest)

    async def _select(self, user_id: str, where: str, params: tuple) -> tuple[Note, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_SELECT} FROM notes {where}", params)).fetchall()
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_note(row, dek) for row in rows)
