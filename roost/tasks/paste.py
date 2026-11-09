"""A pasted list (Amendment T): each line becomes a task, and an indented line a step of the task above.

Pure. A ``- `` or ``• `` bullet and a ``[ ]`` / ``[x]`` box in front of a line are dropped. Blank lines are
skipped. Indentation is read against the least-indented line, so an indented list is still a list."""

from __future__ import annotations

import re
from dataclasses import dataclass

from roost.constants import PASTE_MAX_LINES

TOO_MANY_TEXT = "A pasted list can hold at most {limit} lines."
_BULLET = re.compile(r"^(?:[-•]\s+)?(?:\[[ xX]\]\s+)?")


@dataclass(frozen=True)
class PasteItem:
    line: str                        # the task's own quick line
    steps: tuple[str, ...] = ()      # its indented lines, as typed


def _clean(line: str) -> str:
    return _BULLET.sub("", line.strip(), count=1).strip()


def split_paste(text: str) -> tuple[PasteItem, ...]:
    """The tasks a pasted list holds. ``ValueError`` when it has more than ``PASTE_MAX_LINES`` lines."""
    rows = [row for row in text.splitlines() if row.strip()]
    if len(rows) > PASTE_MAX_LINES:
        raise ValueError(TOO_MANY_TEXT.format(limit=PASTE_MAX_LINES))
    base = min((len(row) - len(row.lstrip()) for row in rows), default=0)    # a whole list may be indented
    items: list[PasteItem] = []
    for row in rows:
        body = _clean(row)
        if not body:
            continue
        if len(row) - len(row.lstrip()) > base and items:
            last = items[-1]
            items[-1] = PasteItem(last.line, (*last.steps, body))
        else:
            items.append(PasteItem(body))
    return tuple(items)
