"""The Open card: an address a guarded run may not open by itself (owner decision 2026-10-23).

A site you name or link opens directly (``LinkScope``). Any other address, in a run that can show you a card,
asks you once: "Open web.whatsapp.com", the whole address shown, Open or No. Your Yes opens exactly the stored
address (``PageOpens``) and counts as a new-site approval for this chat, so the run that carries on may open it
(the card answer's link scope) and the computer may browse it (``approved_site_hosts``). Nobody watching (a
routine, a handoff, a room) keeps the plain refusal. An address no card could make safe (credentials, a port, a
backslash, a scheme other than http(s), a local or private host) is never opened.

W6 (owner, 2026-10-24): a fresh run of your own chat opens any address ``askable_url`` accepts with no card
(``roost/talk/gate.py``), and ``fresh_site`` names the site it may then keep browsing."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

from roost.approvals.models import ArgRow, PendingCall, StepOutcome
from roost.desk import DeskAsleep, DeskBusy, DeskUnavailable
from roost.desk.url_policy import UrlBlocked, check_url
from roost.talk.link_scope import HOST_PREFIX

logger = logging.getLogger(__name__)

OPEN_PAGE = "open_page"
NEW_SITE = "new_site"

OPENED_TEXT = "Opened {host}. Read the page or look at the screen to carry on."
NOT_OPENED_TEXT = "I couldn't open {host} just now, so nothing was opened."
UNSAFE_ADDRESS_TEXT = (
    "I didn't open that address: Roost never opens a link with a password or a port in it, a local or private "
    "address, or anything but an http or https page."
)
_DOES = "Opens {host} in my browser"
_WWW = "www."


def askable_url(url: Any) -> str | None:
    """The canonical address a card may offer, or None when no card could make it safe."""
    if not isinstance(url, str) or not url.strip() or "\\" in url or any(c.isspace() for c in url.strip()):
        return None
    try:
        canonical = check_url(url.strip())
    except UrlBlocked:
        return None
    parts = urlsplit(canonical)
    if (parts.scheme not in ("http", "https") or parts.username is not None or parts.password is not None
            or parts.port is not None or not parts.hostname):
        return None
    return canonical


def url_host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def fresh_site(url: str) -> str:
    """W6: the site a fresh run opened (its host without ``www.``), or "" for an address no card could offer."""
    canonical = askable_url(url)
    host = url_host(canonical) if canonical is not None else ""
    return host[len(_WWW):] if host.startswith(_WWW) and host.count(".") > 1 else host


def page_step(url: str) -> PendingCall:
    """The Open card's one step: the stored call is exactly ``open_page`` on this address."""
    host = url_host(url)
    rows = (ArgRow("site", "Site", host), ArgRow("url", "Address", url), ArgRow("does", "What it does",
                                                                               _DOES.format(host=host)))
    return PendingCall(tool=OPEN_PAGE, arguments={"url": url}, topic=None, title=f"Open {host}",
                       floor=NEW_SITE, rows=rows)


def open_card_host(step: PendingCall) -> str | None:
    """The site an approved Open card lets this chat use; None for any other step."""
    if step.tool != OPEN_PAGE or step.floor != NEW_SITE:
        return None
    url = askable_url(step.arguments.get("url"))
    return url_host(url) if url is not None else None


def approved_scope(step: PendingCall) -> tuple[str, ...]:
    """The link-scope entries a Yes on an Open card hands the run that carries on: the address and its site."""
    host = open_card_host(step)
    return () if host is None else (str(step.arguments["url"]), f"{HOST_PREFIX}{host}")


class PageOpens:
    """Runs an approved Open card outside any run: the bot's own browser opens the stored address."""

    def __init__(self, bots: Any, desks: Any) -> None:
        self._bots = bots
        self._desks = desks

    async def open(self, user_id: str, card: Any, step: PendingCall) -> StepOutcome:
        url = askable_url(step.arguments.get("url"))
        bot = await self._bots.get(user_id, card.bot_id)
        if url is None or bot is None:
            return StepOutcome(False, NOT_OPENED_TEXT.format(host="that site"))
        host = url_host(url)
        try:
            await self._desks.for_bot(bot.id, bot.computer).open_page(url)
        except (DeskAsleep, DeskBusy, DeskUnavailable, UrlBlocked) as exc:
            logger.warning("An approved open of bot %s failed: %s", bot.id, type(exc).__name__)
            return StepOutcome(False, NOT_OPENED_TEXT.format(host=host))
        return StepOutcome(True, OPENED_TEXT.format(host=host), tainted=True)
