"""The Bot Journal's Markdown (pure): a daily note with front matter tags and one line per entry."""

from __future__ import annotations

from datetime import date

import pytest

from roost.constants import JOURNAL_ENTRY_MAX_CHARS
from roost.journal.markdown import add_entry, entry_lines, entry_text, matching_lines, new_day, run_line

DAY = date(2026, 10, 22)


def test_a_new_day_is_an_obsidian_daily_note():
    text = new_day("Penny Pincher", DAY)
    assert text.startswith("---\n")
    assert 'tags: ["roost/journal", "bot/penny-pincher"]' in text
    assert 'day: "2026-10-22"' in text and "# Penny Pincher · 2026-10-22" in text


def test_entries_are_one_line_each_in_order():
    text = add_entry(add_entry(new_day("Ana", DAY), "09:05", "Added a task"), "14:19", "Wrote\nthe  report")
    assert entry_lines(text) == ("- 09:05 Added a task", "- 14:19 Wrote the report")


def test_entry_text_is_one_trimmed_line_and_refuses_empty_or_long():
    assert entry_text("  a\n\n b\tc ") == "a b c"
    with pytest.raises(ValueError):
        entry_text("   ")
    with pytest.raises(ValueError):
        entry_text("x" * (JOURNAL_ENTRY_MAX_CHARS + 1))


def test_an_entry_cannot_start_front_matter_or_a_heading():
    text = add_entry(new_day("Ana", DAY), "10:00", "--- # hi")
    assert entry_lines(text) == ("- 10:00 --- # hi",)


def test_matching_lines_need_every_word_and_ignore_case_and_accents():
    text = add_entry(add_entry(new_day("Ana", DAY), "09:05", "Paid the Café bill"), "10:00", "Called Joe")
    assert matching_lines(text, ("cafe", "bill")) == ("- 09:05 Paid the Café bill",)
    assert matching_lines(text, ("nothing",)) == ()


def test_a_run_line_names_each_step_once_with_a_count():
    steps = ("adding a task", "saving a note", "adding a task", "logging an expense")
    assert run_line(steps) == "Added a task ×2, saved a note, logged an expense"
    assert run_line(()) is None


def test_a_run_line_is_capped():
    steps = tuple(f"adding thing {n}" for n in range(20))
    line = run_line(steps)
    assert line is not None and line.endswith("and 14 more") and len(line) <= JOURNAL_ENTRY_MAX_CHARS
