"""The card's line diff and how much of it goes on the wire (approval plan Task 10)."""

from __future__ import annotations

from roost.approvals.models import ApprovalCard, CardState, DiffView, PendingCall, approval_card_out
from roost.constants import APPROVAL_DIFF_SHOWN_LINES
from roost.mac.diff import line_diff


def _card(diff: DiffView) -> ApprovalCard:
    step = PendingCall(tool="mac_edit", arguments={}, topic="files", title="Edit a.md · MySpace", diff=diff)
    return ApprovalCard(id="c", user_id="u", bot_id="b", thread_id="t", work_item_id=None, kind="ask",
                        state=CardState.OPEN, steps=(step,), request="", tainted=False, session_offer=False,
                        answer_item_id=None, created_at="2026-10-22T00:00:00+00:00", closed_at=None)


def test_a_diff_counts_added_and_removed_lines():
    view = line_diff("one\ntwo\nthree\n", "one\n2\nthree\nfour\n")
    assert (view.plus, view.minus) == (2, 1)
    assert "-two" in view.text and "+2" in view.text and "+four" in view.text
    assert not view.text.startswith("---")          # no file header lines: the card names the file
    assert line_diff("same\n", "same\n") == DiffView("", 0, 0)
    assert line_diff("", "a\nb\n").plus == 2


def test_a_long_diff_is_cut_at_400_lines_on_the_wire():
    view = line_diff("", "".join(f"line {n}\n" for n in range(1000)))
    assert view.plus == 1000
    cut = approval_card_out(_card(view)).steps[0].diff
    assert cut is not None and cut.truncated and len(cut.text.split("\n")) == APPROVAL_DIFF_SHOWN_LINES
    assert cut.plus == 1000
    full = approval_card_out(_card(view), full=True).steps[0].diff
    assert full is not None and not full.truncated and len(full.text.split("\n")) > APPROVAL_DIFF_SHOWN_LINES
    live = approval_card_out(_card(view), counts_only=True).steps[0].diff
    assert live is not None and live.text == "" and live.plus == 1000
