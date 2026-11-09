"""The watched part of a page, found and compared with no model (roost/routines/watch_part.py)."""

from __future__ import annotations

from roost.constants import WATCH_CHANGE_MAX_CHARS, WATCH_SNAPSHOT_MAX_CHARS, WATCH_TAIL_LINES
from roost.routines.watch_part import (
    AreaText, changed_lines, fingerprint, normalise, pick_part,
)

DEK = b"k" * 32
LIST = AreaText(role="grid", name="Chat list", text="Mum\n14:02\nsee you\nPhysio Ana\n14:50\nTomorrow at 10?\n2\nWork")
PANE_LINES = [f"Ana: line {n}" for n in range(30)]
PANE = AreaText(role="application", name="Messages", text="\n".join(PANE_LINES))


def test_an_area_named_by_the_words_is_the_part():
    price = AreaText(role="region", name="Price box", text="Now €24.99\nWas €29.99")
    part = pick_part("the price box", (LIST, price), "Shop\nNow €24.99\nWas €29.99")
    assert part.where == "area" and part.text == "Now €24.99\nWas €29.99"


def test_an_open_chat_named_in_the_header_gives_the_newest_messages_of_its_pane():
    page = "WhatsApp. Physio Ana.\n" + LIST.text + "\n" + PANE.text
    part = pick_part("physio ana", (LIST, PANE), page)
    assert part.where == "pane"
    assert part.text.splitlines() == PANE_LINES[-WATCH_TAIL_LINES:]


def test_a_chat_list_row_that_names_the_chat_is_the_part_with_its_neighbours():
    part = pick_part("Physio", (LIST,), "WhatsApp\n" + LIST.text)
    assert part.where == "rows"
    assert part.text == "Physio Ana\n14:50\nTomorrow at 10?\n2"


def test_only_meaningful_words_count():
    chat = AreaText(role="region", name="Chat", text="Someone else")
    part = pick_part("the physio chat", (chat, LIST), "WhatsApp\n" + LIST.text)
    assert part.where == "rows"


def test_words_found_nowhere_fall_back_to_the_main_text():
    main = AreaText(role="main", name="", text="Headline\nBody")
    part = pick_part("the price box", (LIST, main), "Top\nHeadline\nBody")
    assert part.where == "page" and part.text == "Headline\nBody"


def test_no_words_and_no_main_area_is_the_whole_page():
    part = pick_part("", (), "Just text\nhere")
    assert part.where == "page" and part.text == "Just text\nhere"


def test_accents_and_case_do_not_matter():
    clinic = AreaText(role="region", name="Clínica Sol", text="Abierto")
    assert pick_part("clinica sol", (clinic,), "x").where == "area"


def test_the_part_is_cut_to_the_snapshot_cap():
    part = pick_part("", (), "x" * (WATCH_SNAPSHOT_MAX_CHARS + 50))
    assert len(part.text) == WATCH_SNAPSHOT_MAX_CHARS


def test_normalise_drops_times_counters_noise_and_spacing():
    one = "Physio Ana\n14:50\nTomorrow  at 10?\n2\nonline\nlast seen today at 14:51\n(3)"
    two = "physio ana\n15:20\nTomorrow at 10?\n5\ntyping…"
    assert normalise(one) == normalise(two) == "physio ana\ntomorrow at 10?"


def test_normalise_keeps_prices_and_relative_times_go():
    assert normalise("€24.99 · 5 min ago") == "€24.99 ·"
    assert normalise("€24.99") != normalise("€19.99")
    assert normalise("hace 3 min") == normalise("hace 10 min")


def test_fingerprint_is_keyed_and_stable():
    assert fingerprint(DEK, "r1", "a") == fingerprint(DEK, "r1", "a")
    assert fingerprint(DEK, "r1", "a") != fingerprint(DEK, "r2", "a")
    assert fingerprint(DEK, "r1", "a") != fingerprint(b"j" * 32, "r1", "a")
    assert len(fingerprint(DEK, "r1", "a")) == 64


def test_changed_lines_are_the_new_ones():
    old = "Ana: hi\n14:02\nAna: how is the knee?"
    new = "Ana: hi\n14:02\nAna: how is the knee?\n15:10\nAna: can we move to 11?"
    assert changed_lines(old, new) == "Ana: can we move to 11?"


def test_changed_lines_with_nothing_new_is_the_whole_part():
    assert changed_lines("b\na", "a\nb") == "a\nb"


def test_changed_lines_are_capped():
    new = "\n".join(f"line {n} " + "x" * 50 for n in range(200))
    assert len(changed_lines("", new)) <= WATCH_CHANGE_MAX_CHARS
