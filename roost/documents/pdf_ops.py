# SPDX-License-Identifier: MIT
# Harvested from LazyClaw lazyclaw/pdf/ops.py lines 1-178, 582-620 @ 21e1002, adapted for Roost

"""Pure functions on PDF bytes (input bytes → output bytes/str).

Every function is stateless: it takes raw PDF ``bytes`` (and parameters) and
returns either raw ``bytes`` (a new PDF) or extracted data. No I/O, no encryption,
no database — the store and skills layer those on top.

Engines (permissive licences only):
- pypdf (BSD): structural ops — page count, merge/split/rotate/delete, AcroForm
  fields + fill, flatten, page-overlay merge.
- pdfplumber (MIT): text + table extraction.
- reportlab (BSD): overlay generation (text/signature stamping, redaction
  rectangles) and from-scratch PDF generation.

NEVER import PyMuPDF/fitz or borb (AGPL) here.

All operations defend against malformed input by raising :class:`PdfError`
(a ``ValueError`` subclass) with a user-facing message, rather than leaking a
raw library traceback. Output PDFs always begin with the ``%PDF`` magic.
"""

from __future__ import annotations

import io
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class PdfError(ValueError):
    """Raised when a PDF operation cannot be completed (bad input, etc.)."""


_PDF_MAGIC = b"%PDF"


def _validate_pdf_bytes(data: bytes) -> None:
    """Fail fast on obviously non-PDF input."""
    if not isinstance(data, (bytes, bytearray)):
        raise PdfError("PDF data must be bytes.")
    if not data:
        raise PdfError("PDF data is empty.")
    # The %PDF header may be preceded by a few junk bytes in the wild; accept
    # it anywhere in the first 1 KB rather than only at offset 0.
    if _PDF_MAGIC not in bytes(data[:1024]):
        raise PdfError("Data does not look like a PDF (missing %PDF header).")


def is_pdf(data: bytes) -> bool:
    """True if *data* carries the ``%PDF`` magic within its first 1 KB."""
    try:
        _validate_pdf_bytes(data)
        return True
    except PdfError:
        return False


# ---------------------------------------------------------------------------
# pypdf helpers
# ---------------------------------------------------------------------------

def _tolerant_reader_cls():
    """A ``PdfReader`` subclass that survives indirect-to-indirect object bodies.

    pypdf 6.x made :pyattr:`IndirectObject.indirect_reference` a *read-only*
    property. Some real-world PDFs (certain scanners / form generators) emit an
    object whose body is a *bare* indirect reference, e.g.::

        4 0 obj
        5 0 R
        endobj

    When pypdf resolves such an object it parses it as an ``IndirectObject`` and
    then, in ``cache_indirect_object``, attempts ``obj.indirect_reference = ...``
    on it — which now raises ``AttributeError: property 'indirect_reference' of
    'IndirectObject' object has no setter`` and aborts every read/clone/stamp.

    The fix collapses the chain at cache time: when the object being cached *is*
    an ``IndirectObject``, resolve it to its concrete target (one hop, with
    self-reference and unresolvable targets degrading to ``NullObject``) before
    delegating to the parent — so a real ``PdfObject`` is cached and the
    read-only property is never written. Built lazily so the import cost (and
    pypdf's exact class layout) is paid only when a PDF op actually runs.
    """
    from pypdf import PdfReader
    from pypdf.generic import IndirectObject, NullObject

    class _TolerantPdfReader(PdfReader):
        def cache_indirect_object(self, generation, idnum, obj):  # type: ignore[override]
            if isinstance(obj, IndirectObject):
                if obj.idnum == idnum and obj.generation == generation:
                    # Self-reference (e.g. "4 0 obj  4 0 R"): cannot resolve —
                    # substitute a null rather than recurse forever.
                    obj = NullObject()
                else:
                    try:
                        resolved = obj.get_object()
                    except Exception:  # noqa: BLE001 — missing / circular target
                        resolved = None
                    # A concrete object collapses the chain; anything else
                    # (missing target, deeper indirection) becomes null so the
                    # read-only ``indirect_reference`` property is never set.
                    obj = (
                        resolved
                        if resolved is not None and not isinstance(resolved, IndirectObject)
                        else NullObject()
                    )
            return super().cache_indirect_object(generation, idnum, obj)

    return _TolerantPdfReader


def _reader(data: bytes):
    """Build a pypdf reader, surfacing parse errors as :class:`PdfError`.

    Uses a tolerant reader (see :func:`_tolerant_reader_cls`) so PDFs carrying
    bare indirect-to-indirect object bodies load instead of crashing on pypdf
    6.x's read-only ``indirect_reference`` property.
    """
    from pypdf.errors import PdfReadError

    _validate_pdf_bytes(data)
    reader_cls = _tolerant_reader_cls()
    try:
        return reader_cls(io.BytesIO(bytes(data)))
    except PdfReadError as exc:
        raise PdfError(f"Could not read PDF: {exc}") from exc
    except Exception as exc:  # malformed xref, encryption, etc.
        raise PdfError(f"Could not read PDF: {exc}") from exc


def _writer_to_bytes(writer) -> bytes:
    buf = io.BytesIO()
    writer.write(buf)
    out = buf.getvalue()
    if not out.startswith(_PDF_MAGIC):
        raise PdfError("Internal error: produced bytes are not a valid PDF.")
    return out


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------

def page_count(data: bytes) -> int:
    """Number of pages in the PDF."""
    reader = _reader(data)
    return len(reader.pages)


def extract_text(data: bytes) -> str:
    """Extract all text, joining pages with a form-feed + newline.

    Uses pdfplumber (MIT). Pages with no extractable text yield an empty
    string for that page. Best-effort: per-page failures are logged and
    skipped rather than aborting the whole extraction.
    """
    import pdfplumber

    _validate_pdf_bytes(data)
    parts: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(bytes(data))) as pdf:
            for i, page in enumerate(pdf.pages):
                try:
                    parts.append(page.extract_text() or "")
                except Exception as exc:  # noqa: BLE001 — per-page resilience
                    logger.warning("extract_text failed on page %d: %s", i, exc)
                    parts.append("")
    except Exception as exc:
        raise PdfError(f"Could not extract text: {exc}") from exc
    # Form-feed separates pages; newline keeps it readable.
    return "\f\n".join(parts)

def generate_from_text(text: str, title: str | None = None) -> bytes:
    """Generate a simple multi-paragraph PDF from plain text.

    Blank lines separate paragraphs. An optional *title* is rendered as a
    heading. Uses reportlab's Platypus flowables with automatic page breaks.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    from xml.sax.saxutils import escape

    if text is None:
        text = ""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, title=(title or "Document"))
    styles = getSampleStyleSheet()
    story: list[Any] = []
    if title:
        story.append(Paragraph(escape(str(title)), styles["Title"]))
        story.append(Spacer(1, 12))
    paragraphs = str(text).split("\n\n")
    for para in paragraphs:
        # Preserve single line breaks inside a paragraph as <br/>.
        safe = escape(para.strip()).replace("\n", "<br/>")
        if not safe:
            story.append(Spacer(1, 12))
            continue
        story.append(Paragraph(safe, styles["BodyText"]))
        story.append(Spacer(1, 6))
    if not story:
        story.append(Paragraph("(empty)", styles["BodyText"]))
    try:
        doc.build(story)
    except Exception as exc:
        raise PdfError(f"Could not generate PDF: {exc}") from exc
    out = buf.getvalue()
    if not out.startswith(_PDF_MAGIC):
        raise PdfError("Internal error: generated bytes are not a valid PDF.")
    return out
