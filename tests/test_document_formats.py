"""Docs, sheets and PDFs as data (M2 D2): the harvested Univer snapshot and PDF
helpers, plus Roost's markdown and table views of them."""

from __future__ import annotations

import time

import pytest
from pydantic import ValidationError

from roost.documents import pdf_ops, sheet_text
from roost.documents.cells import CellEdit, sheet_cells_in_bounds
from roost.documents.doc_markdown import append_markdown, doc_from_markdown, doc_plain_text, doc_to_markdown
from roost.documents.sheet_snapshot import as_grid, set_cells
from roost.documents.sheet_text import format_grid, sheet_from_rows

_TASKS_MD = "# My tasks\n\n- Call the dentist\n- **Buy** orchids\n1. first\nSee [the shop](https://example.com/shop)"


def test_markdown_survives_a_round_trip_through_a_univer_doc():
    snap = doc_from_markdown("My tasks", _TASKS_MD)
    assert snap["body"]["dataStream"].endswith("\r\n")
    out = doc_to_markdown(snap)
    for line in ("# My tasks", "- Call the dentist", "- **Buy** orchids", "1. first",
                 "[the shop](https://example.com/shop)"):
        assert line in out


def test_appending_markdown_keeps_what_was_there():
    snap = append_markdown(doc_from_markdown("List", "- eggs"), "- milk")
    assert doc_to_markdown(snap).splitlines() == ["- eggs", "- milk"]


def test_plain_text_drops_the_markdown_marks():
    assert doc_plain_text(doc_from_markdown("T", "# Title\n**bold** words")) == "Title\n\nbold words"


def test_a_sheet_from_rows_reads_back_as_a_small_table():
    snap = sheet_from_rows("October expenses", [["Date", "Category", "Amount"], ["2026-10-03", "food", "12.50"]])
    assert as_grid(snap) == [["Date", "Category", "Amount"], ["2026-10-03", "food", 12.5]]
    text = format_grid(snap)
    assert "A | B | C" in text and "12.5" in text and "food" in text


def test_a_big_sheet_is_shown_capped():
    snap = sheet_from_rows("Big", [[f"r{r}c{c}" for c in range(12)] for r in range(40)])
    text = format_grid(snap)
    assert "showing 30×10 of 40×12" in text and "r29c9" in text and "r30c0" not in text


def test_cells_are_set_by_a1_reference():
    snap = set_cells(sheet_from_rows("S", [["a", "1"]]), [{"cell": "B1", "value": "2"}, {"cell": "C1", "formula": "=A1"}])
    assert as_grid(snap) == [["a", 2, "=A1"]]


def test_only_a_plain_finite_decimal_coerces_to_a_number():
    """Fix round 1, finding 1: 'Nan'/'Infinity'/'inf' must stay text (a bare
    float()/int() turned them into a non-finite float that later broke
    GET /api/documents/{id}), and text someone meant to keep as text — a
    leading-zero postal code, a leading '+' phone number, an
    underscore-grouped numeral — must never silently become a number."""
    row = ["Nan", "Infinity", "inf", "08001", "+34600123456", "1_000", "12.50", "-3.5", "0"]
    snap = sheet_from_rows("S", [row])
    assert as_grid(snap)[0] == ["Nan", "Infinity", "inf", "08001", "+34600123456", "1_000", 12.5, -3.5, 0]


def test_a_far_off_cell_is_read_capped_without_the_dense_grid(monkeypatch):
    """One cell at ZZZ9999999 (an old edit, or an imported sheet's stray cell)
    must not make a read allocate rows x columns: only the 30x10 window is built."""
    def dense(*_args, **_kwargs):
        raise AssertionError("a read built the dense grid (as_grid)")

    monkeypatch.setattr(sheet_text.S, "as_grid", dense)
    snap = set_cells(sheet_from_rows("Far", [["a"]]), [{"row": 9_999_998, "col": 18_277, "value": "far"}])
    started = time.perf_counter()
    text = format_grid(snap)
    assert time.perf_counter() - started < 1.0
    assert "showing 30×10 of 9999999×18278" in text and "| a" in text and "far" not in text


def test_a_cell_past_the_sheets_corner_is_refused():
    assert CellEdit(cell="zz100000", value=1).cell == "zz100000"
    for far in ("ZZZ9999999", "AAA1", "A100001"):
        with pytest.raises(ValidationError):
            CellEdit(cell=far, value=1)
    assert sheet_cells_in_bounds(sheet_from_rows("S", [["a"]]))
    assert not sheet_cells_in_bounds(set_cells(sheet_from_rows("S", [["a"]]), [{"row": 100_000, "col": 0, "value": 1}]))
    assert not sheet_cells_in_bounds(set_cells(sheet_from_rows("S", [["a"]]), [{"row": 0, "col": 702, "value": 1}]))


def test_a_pdf_made_from_text_reads_back():
    data = pdf_ops.generate_from_text("Ana likes orchids.\n\nBirthday 3 May.", title="Ana")
    assert pdf_ops.is_pdf(data) and pdf_ops.page_count(data) == 1
    assert "orchids" in pdf_ops.extract_text(data)


def test_something_that_is_not_a_pdf_is_refused():
    assert not pdf_ops.is_pdf(b"hello")
    with pytest.raises(pdf_ops.PdfError):
        pdf_ops.page_count(b"hello")
