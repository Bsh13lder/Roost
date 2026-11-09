"""Rendering a document for a tool result or the Board (M2 D2). Titles are the
user's (or a page's) data: escaped here, by their producer, before any prompt."""

from __future__ import annotations

import html
from types import MappingProxyType
from typing import Any, Mapping

from roost.documents.models import Document, DocumentMeta
from roost.documents.render import snapshot_of

KIND_LABEL: Mapping[str, str] = MappingProxyType({"doc": "doc", "sheet": "sheet", "pdf": "PDF"})
WEB_MARK = " [from web content]"


def document_line(meta: DocumentMeta) -> str:
    pages = f", {meta.pages} pages" if meta.pages else ""
    web = WEB_MARK if meta.tainted else ""
    return (f"[{KIND_LABEL[meta.kind]}] “{html.escape(meta.title, quote=True)}” "
            f"(updated {meta.updated_at[:10]}{pages}){web} id={meta.id}")


def document_list_text(metas: tuple[DocumentMeta, ...], total: int) -> str:
    if not metas:
        return "No documents yet."
    more = f"\n…and {total - len(metas)} more." if total > len(metas) else ""
    return "\n".join(f"- {document_line(meta)}" for meta in metas) + more


def document_out(meta: DocumentMeta) -> dict[str, Any]:
    return {
        "id": meta.id, "kind": meta.kind, "title": meta.title, "pages": meta.pages, "revision": meta.revision,
        "created_at": meta.created_at, "updated_at": meta.updated_at, "created_by_bot": meta.created_by_bot,
        "tainted": meta.tainted, "project_id": meta.project_id, "tags": list(meta.tags),
    }


def document_detail_out(document: Document) -> dict[str, Any]:
    """Raises ValueError (plain text) when the stored copy can't be read."""
    payload = None if document.meta.kind == "pdf" else snapshot_of(document)
    return {**document_out(document.meta), "payload": payload}
