# SPDX-License-Identifier: MIT
# Harvested from LazyClaw lazyclaw/skills/builtin/sheets.py lines 72-89 @ 21e1002, adapted for Roost

"""A sheet as text for the model (the harvested ``_format_grid``, with Roost's
caps and a bounded window) and a new sheet from plain rows (Roost)."""

from __future__ import annotations

from typing import Any, Sequence

from roost.constants import SHEET_READ_MAX_COLS, SHEET_READ_MAX_ROWS
from roost.documents import sheet_snapshot as S


def format_grid(snap: dict[str, Any], sheet: int | str = 0) -> str:
    """Render a worksheet's value grid as a labelled text table for the LLM.

    Roost: only the capped window is built, from ``iter_cells``. The harvested
    ``as_grid`` builds the whole dense grid up to ``used_bounds`` first, so one
    far-off cell would allocate millions of rows; no read path calls it.
    ``used_bounds`` gives only the size for the "showing X of Y" note."""
    max_r, max_c = S.used_bounds(snap, sheet)
    if max_r < 0:
        return "(empty sheet)"
    n_rows, n_cols = min(max_r + 1, SHEET_READ_MAX_ROWS), min(max_c + 1, SHEET_READ_MAX_COLS)
    shown = {(r, c): S.cell_display(cell) for r, c, cell in S.iter_cells(snap, sheet)
             if r < n_rows and c < n_cols and S.has_content(cell)}
    header = "    | " + " | ".join(S.col_to_letter(c) for c in range(n_cols))
    lines = [header, "    |-" + "-|-".join("-" * 3 for _ in range(n_cols))]
    for r in range(n_rows):
        cells = " | ".join(str(shown.get((r, c), "")) for c in range(n_cols))
        lines.append(f"{r + 1:>3} | {cells}")
    note = ""
    if max_r + 1 > n_rows or max_c + 1 > n_cols:
        note = f"\n…(showing {n_rows}×{n_cols} of {max_r + 1}×{max_c + 1})"
    return "\n".join(lines) + note


def sheet_from_rows(title: str, rows: Sequence[Sequence[Any]]) -> dict[str, Any]:
    """Roost: a new workbook whose first sheet holds ``rows`` from A1. Empty
    cells stay empty; numeric text becomes numbers (the harvested coerce_value)."""
    width = max((len(row) for row in rows), default=0)
    workbook = S.blank_workbook(title, rows=max(S.DEFAULT_ROWS, len(rows)), cols=max(S.DEFAULT_COLS, width))
    edits = [{"row": r, "col": c, "value": value}
             for r, row in enumerate(rows) for c, value in enumerate(row) if value is not None and value != ""]
    return S.set_cells(workbook, edits)
