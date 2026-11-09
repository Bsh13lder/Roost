"""Does the bot's computer look signed in to the card's site? (owner, 2026-10-23, A1).

I'm done on a Sign-in card saves a Vault login only when the answer is yes: the sign-in page detector
(``roost/desk/stuck.py``) sees no sign-in or code page on the bot's front tab, and the browser holds at least one
cookie for the host or a parent domain (``roost/desk/site_data.py``, fixed CDP, the host validated). A bot that is
not on its Linux computer (Mac Brave) is never read: the answer is unchanged there."""

from __future__ import annotations

import logging

from roost.bots.store import BotStore
from roost.desk import DeskAsleep, DeskFactory, PageText
from roost.desk.site_data import BadHost
from roost.desk.stuck import detect_block

logger = logging.getLogger(__name__)

_LINUX = "linux"
_SIGN_IN_REASONS = frozenset({"login", "code"})


class NotSignedInYet(Exception):
    """The computer doesn't look signed in to the card's site: nothing is saved and the card stays open."""

    def __init__(self, host: str) -> None:
        super().__init__(host)
        self.host = host


def looks_signed_in(page: PageText, cookies: int) -> bool:
    """No sign-in (or code) page in front, and at least one cookie for the site."""
    block = detect_block(page)
    return cookies > 0 and (block is None or block.reason not in _SIGN_IN_REASONS)


class SignInCheck:
    """``require(user_id, bot_id, host)`` raises ``NotSignedInYet`` unless the bot's Linux computer looks signed
    in. ``DeskUnavailable`` / ``DeskBusy`` pass through (the route answers 503 / 409, the card stays open)."""

    def __init__(self, bots: BotStore, desks: DeskFactory) -> None:
        self._bots = bots
        self._desks = desks

    async def require(self, user_id: str, bot_id: str, host: str) -> None:
        bot = await self._bots.get(user_id, bot_id)
        if bot is None or bot.computer != _LINUX:
            return
        try:
            signals = await self._desks.for_bot(bot_id, _LINUX).sign_in_signals(host)
        except (BadHost, DeskAsleep):
            logger.info("Bot %s's sign-in could not be checked; nothing is saved", bot_id)
            raise NotSignedInYet(host) from None
        if not looks_signed_in(signals.page, signals.cookies):
            raise NotSignedInYet(host)
