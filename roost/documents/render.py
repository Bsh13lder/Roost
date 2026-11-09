"""Reading a stored document (M2 D2): its snapshot or its PDF bytes, and the
text ``read_document`` and ``GET /api/documents/{id}/text`` show — a doc as
markdown, a sheet as a small table, a PDF as its text, capped. Plain text: the
tool escapes it for the model; React escapes it on the Board. Every reader is
bounded by the work it does, not only by what it prints (the gateway has
mem_limit 1g): a sheet renders its capped window, a PDF reads page by page."""

from __future__ import annotations

import base64
import binascii
import io
import json
import logging
from typing import Any

from roost.constants import DOCUMENT_READ_MAX_CHARS, PDF_READ_MAX_PAGES
from roost.documents.doc_markdown import doc_to_markdown
from roost.documents.models import Document
from roost.documents.pdf_ops import PdfError, is_pdf
from roost.documents.sheet_text import format_grid

logger = logging.getLogger(__name__)
UNREADABLE_TEXT = "This document's stored copy could not be read."


def snapshot_of(document: Document) -> dict[str, Any]:
    try:
        value = json.loads(document.body)
    except json.JSONDecodeError as exc:
        raise ValueError(UNREADABLE_TEXT) from exc
    if not isinstance(value, dict):
        raise ValueError(UNREADABLE_TEXT)
    return value


def pdf_bytes_of(document: Document) -> bytes:
    try:
        return base64.b64decode(document.body, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(UNREADABLE_TEXT) from exc


def _page_text(page: Any) -> str:
    """One page's text; ``page.close()`` then frees what pdfplumber parsed. A
    page that fails is logged and read as empty, as in the harvested reader."""
    try:
        return page.extract_text() or ""
    except Exception as exc:  # noqa: BLE001 — per-page resilience
        logger.warning("PDF page %d could not be read: %s", page.page_number, exc)
        return ""
    finally:
        page.close()


def pdf_text(data: bytes) -> str:
    """Roost: the text of a PDF's first pages, joined like the harvested
    ``extract_text`` (form feed + newline). The harvested reader extracts every
    page before anything is cut, so a 1,000-page upload could OOM the gateway.
    This one reads page by page, closes each page, and stops at
    DOCUMENT_READ_MAX_CHARS or after PDF_READ_MAX_PAGES pages."""
    import pdfplumber

    if not is_pdf(data):
        raise PdfError("Data does not look like a PDF (missing %PDF header).")
    parts: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(data), pages=list(range(1, PDF_READ_MAX_PAGES + 1))) as pdf:
            for page in pdf.pages:
                parts.append(_page_text(page))
                if sum(len(part) for part in parts) >= DOCUMENT_READ_MAX_CHARS:
                    break
    except Exception as exc:  # noqa: BLE001 — a damaged file is a plain refusal, as in the harvested reader
        raise PdfError(f"Could not extract text: {exc}") from exc
    return "\f\n".join(parts)


def _capped(text: str) -> str:
    if len(text) <= DOCUMENT_READ_MAX_CHARS:
        return text
    return text[:DOCUMENT_READ_MAX_CHARS] + f"\n…(showing {DOCUMENT_READ_MAX_CHARS} of {len(text)} characters)"


def _pdf_capped(text: str, pages: int | None) -> str:
    """``pdf_text`` stops early, so the full length is unknown: say it is the start."""
    if len(text) < DOCUMENT_READ_MAX_CHARS and (pages or 0) <= PDF_READ_MAX_PAGES:
        return text
    return text[:DOCUMENT_READ_MAX_CHARS] + f"\n…(showing the start of a {pages}-page PDF)"


def document_text(document: Document) -> str:
    """Blocking for a PDF (text extraction): callers run it off the event loop
    (``DocumentService.text``, under a timeout).

    The harvested doc/sheet readers trust the snapshot's shape (a workbook
    with no sheets, a dangling ``sheetOrder`` entry, a cell that isn't a
    dict all raise KeyError/IndexError/AttributeError rather than failing
    gracefully). The PUT boundary rejects an unusable sheet going IN
    (``sheet_cells_in_bounds``), but older or imported data can still reach
    this point, so this is the backstop: any such shape error reads back as
    the same plain ``UNREADABLE_TEXT`` as a damaged blob, not a 500."""
    try:
        if document.meta.kind == "doc":
            return _capped(doc_to_markdown(snapshot_of(document)))
        if document.meta.kind == "sheet":
            return _capped(format_grid(snapshot_of(document)))
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        logger.warning("Document %s's stored %s snapshot could not be read: %s",
                       document.meta.id, document.meta.kind, exc)
        raise ValueError(UNREADABLE_TEXT) from exc
    return _pdf_capped(pdf_text(pdf_bytes_of(document)).strip(), document.meta.pages)
