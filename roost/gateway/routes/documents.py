"""Documents over HTTP — the Board's Documents tab (M2 D2, D4), in the shape of
LazyClaw's ``gateway/routes/{docs,sheets,pdf}.py``: list, read, create, save
with a revision compare-and-swap (409 carries the current copy), the raw PDF
for the viewer, a PDF upload, Keep and delete. Same ``DocumentService`` as the
tools, so every change publishes ``documents_changed``. An uploaded PDF is
outside content (spec §8.2), so it is stored tainted until the user Keeps it."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from roost.constants import (
    MAX_DOC_MARKDOWN_LENGTH, MAX_DOCUMENT_PAYLOAD_CHARS, MAX_DOCUMENT_TITLE_LENGTH, MAX_PDF_BYTES,
    MAX_RECORD_ID_LENGTH,
)
from roost.documents.cells import LAST_CELL, SheetRows, sheet_cells_in_bounds
from roost.documents.format import document_detail_out, document_out
from roost.documents.models import Document, DocumentChange, DocumentKind
from roost.documents.pdf_ops import PdfError
from roost.documents.render import pdf_bytes_of
from roost.documents.service import DocumentService
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.gateway.routes.projects import ProjectLinkIn, refuse_general
from roost.records.revision import RevisionConflict

documents_router = APIRouter(prefix="/api/documents", tags=["documents"])
DOCUMENT_CONFLICT_TEXT = "This document changed since you opened it."
_PDF_MEDIA = "application/pdf"
_SNAPSHOT_KEY = {"doc": "body", "sheet": "sheets"}   # what a Univer snapshot of each kind must carry


class DocumentCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["doc", "sheet"]
    title: str = Field(min_length=1, max_length=MAX_DOCUMENT_TITLE_LENGTH)
    markdown: str = Field(default="", max_length=MAX_DOC_MARKDOWN_LENGTH)
    rows: SheetRows | None = None
    project_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)   # one of the user's (H12)


class DocumentSaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=MAX_DOCUMENT_TITLE_LENGTH)
    payload: dict[str, Any] | None = None


def _service(request: Request) -> DocumentService:
    return request.app.state.documents


def _unreadable(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


async def _document(request: Request, user_id: str, document_id: str) -> Document:
    document = await _service(request).get(user_id, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def _payload_body(kind: str, payload: dict[str, Any] | None) -> str | None:
    if payload is None:
        return None
    if kind == "pdf":
        raise HTTPException(status_code=422, detail="A PDF's pages can't be edited here.")
    if not isinstance(payload.get(_SNAPSHOT_KEY[kind]), dict):
        raise HTTPException(status_code=422, detail=f"That isn't a {kind} snapshot.")
    if kind == "sheet" and not sheet_cells_in_bounds(payload):
        raise HTTPException(status_code=422, detail=f"A sheet's cells go from A1 to {LAST_CELL}.")
    text = json.dumps(payload)
    if len(text) > MAX_DOCUMENT_PAYLOAD_CHARS:
        raise HTTPException(status_code=413, detail="This document is too big to save.")
    return text


async def _pdf_body(request: Request) -> bytes:
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != _PDF_MEDIA:
        raise HTTPException(status_code=415, detail="Upload a PDF file (Content-Type: application/pdf).")
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="That PDF is too big (20 MB at most).")
    data = await request.body()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="That PDF is too big (20 MB at most).")
    return data


@documents_router.get("")
async def list_documents(request: Request, user: CurrentUser, kind: DocumentKind | None = None,
                         project_id: str | None = Query(default=None, max_length=MAX_RECORD_ID_LENGTH)):
    """``project_id`` keeps one project's documents (H12); an empty one is no filter."""
    metas = await _service(request).list(user.id, kind, project_id=project_id or None)
    return [document_out(meta) for meta in metas]


@documents_router.get("/{document_id}")
async def get_document(document_id: str, request: Request, user: CurrentUser):
    try:
        return document_detail_out(await _document(request, user.id, document_id))
    except ValueError as exc:
        raise _unreadable(exc) from exc


@documents_router.get("/{document_id}/text")
async def get_document_text(document_id: str, request: Request, user: CurrentUser):
    document = await _document(request, user.id, document_id)
    try:
        return {"text": await _service(request).text(document)}
    except ValueError as exc:   # a damaged blob, or a PDF the extractor can't read (PdfError)
        raise _unreadable(exc) from exc


@documents_router.get("/{document_id}/pdf")
async def get_document_pdf(document_id: str, request: Request, user: CurrentUser) -> Response:
    document = await _document(request, user.id, document_id)
    if document.meta.kind != "pdf":
        raise HTTPException(status_code=404, detail="Not a PDF")
    try:
        data = pdf_bytes_of(document)
    except ValueError as exc:
        raise _unreadable(exc) from exc
    return Response(content=data, media_type=_PDF_MEDIA,
                    headers={"Content-Disposition": "inline", "Cache-Control": "no-store"})


@documents_router.post("", status_code=201, dependencies=[RequireOrigin])
async def create_document(body: DocumentCreateIn, request: Request, user: CurrentUser):
    service, title = _service(request), body.title.strip()
    try:
        await refuse_general(request, user.id, body.project_id)
        if body.kind == "doc":
            meta = await service.create_doc(user.id, title, body.markdown, project_id=body.project_id)
        else:
            meta = await service.create_sheet(user.id, title, body.rows or [], project_id=body.project_id)
    except ValueError as exc:   # General, or not one of the user's projects
        raise _unreadable(exc) from exc
    return document_out(meta)


@documents_router.post("/pdf", status_code=201, dependencies=[RequireOrigin])
async def upload_pdf(request: Request, user: CurrentUser,
                     title: str = Query(min_length=1, max_length=MAX_DOCUMENT_TITLE_LENGTH)):
    data = await _pdf_body(request)
    try:
        meta = await _service(request).create_pdf(user.id, title.strip(), data, tainted=True)
    except PdfError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return document_out(meta)


@documents_router.put("/{document_id}", dependencies=[RequireOrigin])
async def save_document(document_id: str, body: DocumentSaveIn, request: Request, user: CurrentUser):
    service = _service(request)
    meta = await service.get_meta(user.id, document_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Document not found")
    change = DocumentChange(base_revision=body.base_revision, body=_payload_body(meta.kind, body.payload),
                            title=body.title.strip() if body.title else None)
    if change.title is None and change.body is None:
        raise HTTPException(status_code=422, detail="Send a title or a payload to save.")
    try:
        saved = await service.save(user.id, document_id, change)
    except RevisionConflict as exc:
        return JSONResponse(status_code=409, content={"detail": DOCUMENT_CONFLICT_TEXT,
                                                      "current": document_detail_out(exc.current)})
    if saved is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document_out(saved)


@documents_router.put("/{document_id}/project", dependencies=[RequireOrigin])
async def set_document_project(document_id: str, body: ProjectLinkIn, request: Request, user: CurrentUser):
    """Link the document to one of the user's projects, or unlink it
    (``null``). The revision stays, so an open editor's next autosave still
    lands (H12)."""
    try:
        await refuse_general(request, user.id, body.project_id)
        meta = await _service(request).set_project(user.id, document_id, body.project_id)
    except ValueError as exc:   # General, or not one of the user's projects
        raise _unreadable(exc) from exc
    if meta is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document_out(meta)


@documents_router.post("/{document_id}/keep", dependencies=[RequireOrigin])
async def keep_document(document_id: str, request: Request, user: CurrentUser):
    """Keep: the user vouches for a web-made or uploaded document (no tool can)."""
    meta = await _service(request).keep(user.id, document_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document_out(meta)


@documents_router.delete("/{document_id}", status_code=204, dependencies=[RequireOrigin])
async def delete_document(document_id: str, request: Request, user: CurrentUser) -> None:
    if not await _service(request).delete(user.id, document_id):
        raise HTTPException(status_code=404, detail="Document not found")
