"""What the bot reads when a click missed (owner, 2026-11-05: move through a site like a human).

- **Covered:** a dialog lies over the control. The miss names that dialog's own close buttons (``closes_dialog``,
  read from the live page, at most ``CU_CLOSERS_SHOWN_MAX``), with their numbers when the newest look has them,
  and Escape. Those buttons and Escape may then run with no look first (``session.closes_cover``).
- **A point with nothing on it:** the miss names the nearest control of the newest look and says to aim by number.

Labels are the page's words cut to one short line, as every other loop sentence shows them."""

from __future__ import annotations

from roost.computer_use.commit_words import closes_dialog
from roost.computer_use.marks import PageMarks
from roost.computer_use.models import PageTarget
from roost.computer_use.texts import (
    CLOSE_UNKNOWN_TEXT, CLOSE_WITH_TEXT, COVERED_TEXT, POINT_MISS_TEXT, POINT_NEAR_TEXT,
)
from roost.constants import CU_CLOSERS_SHOWN_MAX, CU_LABEL_SHOWN_CHARS

_SOMETHING = "something"     # the page's word for a cover it can't name (roost/desk/page_targets.py)


def _label(target: PageTarget) -> str:
    return " ".join((target.visible_text or target.text).split())[:CU_LABEL_SHOWN_CHARS]


def _index_of(marks: PageMarks, target: PageTarget) -> int | None:
    return next((i for i, mark in enumerate(marks.controls, start=1) if mark.node_id == target.node_id), None)


async def closers_of(page, dialog: str) -> tuple[PageTarget, ...]:
    """The covering dialog's own close buttons on the live page; none when the cover has no name."""
    if not dialog or dialog == _SOMETHING:
        return ()
    found = [t for t in await page.targets() if t.in_dialog == dialog and closes_dialog(t)]
    return tuple(found[:CU_CLOSERS_SHOWN_MAX])


def _named(marks: PageMarks, target: PageTarget) -> str:
    index = _index_of(marks, target)
    return f"[{index}] '{_label(target)}'" if index is not None else f"'{_label(target)}'"


def covered_text(label: str, dialog: str, closers: tuple[PageTarget, ...], marks: PageMarks) -> str:
    """The covered miss, with how to close the dialog."""
    how = (CLOSE_WITH_TEXT.format(closers=" or ".join(_named(marks, t) for t in closers)) if closers
           else CLOSE_UNKNOWN_TEXT)
    return COVERED_TEXT.format(label=label, dialog=dialog, how=how)


def _distance(target: PageTarget, point: tuple[int, int]) -> float:
    cx, cy = target.box.center()
    return float((cx - point[0]) ** 2 + (cy - point[1]) ** 2)


def point_miss_text(point: tuple[int, int], marks: PageMarks) -> str:
    """A point click that found nothing: the nearest numbered control of the newest look, and aim by number."""
    near = ""
    if marks.controls:
        target = min(marks.controls, key=lambda t: _distance(t, point))
        cx, cy = target.box.center()
        near = POINT_NEAR_TEXT.format(index=_index_of(marks, target), kind=target.kind, label=_label(target),
                                      cx=cx, cy=cy)
    return POINT_MISS_TEXT.format(x=point[0], y=point[1], near=near)
