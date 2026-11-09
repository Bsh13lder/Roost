"""Document domain model (M2 D2, D5) — frozen dataclasses. One record per file:
a doc or a sheet is a Univer snapshot (JSON), a PDF its bytes (base64). Field
meanings follow LazyClaw's docs / sheets / pdf_files (``name`` is ``title``
here) so M4 can import the user's documents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DocumentKind = Literal["doc", "sheet", "pdf"]
DOCUMENT_KINDS: tuple[DocumentKind, ...] = ("doc", "sheet", "pdf")


@dataclass(frozen=True)
class DocumentMeta:
    id: str
    user_id: str
    kind: DocumentKind
    title: str
    pages: int | None             # PDFs only
    revision: int                 # bumped by every save: the compare-and-swap counter
    created_at: str
    updated_at: str
    created_by_bot: str | None    # NULL: the user, or a retired bot
    tainted: bool                 # written by a run that read outside content, or an uploaded file
    project_id: str | None = None  # one of the user's projects (H12); linking never bumps the revision
    tags: tuple[str, ...] = ()     # sealed (documents:tags); a bot's document carries bot:<slug> and its topics


@dataclass(frozen=True)
class Document:
    meta: DocumentMeta
    body: str                     # decrypted: the snapshot JSON (doc/sheet) or base64 bytes (pdf)


@dataclass(frozen=True)
class DocumentDraft:
    kind: DocumentKind
    title: str
    body: str
    pages: int | None = None
    project_id: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class DocumentChange:
    base_revision: int            # the revision the writer read
    body: str | None = None
    title: str | None = None
    pages: int | None = None
