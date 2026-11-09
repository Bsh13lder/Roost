"""A scroll call as inputs the computer takes (fast pages, slice 6).

A ``scroll`` may ask for up to ``CU_SCROLL_MAX_NOTCHES``; the keeper and the computer's ``roost-input`` take at most
``CU_SCROLL_NOTCHES_PER_INPUT`` per input, so a bigger scroll goes out in pieces (no computer image change)."""

from __future__ import annotations

from roost.constants import CU_SCROLL_NOTCHES_PER_INPUT


def scroll_pieces(notches: int) -> tuple[int, ...]:
    """``notches`` (signed; down is positive) as inputs of at most ``CU_SCROLL_NOTCHES_PER_INPUT`` each."""
    sign, left = (1 if notches > 0 else -1), abs(notches)
    pieces: list[int] = []
    while left > 0:
        piece = min(left, CU_SCROLL_NOTCHES_PER_INPUT)
        pieces.append(sign * piece)
        left -= piece
    return tuple(pieces)
