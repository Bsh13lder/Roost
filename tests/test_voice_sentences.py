"""Speak-ahead's words (docs/plans/2026-10-30-roost-voice.md §3, contract B): a reply's streamed text cut into
sentence parts whose numbering never changes as more text arrives, a short first part, emoji dropped, and the
"On it: …" lead left out of what is read aloud."""

from __future__ import annotations

import pytest

from roost.talk.store import Message
from roost.voice.constants import VOICE_FIRST_PART_CHARS_MAX, VOICE_PART_CHARS_MAX
from roost.voice.sentences import call_parts, open_tail, split_sentences
from roost.voice.speech_text import speech_words
from roost.voice.spoken import message_parts

REPLY = "I found three flights. The cheapest leaves at 7:30 in the morning! Shall I book it?"


def test_split_sentences_keeps_only_closed_sentences_and_leaves_the_tail_open():
    assert split_sentences("One. Two! Three? Four… 五。 and the rest") == ("One.", "Two!", "Three?", "Four…", "五。")
    assert open_tail("One. Two! Three? Four… 五。 and the rest") == "and the rest"
    assert split_sentences("Still typing") == () and open_tail("Still typing") == "Still typing"
    assert split_sentences("Costs 3.50 euros. Ok") == ("Costs 3.50 euros.",)   # a decimal is not a sentence end
    assert split_sentences("") == () and open_tail("") == ""


def test_call_parts_are_one_sentence_each_and_the_tail_waits_for_done():
    # The last sentence has no whitespace after it yet, so it is still open until the reply is done.
    assert call_parts(REPLY, done=False) == ("I found three flights.", "The cheapest leaves at 7:30 in the morning!")
    assert call_parts(REPLY, done=True) == ("I found three flights.", "The cheapest leaves at 7:30 in the morning!",
                                            "Shall I book it?")
    assert call_parts("I found three flights. The cheapest", done=False) == ("I found three flights.",)
    assert call_parts("I found three flights. The cheapest", done=True) == ("I found three flights.", "The cheapest")
    assert call_parts("", done=True) == ()


@pytest.mark.parametrize("cut", list(range(0, len(REPLY) + 1, 7)))
def test_call_parts_are_prefix_stable(cut: int):
    earlier = call_parts(REPLY[:cut], done=False)
    later = call_parts(REPLY, done=False)
    assert later[:len(earlier)] == earlier
    assert call_parts(REPLY, done=True)[:len(earlier)] == earlier


def test_the_first_part_is_cut_at_a_clause_so_the_first_sound_comes_soon():
    long_first = ("Right now the forecast for Madrid says it will be sunny all morning with a light breeze from the "
                  "west, then clouds roll in after lunch and a shower is likely in the evening. Bring a jacket.")
    assert len(long_first.split(". ")[0]) > VOICE_FIRST_PART_CHARS_MAX
    parts = call_parts(long_first, done=True)
    assert parts[0].endswith("west,") and len(parts[0]) <= VOICE_FIRST_PART_CHARS_MAX
    assert parts[1].startswith("then clouds") and parts[1].endswith("evening.")
    assert parts[2] == "Bring a jacket."
    # The cut is made while the first sentence is still open, so the first sound is not held for its end.
    streamed = long_first[:VOICE_FIRST_PART_CHARS_MAX + 10]
    assert call_parts(streamed, done=False) == (parts[0],)


def test_a_first_sentence_with_no_clause_mark_is_spoken_whole():
    text = "Yes " * 40 + "indeed. Next."
    parts = call_parts(text, done=True)
    assert parts[0].endswith("indeed.") and parts[1] == "Next."


def test_a_long_sentence_is_cut_at_words_under_the_part_cap():
    sentence = " ".join(f"word{i}" for i in range(80)) + "."
    assert len(sentence) > VOICE_PART_CHARS_MAX
    parts = call_parts("Short one. " + sentence, done=True)
    assert parts[0] == "Short one."
    assert all(len(p) <= VOICE_PART_CHARS_MAX for p in parts[1:])
    assert " ".join(parts[1:]) == sentence


def test_the_on_it_lead_is_not_spoken_and_the_split_waits_for_its_line_end():
    assert call_parts("On it: checking", done=False) == ()           # the lead's end is not known yet
    assert call_parts("On it: checking the weather.\n\n", done=False) == ()
    assert call_parts("On it: checking the weather.\n\nSunny all day. Pack light.", done=False) == ("Sunny all day.",)
    assert call_parts("On it: checking the weather.\n\nSunny all day. Pack light.", done=True) == (
        "Sunny all day.", "Pack light.")
    assert call_parts("On it: checking.", done=True) == ("checking.",)   # nothing followed: its words alone


def test_emoji_and_table_rows_are_not_read_aloud():
    assert speech_words("Done ✅ and booked 🎉!") == "Done and booked !"
    table = "| Flight | Price |\n|---|---|\n| IB123 | 80 € |"
    words = speech_words(table)
    assert "---" not in words and "Flight Price" in words and "IB123 80 €" in words
    assert speech_words("Flags 🇪🇸 fly") == "Flags fly"


def test_read_aloud_strips_the_on_it_lead():
    message = Message(id="m", user_id="u", thread_id="t", role="bot", body="On it: looking it up.\n\nIt is 12:16 Madrid.",
                      tainted=False, seq=1, created_at="2026-10-30T10:00:00+00:00", kind="text")
    assert message_parts(message) == ["It is 12:16 Madrid."]
