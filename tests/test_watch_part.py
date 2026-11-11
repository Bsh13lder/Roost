"""The watched part of a page, found and compared with no model (roost/routines/watch_part.py)."""

from __future__ import annotations

from roost.constants import WATCH_CHANGE_MAX_CHARS, WATCH_SNAPSHOT_MAX_CHARS, WATCH_TAIL_LINES
from roost.routines.watch_part import (
    AreaText, changed_lines, compared, fingerprint, normalise, pick_part,
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


def test_words_found_nowhere_are_missing_never_the_whole_page():
    """Owner, 2026-11-09: the whole page as a fallback made every other chat's news a model run."""
    main = AreaText(role="main", name="", text="Headline\nBody")
    part = pick_part("the price box", (LIST, main), "Top\nHeadline\nBody")
    assert part.where == "missing" and part.text == ""


def test_no_words_watch_the_main_text():
    main = AreaText(role="main", name="", text="Headline\nBody")
    part = pick_part("", (LIST, main), "Top\nHeadline\nBody")
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


def test_counters_with_thousands_are_noise():
    assert normalise("Group\n1,234 unread messages\n2.345\n(1 234)") == "group"


def test_rows_that_only_move_compare_the_same():
    assert compared("Mum\nsee you\nAna\nok") == compared("Ana\nok\nMum\nsee you")
    assert compared("ok\nok") != compared("ok")


def test_a_name_in_quotes_is_the_part_and_the_rest_of_the_sentence_is_ignored():
    """Owner, 2026-11-10: "new messages from Ana in her chat \"Physio Ana\"" never stood on one line."""
    part = pick_part('new messages from Ana in her direct chat "Physio Ana"', (LIST,), "WhatsApp\n" + LIST.text)
    assert part.where == "rows" and part.text.startswith("Physio Ana")


def test_curly_and_angle_quotes_count_too():
    for said in ("watch “Physio Ana” please", "mensajes de «Physio Ana»"):
        assert pick_part(said, (LIST,), "WhatsApp\n" + LIST.text).where == "rows"


def test_several_quoted_names_watch_each_row():
    part = pick_part('"Mum" or "Physio Ana"', (LIST,), "WhatsApp\n" + LIST.text)
    assert part.where == "rows" and "Mum" in part.text and "Physio Ana" in part.text


def test_request_words_do_not_have_to_be_on_the_page():
    part = pick_part("new messages from Physio Ana", (LIST,), "WhatsApp\n" + LIST.text)
    assert part.where == "rows" and part.text.startswith("Physio Ana")


def test_a_quoted_name_found_nowhere_is_missing():
    assert pick_part('"Nobody Here"', (LIST,), "WhatsApp\n" + LIST.text).where == "missing"


def test_a_name_in_brackets_counts_like_quotes():
    part = pick_part("new messages from Ana on her phone chat (Physio Ana)", (LIST,), "WhatsApp\n" + LIST.text)
    assert part.where == "rows" and part.text.startswith("Physio Ana")


def test_a_phone_number_is_a_name_of_its_own():
    rows = AreaText(role="grid", name="Chat list", text="+34 612 34 56 78\n14:02\nhola\nMum\nok")
    part = pick_part("new messages from +34 612 34 56 78 (Nobody Here) on the work chat", (rows,), rows.text)
    assert part.where == "rows" and part.text.startswith("+34 612 34 56 78")


def test_a_row_stops_where_the_next_chat_starts():
    """Owner, 2026-11-10: the next chat's news ran the watch of the chat above it."""
    rows = AreaText(role="grid", name="Chat list", text="Physio Ana\n14:50\nok\nGroup one\n14:51\nhi all\nMum\nYesterday\nbye")
    part = pick_part("(Physio Ana)", (rows,), rows.text)
    assert part.text == "Physio Ana\n14:50\nok"


def test_a_row_with_an_unread_counter_keeps_it():
    part = pick_part("(Physio Ana)", (LIST,), "WhatsApp\n" + LIST.text)
    assert part.text == "Physio Ana\n14:50\nTomorrow at 10?\n2"


WA_LIST = AreaText(role="grid", name="Chat list", text="Physio Ana\n14:50\nok\nGroup one\n14:51\nhi all")


def test_all_chats_watches_the_whole_chat_list():
    """Owner, 2026-11-11: "(not groups)" was taken for a chat's name, so the general watch never changed."""
    part = pick_part("new incoming messages on WhatsApp Web (DM + all chats) (not groups)", (WA_LIST, PANE),
                     "WhatsApp\nnot groups here\n" + WA_LIST.text)
    assert part.where == "area" and part.text == WA_LIST.text


def test_the_chat_list_by_name_and_in_spanish():
    for said in ("the chat list", "todos los chats", "every chat"):
        assert pick_part(said, (WA_LIST,), WA_LIST.text).text == WA_LIST.text


def test_all_chats_with_no_named_list_takes_the_largest_list():
    rows = AreaText(role="grid", name="", text=WA_LIST.text)
    assert pick_part("all chats", (rows,), "Top\n" + rows.text).text == WA_LIST.text


def test_a_lowercase_bracket_is_not_a_name():
    part = pick_part("Physio Ana (not groups)", (LIST,), "WhatsApp\nnot groups\n" + LIST.text)
    assert part.text.startswith("Physio Ana")


def test_chats_in_the_plural_with_no_name_watch_the_whole_chat_list():
    """Owner, 2026-11-11: "new incoming messages in personal one-to-one chats (not groups)"."""
    for said in ("new incoming messages in personal one-to-one chats (not groups)", "my DMs",
                 "conversaciones privadas"):
        assert pick_part(said, (WA_LIST,), WA_LIST.text).text == WA_LIST.text, said


def test_a_named_chat_in_the_plural_sentence_is_still_that_chat():
    part = pick_part('new messages in my chats from "Physio Ana"', (LIST,), "WhatsApp\n" + LIST.text)
    assert part.where == "rows" and part.text.startswith("Physio Ana")
