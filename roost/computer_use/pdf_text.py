"""A PDF's text for ``read_pdf`` (fast pages, slice 5): pdfplumber (MIT, on pypdf, BSD-3), already Roost's PDF
reader for documents (``roost/documents/pdf_ops.py``). Never PyMuPDF.

The bytes come from the bot's own browser and stay in memory. The PDF is a stranger's file, so its reading is
capped: at most ``CU_PDF_PAGES_MAX`` pages, in a worker thread given ``CU_PDF_PARSE_TIMEOUT_S``; anything that is not
a PDF, fails to parse or runs out of time is ``PdfUnreadable``."""

from __future__ import annotations

import asyncio
import io
import logging

from roost.constants import CU_PDF_PAGES_MAX, CU_PDF_PARSE_TIMEOUT_S
from roost.documents.pdf_ops import is_pdf

logger = logging.getLogger(__name__)

PAGE_MARK = "--- page {n} ---"
MORE_PAGES = "(The PDF has {left} more pages that were not read.)"


class PdfUnreadable(Exception):
    """Not a PDF, a PDF that could not be read, or one that took too long."""


def _open(data: bytes):
    import pdfplumber

    return pdfplumber.open(io.BytesIO(data))


def _extract(data: bytes) -> str:
    parts: list[str] = []
    with _open(data) as pdf:
        pages = list(pdf.pages)
        for n, page in enumerate(pages[:CU_PDF_PAGES_MAX], start=1):
            parts += [PAGE_MARK.format(n=n), page.extract_text() or ""]
        if len(pages) > CU_PDF_PAGES_MAX:
            parts.append(MORE_PAGES.format(left=len(pages) - CU_PDF_PAGES_MAX))
    return "\n".join(parts)


async def pdf_text(data: bytes) -> str:
    """The text of the PDF in ``data``, page by page; ``PdfUnreadable`` when it can't be had in time."""
    if not is_pdf(data):
        raise PdfUnreadable("not a PDF")
    try:
        return await asyncio.wait_for(asyncio.to_thread(_extract, data), CU_PDF_PARSE_TIMEOUT_S)
    except asyncio.TimeoutError as exc:
        raise PdfUnreadable("the PDF took too long to read") from exc
    except Exception as exc:  # noqa: BLE001 - a stranger's file: any parser failure is "unreadable"
        logger.warning("A PDF could not be read: %s", type(exc).__name__)
        raise PdfUnreadable("the PDF could not be read") from exc
