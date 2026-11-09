"""A page that answered with a server error is loaded again (owner, 2026-10-31: "when it hits an error, just reload
the page"). Upwork's job page answered 500 ("We'll be right back") and the bot gave up at once.

``open_page`` hands its first page here: on a 5xx status the page's plain address is tried first, with no wait, when
it has one (owner, 2026-11-01: Upwork's list popup answers 500 every time while the job's own page answers 200;
``roost/talk/plain_address.py``). Then the bot says so, waits each of ``SERVER_ERROR_RELOAD_WAITS_S`` in turn and loads
the page again, stopping at the first answer that is not a server error. A page that stays broken gets a fixed notice
the tool result starts with; it never claims the site is down for sure, since one address can fail alone. A reload that
fails keeps the page there was. Never a word of the page in the notice."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Awaitable, Callable

from roost.constants import SERVER_ERROR_RELOAD_WAITS_S
from roost.desk import PageText

logger = logging.getLogger(__name__)

Fetch = Callable[[], Awaitable[PageText]]

SERVER_ERROR_ACTIVITY = "the site answered with an error, loading it again"
SERVER_ERROR_PLAIN_ACTIVITY = "the site answered with an error, trying the page's plain address"
SERVER_ERROR_DOWN_TEXT = ("The page answered with a server error ({status}) {tries} times. The site may be down, or "
                          "this exact address may not open on its own: open the site's main page and reach it from "
                          "there before saying the site is down. Nothing was done there.")
_SERVER_ERROR_MIN, _SERVER_ERROR_MAX = 500, 599


def is_server_error(status: int | None) -> bool:
    return status is not None and _SERVER_ERROR_MIN <= status <= _SERVER_ERROR_MAX


async def _try_plain(plain: Fetch, announce: Callable[[str], Awaitable[None]]) -> PageText | None:
    await announce(SERVER_ERROR_PLAIN_ACTIVITY)
    try:
        page = await plain()
    except Exception as exc:              # the plain address failed to load: go on with reloads
        logger.warning("Loading a page's plain address after a server error failed: %s", type(exc).__name__)
        return None
    return None if is_server_error(page.status) else page


async def reload_on_server_error(
    page: PageText, fetch: Fetch, *, plain: Fetch | None = None,
    sleep: Callable[[float], Awaitable[None]], announce: Callable[[str], Awaitable[None]],
) -> tuple[PageText, Fetch]:
    """``page`` as it is when it is no server error, else the plain address when it works, else the first reload that
    is not one, else the last answer with the notice; with the fetch that gave it, for later repeats."""
    if not is_server_error(page.status):
        return page, fetch
    if plain is not None and (good := await _try_plain(plain, announce)) is not None:
        return good, plain
    tries = 1
    for wait in SERVER_ERROR_RELOAD_WAITS_S:
        await announce(SERVER_ERROR_ACTIVITY)
        await sleep(wait)
        try:
            page = await fetch()
        except Exception as exc:          # the reload itself failed: keep what there was, say the site is down
            logger.warning("Reloading a page after a server error failed: %s", type(exc).__name__)
            break
        tries += 1
        if not is_server_error(page.status):
            return page, fetch
    return replace(page, notice=SERVER_ERROR_DOWN_TEXT.format(status=page.status, tries=tries)), fetch
