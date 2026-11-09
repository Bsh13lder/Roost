"""``line_diff``: the unified, line-based diff a Mac edit card shows."""

from __future__ import annotations

import difflib

from roost.approvals.models import DiffView

CONTEXT_LINES = 3


def line_diff(old: str, new: str) -> DiffView:
    """Changed lines with ``CONTEXT_LINES`` of context, no file header lines, and the counts of lines
    added and removed. Empty text and counts of 0 when nothing changed."""
    lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=CONTEXT_LINES))
    body = [line for line in lines if not line.startswith(("---", "+++"))]
    plus = sum(1 for line in body if line.startswith("+"))
    minus = sum(1 for line in body if line.startswith("-"))
    return DiffView("\n".join(body), plus, minus)
