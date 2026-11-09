"""The tail of a capped listing (M2 D3): how many records are left and how to
get them, so "save ALL my tasks in a document" can page through every one."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

# The ``offset`` argument of every paged listing's tool spec (copied with dict() into each spec).
OFFSET_PROPERTY: Mapping[str, Any] = MappingProxyType({
    "type": "integer", "minimum": 0,
    "description": "Skip this many, to get the rest after a listing that ends with '…and N more'.",
})


def more_line(total: int, offset: int, shown: int) -> str:
    rest = total - offset - shown
    return f"\n…and {rest} more: call again with offset={offset + shown}." if rest > 0 else ""
