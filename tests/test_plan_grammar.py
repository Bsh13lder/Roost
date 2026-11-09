"""The Plan grammar (design 4.1): lenient read, canonical write."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from roost.plan import grammar
from roost.plan.grammar import PlanRefused

FIX = Path(__file__).parent / "fixtures" / "plan"
TODAY = date(2026, 10, 22)


def fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_round_trip_is_the_canonical_form() -> None:
    canon = fx("canonical.md")
    assert grammar.render(grammar.parse(canon)) == canon
    assert grammar.canonical(canon, TODAY) == canon
    for name in ("user_order.md", "obsidian_tasks.md"):
        once = grammar.canonical(fx(name), TODAY)
        assert grammar.canonical(once, TODAY) == once


def test_other_lines_survive_byte_for_byte() -> None:
    text = fx("odd_lines.md")
    doc = grammar.parse(text)
    assert grammar.render(doc) == text
    assert doc.items == ()
    assert doc.unreadable == 2  # the bad date and the bad time


def test_both_field_orders_parse_the_same() -> None:
    a = grammar.parse(fx("canonical.md"))
    b = grammar.parse(fx("user_order.md"))
    strip = lambda d: [(i.id, i.status, i.text, i.tags, i.date, i.time, i.done_on, i.dropped_on, i.scheduled, i.indent) for i in d.items]
    assert strip(a) == strip(b)
    assert grammar.canonical(fx("user_order.md"), TODAY) == fx("canonical.md")


def test_obsidian_tasks_fixture_parses_every_field() -> None:
    items = grammar.parse(fx("obsidian_tasks.md")).items
    first, second, third = items
    assert (first.id, first.status, first.time, first.date, first.scheduled) == ("aaa111", "planned", "08:30", "2026-10-22", "2026-10-21")
    assert first.tags == ("#home", "#garden")
    assert (second.status, second.done_on, second.date) == ("done", "2026-10-19", "2026-10-18")
    assert (third.status, third.dropped_on) == ("dropped", "2026-10-17")


def test_unknown_emoji_fields_stay_in_the_text() -> None:
    item = grammar.parse(fx("obsidian_tasks.md")).items[0]
    assert item.text == "Water plants 🔁 every week ⏫"
    assert "🔁 every week ⏫" in grammar.render(grammar.parse(fx("obsidian_tasks.md")))


@pytest.mark.parametrize("line", [
    "- [ ] x 📅 2026-02-30", "- [ ] x 📅 nope", "- [ ] x ⏰ 24:00", "- [ ] x ⏰ 9:5",
    "- [ ] x 🆔 ab", "- [ ] x 📅", "- [ ] x 📅 2026-10-01 📅 2026-10-02",
])
def test_bad_dates_make_a_line_unreadable_not_lost(line: str) -> None:
    doc = grammar.parse(line + "\n")
    assert doc.items == () and doc.unreadable == 1
    assert grammar.render(doc) == line + "\n"


def test_status_rules_add_and_clear_done_and_dropped_dates() -> None:
    item = grammar.parse("- [ ] a 🆔 aaaaaa\n").items[0]
    done = grammar.apply_status(item, "done", TODAY)
    assert done.done_on == "2026-10-22" and done.dropped_on is None
    again = grammar.apply_status(done, "done", date(2026, 11, 1))
    assert again.done_on == "2026-10-22"
    dropped = grammar.apply_status(done, "dropped", TODAY)
    assert dropped.dropped_on == "2026-10-22" and dropped.done_on is None
    back = grammar.apply_status(dropped, "on_it", TODAY)
    assert back.dropped_on is None and back.done_on is None
    with pytest.raises(ValueError):
        grammar.apply_status(item, "bogus", TODAY)
    # a hand-written [x] without a date gets today
    assert "✅ 2026-10-22" in grammar.canonical("- [x] a\n", TODAY)
    assert "❌ 2026-10-22" in grammar.canonical("- [-] a\n", TODAY)
    assert "✅" not in grammar.canonical("- [ ] a ✅ 2026-01-01\n", TODAY)


def test_ids_are_assigned_once_and_unique() -> None:
    text = "- [ ] a\n- [ ] b 🆔 zzzzzz\n- [ ] c 🆔 zzzzzz\n- [ ] d\n"
    doc = grammar.assign_ids(grammar.parse(text), taken=frozenset({"qqqqqq"}))
    ids = [i.id for i in doc.items]
    assert all(i and len(i) == 6 and i.isalnum() and i == i.lower() for i in ids)
    assert len(set(ids)) == 4 and ids[1] == "zzzzzz"
    again = grammar.assign_ids(doc, taken=frozenset())
    assert [i.id for i in again.items] == ids


def test_one_subtask_level_with_spaces_or_a_tab() -> None:
    text = "- [ ] p\n  - [ ] two\n    - [ ] four\n\t- [ ] tab\n"
    doc = grammar.parse(text)
    assert [i.indent for i in doc.items] == [0, 1, 1, 1]
    assert grammar.render(doc) == "- [ ] p\n  - [ ] two\n  - [ ] four\n  - [ ] tab\n"


def test_archive_moves_old_finished_items() -> None:
    text = (
        "- [x] old ✅ 2026-01-01 🆔 aaaaaa\n  - [ ] sub 🆔 bbbbbb\n"
        "- [x] recent ✅ 2026-10-20 🆔 cccccc\n- [-] old drop ❌ 2026-02-01 🆔 dddddd\n"
        "- [ ] open 📅 2026-01-01 🆔 eeeeee\n"
    )
    out = grammar.render(grammar.archive_old(grammar.parse(text), TODAY))
    head, _, tail = out.partition("## Archive\n")
    assert "old ✅" not in head and "old drop" not in head and "recent" in head and "open" in head
    assert "old ✅" in tail and "sub" in tail and "old drop" in tail
    again = grammar.render(grammar.archive_old(grammar.parse(out), TODAY))
    assert again == out and out.count("## Archive") == 1


def test_limits_refuse_with_plain_text() -> None:
    many = "".join(f"- [ ] t{i}\n" for i in range(2001))
    with pytest.raises(PlanRefused, match="The Plan is too long. Archive or remove some items."):
        grammar.canonical(many, TODAY)
    with pytest.raises(PlanRefused):
        grammar.canonical("x" * 262_145, TODAY)
