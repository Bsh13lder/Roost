"""``apply_edits``: the old-text/new-text edits of ``mac_edit``, each of which must match exactly once."""

from __future__ import annotations

from typing import Mapping, Sequence


class EditError(ValueError):
    """An edit that cannot be applied. The message is a plain sentence for the bot."""


def apply_edits(text: str, edits: Sequence[Mapping[str, str]]) -> str:
    """Apply ``edits`` in order, each to the text the earlier ones left. A new object comes back."""
    current = text
    for number, edit in enumerate(edits, start=1):
        old, new = edit["old"], edit["new"]
        count = current.count(old) if old else 0
        if count != 1:
            raise EditError(f"Edit {number}: its old text appears {count} times; it must appear once.")
        current = current.replace(old, new, 1)
    return current
