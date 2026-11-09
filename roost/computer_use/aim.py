"""An act aimed by a look's number (fast pages, slice 2): the number becomes a live control, or a refusal.

The number names a backend node from the newest look (``PageMarks``). It is read again on the live page
(``target_for``: still there and in view) and must still be the same control (``same_mark``) on the same page
address. Only then does the runner build the resolution the gate judges, from that live control. A card's
approved re-run names the stored control instead (``pinned``), and ``same_target`` checks the rest."""

from __future__ import annotations

from dataclasses import replace

from roost.computer_use.marks import PageMarks, same_mark, same_page
from roost.computer_use.models import PageTarget, without_counts
from roost.computer_use.texts import NO_MARK_TEXT, STALE_MARK_TEXT


async def indexed(page, marks: PageMarks, index: int, url: str) -> tuple[PageTarget | None, str]:
    """The live control for ``index``, or None and the sentence why not."""
    stored = marks.control(index)
    if stored is None:
        return None, NO_MARK_TEXT.format(index=index)
    if not same_page(marks.url, url):
        return None, STALE_MARK_TEXT.format(index=index)
    live = await pinned(page, stored)
    if live is None:
        return None, STALE_MARK_TEXT.format(index=index)
    return live, ""


def _counts_aside(target: PageTarget) -> PageTarget:
    return replace(target, text=without_counts(target.text), visible_text=without_counts(target.visible_text),
                   form_submit_text=without_counts(target.form_submit_text))


async def pinned(page, stored: PageTarget | None, *, counts_free: bool = False) -> PageTarget | None:
    """The stored control read again from the live page, when it is still the same control and in view.
    ``counts_free`` (a card's send, submit or accept, owner 2026-11-03): a count in its label may have changed."""
    if stored is None:
        return None
    live = await page.target_for(stored.node_id)
    if live is None:
        return None
    if same_mark(stored, live):
        return live
    return live if counts_free and same_mark(_counts_aside(stored), _counts_aside(live)) else None
