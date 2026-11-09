"""Owner, 2026-10-31: Gigs read a card's No ("Don't do it") as a standing rule and asked for "your clear OK" again
after the owner's new message asked for the very thing. A No is for that one time; a newer message is the OK."""

from __future__ import annotations

from roost.approvals.texts import NO_LINE
from roost.talk import instructions


def test_a_no_line_says_not_this_time():
    line = NO_LINE.format(title="Click 'Apply now'")
    assert line == "No: Click 'Apply now'. Not this time; carry on without it."
    assert "Don't do it" not in line


def test_the_bot_is_told_a_newer_message_is_the_ok():
    text = " ".join(v for v in vars(instructions).values() if isinstance(v, str))
    assert "A No on a card is for that one time" in text
