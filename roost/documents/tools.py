"""The document tools over the user's shared documents (M2 D2; projects hub
H12). Pydantic arguments, provenance (bot + taint) on every new document,
escaped results, exact-or-ask names (a near miss never changes a document),
and a document's taint taints the run that reads it — an uploaded PDF is
outside content. A document may belong to one of the user's projects (never
General): ``create_doc`` and ``create_sheet`` take one, a PDF made from a doc
lands in the doc's, and ``set_document_project`` moves one without a new
revision, so an open editor still saves."""

from __future__ import annotations

import html
from typing import Any

from pydantic import ValidationError

from roost.constants import DOCUMENT_LIST_LIMIT, MAX_SHEET_CELLS_PER_CALL, MAX_SHEET_COLS, MAX_SHEET_ROWS_PER_CALL
from roost.documents.cells import LAST_CELL
from roost.documents.format import KIND_LABEL, document_line, document_list_text
from roost.documents.models import Document, DocumentMeta
from roost.documents.service import DocumentService
from roost.documents.tool_args import (
    AppendToDocArgs, CreateDocArgs, CreateSheetArgs, DocumentRefArgs, ListDocumentsArgs, MakePdfArgs,
    SetDocumentProjectArgs, UpdateSheetCellsArgs,
)
from roost.money.models import Project
from roost.tags.record import bot_record_tags
from roost.constants import PROJECT_TAG_PREFIX
from roost.projects.refs import id_of, project_ref, project_suffix, project_taint
from roost.projects.service import ProjectService
from roost.records.resolver import NamedRef, resolve
from roost.records.revision import RevisionConflict
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome

CHANGED_WHILE_WRITING_TEXT = "Refused: that document changed while I was writing. Read it again first."
_ACTIVITY = {
    "list_documents": "checking your documents", "read_document": "reading a document",
    "create_doc": "writing a doc", "create_sheet": "making a sheet", "append_to_doc": "adding to a doc",
    "update_sheet_cells": "updating a sheet", "delete_document": "deleting a document",
    "make_pdf_from_doc": "making a PDF", "set_document_project": "filing a document in a project",
}
_NEEDS = {
    "list_documents": "an optional kind (doc, sheet or pdf) and project",
    "read_document": "the document (its id or title)",
    "create_doc": "a title and markdown text (and optionally a project)",
    "create_sheet": f"rows (1 to {MAX_SHEET_ROWS_PER_CALL}, each at most {MAX_SHEET_COLS} cells) and a title",
    "append_to_doc": "the doc (its id or title) and the markdown to add",
    "update_sheet_cells": f"the sheet (its id or title) and 1 to {MAX_SHEET_CELLS_PER_CALL} cells from A1 to "
                          f"{LAST_CELL}, like {{\"cell\": \"B3\", \"value\": 35}}",
    "delete_document": "the document (its id or title)",
    "make_pdf_from_doc": "the doc (its id or title)",
    "set_document_project": "the document (its id or title) and the project (its name or id; '' takes it out)",
}


def _tags(ctx: RecordContext, project: Project | None, topics: list[str]) -> tuple[str, ...]:
    return bot_record_tags(ctx, None if project is None else project.name, topics)


def _pdf_tags(ctx: RecordContext, source_tags: tuple[str, ...]) -> tuple[str, ...]:
    """A PDF made from a doc: this bot's tag, and the doc's project tag (it lands in the doc's project)."""
    project = tuple(tag for tag in source_tags if tag.startswith(f"{PROJECT_TAG_PREFIX}:"))
    return (*bot_record_tags(ctx, None, ()), *project)


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


_CHANGES = frozenset({"append_to_doc", "update_sheet_cells", "delete_document", "set_document_project"})


def _title(raw: str | None, fallback: str) -> str:
    return (raw or "").strip() or fallback


def _match(metas: tuple[DocumentMeta, ...], ref: str, change: bool) -> DocumentMeta | ToolOutcome:
    """Id, exact title or a unique part of it (harvested resolver); a lone near
    miss may be read but never changed. A refusal that lists titles carries
    those documents' taint (M1 D3)."""
    by_id = next((meta for meta in metas if meta.id == ref.strip()), None)
    if by_id is not None:
        return by_id
    by_key = {meta.id: meta for meta in metas}
    hit = resolve(ref, [NamedRef(meta.id, meta.title) for meta in metas])
    if hit.resolved is not None and (hit.reason != "fuzzy" or not change):
        return by_key[hit.resolved.id]
    shown = tuple(by_key[c.id] for c in hit.candidates[:5])
    listed, tainted = "; ".join(document_line(meta) for meta in shown), any(meta.tainted for meta in shown)
    if hit.reason == "fuzzy":
        return ToolOutcome(f"Refused: no document is called “{_escape(ref)}”. Did you mean {listed}? Say it exactly.",
                           tainted=tainted)
    if hit.reason == "multi":
        return ToolOutcome(f"Refused: several documents match “{_escape(ref)}”: {listed}. Say which one (its id).",
                           tainted=tainted)
    return ToolOutcome(f"Refused: no document matches “{_escape(ref)}”.")


def _saved(found: Document, meta: DocumentMeta | None, verb: str) -> ToolOutcome:
    if meta is None:
        return ToolOutcome("Refused: that document is gone.", tainted=found.meta.tainted)
    return ToolOutcome(f"{verb} “{_escape(found.meta.title)}” (revision {meta.revision}).", tainted=found.meta.tainted)


def _filed(meta: DocumentMeta, project: Project | None) -> str:
    title = _escape(meta.title)
    if project is None:
        return f"“{title}” is in no project now."
    return f"Moved “{title}” to the project “{_escape(project.name)}”."


class DocumentTools:
    names = frozenset(_ACTIVITY)

    def __init__(self, service: DocumentService, projects: ProjectService) -> None:
        self._service = service
        self._projects = projects

    def activity(self, name: str) -> str:
        return _ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        handlers = {
            "list_documents": self._list, "read_document": self._read, "create_doc": self._create_doc,
            "create_sheet": self._create_sheet, "append_to_doc": self._append, "update_sheet_cells": self._cells,
            "delete_document": self._delete, "make_pdf_from_doc": self._make_pdf,
            "set_document_project": self._set_project,
        }
        try:
            return await handlers[name](arguments, ctx)
        except ValidationError:
            return ToolOutcome(f"Refused: {name} needs {_NEEDS[name]}.")
        except RevisionConflict:
            return ToolOutcome(CHANGED_WHILE_WRITING_TEXT)
        except ValueError as exc:   # a damaged blob, a bad A1 reference, PdfError, no such project
            return ToolOutcome(f"Refused: {_escape(str(exc))}")

    async def _list(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = ListDocumentsArgs.model_validate(arguments)
        project = await project_ref(self._projects, ctx.user_id, args.project, change=False)
        if isinstance(project, ToolOutcome):
            return project
        metas = await self._service.list(ctx.user_id, args.kind, project_id=id_of(project))
        shown = metas[:DOCUMENT_LIST_LIMIT]
        return ToolOutcome(document_list_text(shown, len(metas)), tainted=any(meta.tainted for meta in shown))

    async def _read(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        found = await self._find(ctx.user_id, DocumentRefArgs.model_validate(arguments).document, change=False)
        if isinstance(found, ToolOutcome):
            return found
        text = await self._service.text(found)
        return ToolOutcome(f"{document_line(found.meta)} revision={found.meta.revision}\n\n{_escape(text)}",
                           tainted=found.meta.tainted)

    async def _create_doc(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = CreateDocArgs.model_validate(arguments)
        project = await project_ref(self._projects, ctx.user_id, args.project, change=True)
        if isinstance(project, ToolOutcome):
            return project
        meta = await self._service.create_doc(ctx.user_id, _title(args.title, "Untitled doc"), args.markdown,
                                              created_by_bot=ctx.bot_id, tainted=ctx.tainted,
                                              project_id=id_of(project), tags=_tags(ctx, project, args.tags))
        return ToolOutcome(f"Created doc: {document_line(meta)}. It's on the Board's Documents tab."
                           f"{project_suffix(project)}", created=True, tainted=project_taint(project))

    async def _create_sheet(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = CreateSheetArgs.model_validate(arguments)
        project = await project_ref(self._projects, ctx.user_id, args.project, change=True)
        if isinstance(project, ToolOutcome):
            return project
        meta = await self._service.create_sheet(ctx.user_id, _title(args.title, "Untitled sheet"), args.rows,
                                                created_by_bot=ctx.bot_id, tainted=ctx.tainted,
                                                project_id=id_of(project), tags=_tags(ctx, project, args.tags))
        return ToolOutcome(f"Created sheet: {document_line(meta)} with {len(args.rows)} rows."
                           f"{project_suffix(project)}", created=True, tainted=project_taint(project))

    async def _append(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = AppendToDocArgs.model_validate(arguments)
        found = await self._find_kind(ctx.user_id, args.document, "doc")
        if isinstance(found, ToolOutcome):
            return found
        return _saved(found, await self._service.append_markdown(ctx.user_id, found, args.markdown), "Added to")

    async def _cells(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = UpdateSheetCellsArgs.model_validate(arguments)
        found = await self._find_kind(ctx.user_id, args.document, "sheet")
        if isinstance(found, ToolOutcome):
            return found
        edits = [{"cell": edit.cell.upper(), "value": edit.value, "formula": edit.formula} for edit in args.cells]
        return _saved(found, await self._service.set_cells(ctx.user_id, found, edits), f"Updated {len(edits)} cells in")

    async def _delete(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        found = await self._find(ctx.user_id, DocumentRefArgs.model_validate(arguments).document, change=True)
        if isinstance(found, ToolOutcome):
            return found
        await self._service.delete(ctx.user_id, found.meta.id)
        return ToolOutcome(f"Deleted: “{_escape(found.meta.title)}”.", tainted=found.meta.tainted)

    async def _make_pdf(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = MakePdfArgs.model_validate(arguments)
        found = await self._find_kind(ctx.user_id, args.document, "doc")
        if isinstance(found, ToolOutcome):
            return found
        meta = await self._service.make_pdf(ctx.user_id, found, _title(args.title, found.meta.title),
                                            created_by_bot=ctx.bot_id, tainted=ctx.tainted,
                                            tags=_pdf_tags(ctx, found.meta.tags))
        return ToolOutcome(f"Created PDF: {document_line(meta)}", created=True, tainted=found.meta.tainted)

    async def _set_project(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        """H12: link or unlink ('' ) without a new revision (``DocumentService.set_project``)."""
        args = SetDocumentProjectArgs.model_validate(arguments)
        match = _match(await self._service.list(ctx.user_id), args.document, change=True)
        if isinstance(match, ToolOutcome):
            return match
        project = await project_ref(self._projects, ctx.user_id, args.project, change=True)
        if isinstance(project, ToolOutcome):
            return project
        meta = await self._service.set_project(ctx.user_id, match.id, id_of(project))
        if meta is None:
            return ToolOutcome("Refused: that document is gone.", tainted=match.tainted)
        return ToolOutcome(_filed(meta, project), tainted=match.tainted or project_taint(project))

    async def target_title(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> str | None:
        """The change check: the stored title of the document a change names, or ``None``."""
        if name not in _CHANGES:
            return None
        try:
            ref = DocumentRefArgs.model_validate(arguments).document
        except ValidationError:
            return None
        match = _match(await self._service.list(ctx.user_id), ref, change=True)
        return None if isinstance(match, ToolOutcome) else match.title

    async def _find_kind(self, user_id: str, ref: str, kind: str) -> Document | ToolOutcome:
        found = await self._find(user_id, ref, change=True)
        if isinstance(found, ToolOutcome) or found.meta.kind == kind:
            return found
        return ToolOutcome(f"Refused: “{_escape(found.meta.title)}” is a {KIND_LABEL[found.meta.kind]}, "
                           f"not a {KIND_LABEL[kind]}.", tainted=found.meta.tainted)

    async def _find(self, user_id: str, ref: str, *, change: bool) -> Document | ToolOutcome:
        match = _match(await self._service.list(user_id), ref, change)
        if isinstance(match, ToolOutcome):
            return match
        document = await self._service.get(user_id, match.id)
        return document if document is not None else ToolOutcome("Refused: that document is gone.")
