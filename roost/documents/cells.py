"""Sheet cells at the boundary (M2 D2): the pydantic types for the rows a tool
or the Board sends, a cell edit by A1 reference, and the sheet's far corner.
No cell may sit past ZZ100000, so no read is asked to cover millions of rows."""

from __future__ import annotations

from typing import Annotated, Any, Mapping, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from roost.constants import (
    MAX_SHEET_CELL_TEXT, MAX_SHEET_COL_INDEX, MAX_SHEET_COLS, MAX_SHEET_ROW_INDEX, MAX_SHEET_ROWS_PER_CALL,
)
from roost.documents.sheet_snapshot import a1_to_rc, rc_to_a1
from roost.records.tool_text import ToolText

LAST_CELL = rc_to_a1(MAX_SHEET_ROW_INDEX, MAX_SHEET_COL_INDEX)   # "ZZ100000"

SheetCell = Union[Annotated[str, Field(max_length=MAX_SHEET_CELL_TEXT)], int, float, bool, None]
SheetRow = Annotated[list[SheetCell], Field(max_length=MAX_SHEET_COLS)]
SheetRows = Annotated[list[SheetRow], Field(max_length=MAX_SHEET_ROWS_PER_CALL)]
# A tool's cells: the same shapes, with copied tool-result text stored plain.
ToolSheetCell = Union[Annotated[ToolText, Field(max_length=MAX_SHEET_CELL_TEXT)], int, float, bool, None]
ToolSheetRows = Annotated[list[Annotated[list[ToolSheetCell], Field(max_length=MAX_SHEET_COLS)]],
                          Field(max_length=MAX_SHEET_ROWS_PER_CALL)]


class CellEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cell: str = Field(pattern=r"^[A-Za-z]{1,3}[1-9][0-9]{0,6}$")
    value: ToolSheetCell = None
    formula: ToolText | None = Field(default=None, max_length=MAX_SHEET_CELL_TEXT)

    @field_validator("cell")
    @classmethod
    def _inside_the_sheet(cls, cell: str) -> str:
        row, col = a1_to_rc(cell)
        if row > MAX_SHEET_ROW_INDEX or col > MAX_SHEET_COL_INDEX:
            raise ValueError(f"cells go from A1 to {LAST_CELL}")
        return cell


def _index_within(key: Any, highest: int) -> bool:
    return isinstance(key, str) and key.isascii() and key.isdigit() and int(key) <= highest


def _first_sheet_id(snapshot: Mapping[str, Any], sheets: Mapping[str, Any]) -> Any:
    """What ``sheet_snapshot._resolve_sheet_id(snap, 0)`` — the default every
    reader uses — would resolve to."""
    order = snapshot.get("sheetOrder")
    return order[0] if isinstance(order, list) and order else next(iter(sheets))


def sheet_cells_in_bounds(snapshot: Mapping[str, Any]) -> bool:
    """Whether this is a USABLE sheet snapshot: it has a resolvable first
    worksheet (what every reader's default ``sheet=0`` resolves to), every
    worksheet's cellData is shaped as real ``ICellData`` (a dict, or empty),
    and every cell sits inside the far corner — so a Board save can't plant a
    snapshot that reads back as a crash (no sheets, a dangling ``sheetOrder``
    entry, a cell that isn't a dict) or a cell at ZZZ9999999."""
    sheets = snapshot.get("sheets")
    if not isinstance(sheets, dict) or not sheets:
        return False
    first = _first_sheet_id(snapshot, sheets)
    if not isinstance(first, str) or first not in sheets:
        return False
    for sheet in sheets.values():
        if not isinstance(sheet, dict):
            return False
        cell_data = sheet.get("cellData")
        if cell_data is None:
            continue
        if not isinstance(cell_data, dict):
            return False
        for row_key, cols in cell_data.items():
            if not _index_within(row_key, MAX_SHEET_ROW_INDEX) or not isinstance(cols or {}, dict):
                return False
            for col_key, cell in (cols or {}).items():
                if not _index_within(col_key, MAX_SHEET_COL_INDEX):
                    return False
                if cell is not None and not isinstance(cell, dict):
                    return False
    return True
