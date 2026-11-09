"""The document tools' arguments (M2 D2; projects hub H12) — pydantic at the
tool boundary. Free text is ``ToolText``: a copy of an escaped tool result is
stored plain. ``project`` names one of the user's projects (its name or id)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from roost.constants import (
    MAX_TASK_TAGS,
    MAX_CATEGORY_NAME_LENGTH, MAX_DOC_MARKDOWN_LENGTH, MAX_DOCUMENT_TITLE_LENGTH, MAX_SHEET_CELLS_PER_CALL,
)
from roost.documents.cells import CellEdit, ToolSheetRows
from roost.documents.models import DocumentKind
from roost.records.tool_text import ToolText


class ListDocumentsArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: DocumentKind | None = None
    project: ToolText | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)


class DocumentRefArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    document: ToolText = Field(min_length=1, max_length=MAX_DOCUMENT_TITLE_LENGTH)


class CreateDocArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: ToolText = Field(default="", max_length=MAX_DOCUMENT_TITLE_LENGTH)
    markdown: ToolText = Field(min_length=1, max_length=MAX_DOC_MARKDOWN_LENGTH)
    project: ToolText | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)
    tags: list[ToolText] = Field(default_factory=list, max_length=MAX_TASK_TAGS)


class CreateSheetArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: ToolText = Field(default="", max_length=MAX_DOCUMENT_TITLE_LENGTH)
    rows: ToolSheetRows = Field(min_length=1)
    project: ToolText | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)
    tags: list[ToolText] = Field(default_factory=list, max_length=MAX_TASK_TAGS)


class AppendToDocArgs(DocumentRefArgs):
    markdown: ToolText = Field(min_length=1, max_length=MAX_DOC_MARKDOWN_LENGTH)


class UpdateSheetCellsArgs(DocumentRefArgs):
    cells: list[CellEdit] = Field(min_length=1, max_length=MAX_SHEET_CELLS_PER_CALL)


class MakePdfArgs(DocumentRefArgs):
    title: ToolText | None = Field(default=None, max_length=MAX_DOCUMENT_TITLE_LENGTH)


class SetDocumentProjectArgs(DocumentRefArgs):
    project: ToolText = Field(max_length=MAX_CATEGORY_NAME_LENGTH)   # '' takes it out of its project
