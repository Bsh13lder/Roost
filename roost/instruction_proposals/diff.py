"""A line diff for the instructions card: what stays, what goes, what comes in, in reading order."""

from __future__ import annotations

from difflib import SequenceMatcher


def _lines(text: str) -> list[str]:
    return text.split("\n") if text else []


def line_diff(before: str, after: str) -> tuple[dict, ...]:
    """``[{op: same | del | add, text}]``: a changed block lists its removed lines before its added ones."""
    old, new = _lines(before), _lines(after)
    out: list[dict] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
        if tag == "equal":
            out.extend({"op": "same", "text": line} for line in old[i1:i2])
            continue
        out.extend({"op": "del", "text": line} for line in old[i1:i2])
        out.extend({"op": "add", "text": line} for line in new[j1:j2])
    return tuple(out)
