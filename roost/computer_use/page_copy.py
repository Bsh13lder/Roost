"""Did the text a card shows come from a page? (Owner, 2026-11-03: the red "from web content" mark sat on every Send
card because the bot had looked at a page.)

The run keeps the page text its looks, glances and reads brought back (in memory only, the newest ``SEEN_MAX_CHARS``),
with the text the run had typed by then taken out (a box's own text can show in the page text). Text counts as copied
from a page when it holds a run of ``COPY_RUN_WORDS`` words in a row that a page showed. This only decides the card's
mark; every gate decision still follows the run's taint."""

from __future__ import annotations

import html
from typing import Iterable

from roost.computer_use.text_source import flat

COPY_RUN_WORDS = 10                  # a phrase this long in a row is a copy, not a shared word or two
SEEN_MAX_CHARS = 200_000             # the newest page text a run keeps for the check


def keep_seen(seen: str, text: str, typed: Iterable[str] = ()) -> str:
    """``seen`` with ``text`` (an escaped ``<untrusted_page>`` reply) added, minus the run's own ``typed`` text, cut to
    the newest ``SEEN_MAX_CHARS``."""
    added = flat(html.unescape(text)).casefold()
    for own in typed:
        mine = flat(own).casefold()
        if mine:
            added = added.replace(mine, " ")
    return f"{seen} {added}"[-SEEN_MAX_CHARS:] if added.strip() else seen


def _runs(words: list[str]) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + COPY_RUN_WORDS]) for i in range(len(words) - COPY_RUN_WORDS + 1)}


def copied_from_page(texts: Iterable[str], seen: str) -> bool:
    """True when any of ``texts`` repeats ``COPY_RUN_WORDS`` words in a row from ``seen``."""
    shown = _runs(seen.split())
    return bool(shown) and any(_runs(flat(text).casefold().split()) & shown for text in texts)
