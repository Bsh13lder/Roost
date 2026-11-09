"""``DocumentService`` — the documents store plus its live frame (M2 D2/D4):
new docs from markdown, sheets from rows, PDFs from bytes or from a doc, saves,
and what a document reads as. Tools and HTTP routes both go through it, so the
Board updates whoever changed a document. PDF work runs off the event loop."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any, Literal, Mapping, Sequence

from roost.constants import DOCUMENT_READ_TIMEOUT_SECONDS
from roost.documents.doc_markdown import append_markdown, doc_from_markdown, doc_plain_text
from roost.documents.models import Document, DocumentChange, DocumentDraft, DocumentKind, DocumentMeta
from roost.documents.pdf_ops import generate_from_text, page_count
from roost.documents.render import document_text, snapshot_of
from roost.documents.sheet_snapshot import set_cells
from roost.documents.sheet_text import sheet_from_rows
from roost.documents.store import DocumentStore
from roost.events.hub import EventHub

DocumentEvent = Literal["created", "updated", "deleted"]
READ_TIMEOUT_TEXT = "This document took too long to read."


class DocumentService:
    def __init__(self, store: DocumentStore, events: EventHub) -> None:
        self._store = store
        self._events = events

    async def list(self, user_id: str, kind: DocumentKind | None = None, *,
                   project_id: str | None = None) -> tuple[DocumentMeta, ...]:
        return await self._store.list(user_id, kind, project_id=project_id)

    async def get(self, user_id: str, document_id: str) -> Document | None:
        return await self._store.get(user_id, document_id)

    async def get_meta(self, user_id: str, document_id: str) -> DocumentMeta | None:
        return await self._store.get_meta(user_id, document_id)

    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[DocumentMeta, ...]:
        return await self._store.made_by(user_id, bot_id, limit)

    async def for_project(self, user_id: str, project_id: str, limit: int) -> tuple[DocumentMeta, ...]:
        return await self._store.for_project(user_id, project_id, limit)

    async def create_doc(self, user_id: str, title: str, markdown: str, *, created_by_bot: str | None = None,
                         tainted: bool = False, project_id: str | None = None,
                         tags: tuple[str, ...] = ()) -> DocumentMeta:
        body = json.dumps(doc_from_markdown(title, markdown))
        draft = DocumentDraft("doc", title, body, project_id=project_id, tags=tags)
        return await self._create(user_id, draft, created_by_bot, tainted)

    async def create_sheet(self, user_id: str, title: str, rows: Sequence[Sequence[Any]], *,
                           created_by_bot: str | None = None, tainted: bool = False,
                           project_id: str | None = None, tags: tuple[str, ...] = ()) -> DocumentMeta:
        body = json.dumps(sheet_from_rows(title, rows))
        draft = DocumentDraft("sheet", title, body, project_id=project_id, tags=tags)
        return await self._create(user_id, draft, created_by_bot, tainted)

    async def create_pdf(self, user_id: str, title: str, data: bytes, *, created_by_bot: str | None = None,
                         tainted: bool = False, project_id: str | None = None,
                         tags: tuple[str, ...] = ()) -> DocumentMeta:
        """Raises ``PdfError`` (a ValueError with a plain message) for a non-PDF,
        and ``ValueError`` for a project that isn't the user's."""
        pages = await asyncio.to_thread(page_count, data)
        draft = DocumentDraft("pdf", title, base64.b64encode(data).decode("ascii"), pages=pages,
                              project_id=project_id, tags=tags)
        return await self._create(user_id, draft, created_by_bot, tainted)

    async def make_pdf(self, user_id: str, source: Document, title: str, *, created_by_bot: str | None,
                       tainted: bool, tags: tuple[str, ...] = ()) -> DocumentMeta:
        """A new PDF from a doc's text. It carries the doc's taint (provenance)
        and lands in the doc's project (H12)."""
        data = await asyncio.to_thread(generate_from_text, doc_plain_text(snapshot_of(source)), title)
        return await self.create_pdf(user_id, title, data, created_by_bot=created_by_bot,
                                     tainted=tainted or source.meta.tainted, project_id=source.meta.project_id,
                                     tags=tags)

    async def save(self, user_id: str, document_id: str, change: DocumentChange) -> DocumentMeta | None:
        meta = await self._store.save(user_id, document_id, change)
        if meta is not None:
            await self._changed(user_id, "updated", meta)
        return meta

    async def append_markdown(self, user_id: str, document: Document, markdown: str) -> DocumentMeta | None:
        body = json.dumps(append_markdown(snapshot_of(document), markdown))
        return await self.save(user_id, document.meta.id, DocumentChange(base_revision=document.meta.revision,
                                                                          body=body))

    async def set_cells(self, user_id: str, document: Document,
                        edits: Sequence[Mapping[str, Any]]) -> DocumentMeta | None:
        body = json.dumps(set_cells(snapshot_of(document), [dict(edit) for edit in edits]))
        return await self.save(user_id, document.meta.id, DocumentChange(base_revision=document.meta.revision,
                                                                          body=body))

    async def text(self, document: Document) -> str:
        """What a document reads as, off the event loop. The readers stop at their
        caps; the timeout bounds how long a tool or the Board waits."""
        try:
            return await asyncio.wait_for(asyncio.to_thread(document_text, document), DOCUMENT_READ_TIMEOUT_SECONDS)
        except TimeoutError as exc:
            raise ValueError(READ_TIMEOUT_TEXT) from exc

    async def keep(self, user_id: str, document_id: str) -> DocumentMeta | None:
        meta = await self._store.keep(user_id, document_id)
        if meta is not None:
            await self._changed(user_id, "updated", meta)
        return meta

    async def set_project(self, user_id: str, document_id: str, project_id: str | None) -> DocumentMeta | None:
        """Link or unlink (``None``). The store's ``ValueError`` (not one of the
        user's projects) passes through, and then nothing is published."""
        meta = await self._store.set_project(user_id, document_id, project_id)
        if meta is not None:
            await self._changed(user_id, "updated", meta)
        return meta

    async def delete(self, user_id: str, document_id: str) -> bool:
        meta = await self._store.get_meta(user_id, document_id)
        if meta is None or not await self._store.delete(user_id, document_id):
            return False
        await self._changed(user_id, "deleted", meta)
        return True

    async def _create(self, user_id: str, draft: DocumentDraft, created_by_bot: str | None,
                      tainted: bool) -> DocumentMeta:
        meta = await self._store.create(user_id, draft, created_by_bot=created_by_bot, tainted=tainted)
        await self._changed(user_id, "created", meta)
        return meta

    async def _changed(self, user_id: str, change: DocumentEvent, meta: DocumentMeta) -> None:
        await self._events.publish(user_id, {"type": "documents_changed", "change": change,
                                             "document_id": meta.id, "kind": meta.kind})
