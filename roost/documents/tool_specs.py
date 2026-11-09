"""The documents tool specs and gate kinds (M2 D2; projects hub H12). Tool
names and caps follow LazyClaw's docs / sheets / pdf skills; the descriptions
are ours."""

from __future__ import annotations

from roost.llm.types import ToolSpec
from roost.tags.rules import TOPIC_TAGS_SCHEMA
from roost.talk.tool_def import ToolDef

_DOCUMENT_REF = {"type": "string", "description": "The document's id, or its title (or a unique part of it)."}
_TITLE = {"type": "string", "description": "Short title, e.g. 'My tasks'."}
_MARKDOWN = {"type": "string", "description": ("Markdown: # headings, - bullets, 1. numbered items, **bold**, "
                                               "*italic*, [links](https://…).")}
_CELL_VALUE = {"type": ["string", "number", "boolean", "null"]}
_PROJECT = {"type": "string", "description": "Optional: one of the user's projects, by name or id. Name it exactly."}

LIST_DOCUMENTS_SPEC = ToolSpec(
    name="list_documents",
    description="List the user's documents (docs, sheets and PDFs; every bot uses them), newest first.",
    input_schema={"type": "object", "properties": {
        "kind": {"type": "string", "enum": ["doc", "sheet", "pdf"]},
        "project": {**_PROJECT, "description": "Only documents in this project, by name or id."},
    }},
)
READ_DOCUMENT_SPEC = ToolSpec(
    name="read_document",
    description=("Read a document: a doc as markdown, a sheet as a table (its first 30 rows and 10 columns), "
                 "a PDF as its text. Long ones are cut."),
    input_schema={"type": "object", "properties": {"document": _DOCUMENT_REF}, "required": ["document"]},
)
CREATE_DOC_SPEC = ToolSpec(
    name="create_doc",
    description="Create a doc from markdown. The user opens and edits it on the Board's Documents tab. "
                "When asked to save something in a document, gather it with your other tools first, then write it.",
    input_schema={"type": "object", "properties": {"title": _TITLE, "markdown": _MARKDOWN, "project": _PROJECT,
                                                   "tags": TOPIC_TAGS_SCHEMA},
                  "required": ["title", "markdown"]},
)
CREATE_SHEET_SPEC = ToolSpec(
    name="create_sheet",
    description=("Create a spreadsheet from rows, starting at A1; the first row is usually the header. Numbers "
                 "stay numbers. At most 500 rows of 26 cells."),
    input_schema={"type": "object", "properties": {
        "title": _TITLE,
        "rows": {"type": "array", "items": {"type": "array", "items": _CELL_VALUE}},
        "project": _PROJECT, "tags": TOPIC_TAGS_SCHEMA,
    }, "required": ["title", "rows"]},
)
APPEND_TO_DOC_SPEC = ToolSpec(
    name="append_to_doc",
    description="Add markdown to the end of a doc. Name the document exactly; if two match, ask the user which.",
    input_schema={"type": "object", "properties": {"document": _DOCUMENT_REF, "markdown": _MARKDOWN},
                  "required": ["document", "markdown"]},
)
UPDATE_SHEET_CELLS_SPEC = ToolSpec(
    name="update_sheet_cells",
    description=("Set cells in a sheet by A1 reference: a value, or a formula like =SUM(B2:B9) (the sheet "
                 "computes it when opened). A cell with neither is cleared. "
                 "Name the document exactly; if two match, ask the user which."),
    input_schema={"type": "object", "properties": {
        "document": _DOCUMENT_REF,
        "cells": {"type": "array", "items": {"type": "object", "properties": {
            "cell": {"type": "string", "description": "A1 reference, e.g. B3."},
            "value": _CELL_VALUE, "formula": {"type": "string"},
        }, "required": ["cell"]}},
    }, "required": ["document", "cells"]},
)
DELETE_DOCUMENT_SPEC = ToolSpec(
    name="delete_document",
    description="Delete a document. Name the document exactly; if two match, ask the user which.",
    input_schema={"type": "object", "properties": {"document": _DOCUMENT_REF}, "required": ["document"]},
)
MAKE_PDF_FROM_DOC_SPEC = ToolSpec(
    name="make_pdf_from_doc",
    description="Make a new PDF from a doc's text (the doc stays as it is). The PDF goes in the doc's project.",
    input_schema={"type": "object", "properties": {
        "document": _DOCUMENT_REF, "title": {"type": "string", "description": "The PDF's title (default: the doc's)."},
    }, "required": ["document"]},
)
SET_DOCUMENT_PROJECT_SPEC = ToolSpec(
    name="set_document_project",
    description=("Put a document (a doc, sheet or PDF) in one of the user's projects, or take it out with project "
                 "''. Its text is not changed. Name the document and the project exactly; if two match, ask the "
                 "user which."),
    input_schema={"type": "object", "properties": {
        "document": _DOCUMENT_REF,
        "project": {"type": "string", "description": "The project's name or id; '' takes the document out of its "
                                                     "project."},
    }, "required": ["document", "project"]},
)

DOCUMENT_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(LIST_DOCUMENTS_SPEC, "read"),
    ToolDef(READ_DOCUMENT_SPEC, "read"),
    ToolDef(CREATE_DOC_SPEC, "write_create"),
    ToolDef(CREATE_SHEET_SPEC, "write_create"),
    ToolDef(APPEND_TO_DOC_SPEC, "write_change"),
    ToolDef(UPDATE_SHEET_CELLS_SPEC, "write_change"),
    ToolDef(DELETE_DOCUMENT_SPEC, "write_change"),
    ToolDef(MAKE_PDF_FROM_DOC_SPEC, "write_create"),
    ToolDef(SET_DOCUMENT_PROJECT_SPEC, "write_change"),
)
