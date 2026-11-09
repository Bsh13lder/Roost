"""The sites a run that carries on after a card may still open (Gela, 2026-11-04).

A run of your own chat may open any safe site itself (W6/W7, ``fresh_open``); the run that carries on after you
cleared its Stuck card or answered its Ask card is a ``card_answer`` run, which is not your own chat, so it is
link-guarded. It keeps, as ``host:`` entries in its item's link scope:

- the site the Stuck card was about (server-made from the block: the page the run was on, or the site it asked you
  to sign in to, which D4 already limited to its open page or its link scope);
- the sites the parked run opened itself while it was your own chat's run (``fresh_open``, or a click the gate let
  go to another site), saved on the parked run's work items when it parked or stopped on a block.

Only sites the gate itself let the run open are carried, never a link a page held: a page never widens the scope.
Carried sites ride on from one continue run to the next, and they join that run's computer fence too."""

from __future__ import annotations

from typing import Iterable

from roost.talk.link_scope import HOST_PREFIX
from roost.talk.new_site import fresh_site
from roost.work.models import WorkItem, WorkKind
from roost.work.queue import WorkQueue

# The parked items whose stored scope may be carried: your own messages, and continue items (whose scope is only
# ever server-made). A handoff's or a room's scope holds links a page named, so it is never carried.
_CARRIES_FROM = frozenset({WorkKind.MESSAGE, WorkKind.CARD_ANSWER})


def site_entries(sites: Iterable[str]) -> tuple[str, ...]:
    """``host:`` entries for bare sites, sorted and without repeats."""
    return tuple(f"{HOST_PREFIX}{site}" for site in sorted({site for site in sites if site}))


def card_site_entries(url: str) -> tuple[str, ...]:
    """The card's own address and its whole site (``host:`` without ``www.``); nothing for an unsafe address."""
    site = fresh_site(url) if url else ""
    return (url, *site_entries((site,))) if site else ((url,) if url else ())


def _sites_in(scope: Iterable[str]) -> frozenset[str]:
    return frozenset(entry[len(HOST_PREFIX):] for entry in scope if entry.startswith(HOST_PREFIX))


def carried_sites(items: Iterable[WorkItem]) -> frozenset[str]:
    """The sites a run's continue items carry in (only ``card_answer`` items: their scope is server-made)."""
    return frozenset(site for item in items if item.kind is WorkKind.CARD_ANSWER for site in _sites_in(item.link_scope))


async def keep_sites(queue: WorkQueue, user_id: str, items: Iterable[WorkItem], sites: Iterable[str]) -> None:
    """Save the sites a run that stops on a card may still open on its items, for the run that carries on."""
    entries = site_entries(sites)
    ids = tuple(item.id for item in items if item.kind in _CARRIES_FROM)
    if entries and ids:
        await queue.set_link_scope(user_id, ids, entries)


async def parked_site_entries(queue: WorkQueue, user_id: str, item_id: str | None) -> tuple[str, ...]:
    """The ``host:`` entries the parked run's item kept; nothing for another kind of item or an unknown id."""
    item = await queue.get(user_id, item_id) if item_id else None
    if item is None or item.kind not in _CARRIES_FROM:
        return ()
    return site_entries(_sites_in(item.link_scope))


def joined(*scopes: Iterable[str]) -> tuple[str, ...]:
    """The scopes one after another, without repeats."""
    return tuple(dict.fromkeys(entry for scope in scopes for entry in scope if entry))
