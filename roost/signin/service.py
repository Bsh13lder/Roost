"""``SignInService``: Open sign-in, the "No, this time" clear after the task, and Sign out (the Sign-in card).

- ``open_sign_in``: the card's own page on the bot's Linux computer (opened only when the computer is elsewhere),
  then you take control. You type the password yourself on the live screen; nothing here reads it.
- ``clear_pending`` (after each of the bot's runs) and ``sweep_on_boot``: a "No, this time" login waits for the whole
  task: while its continue item is queued or running, the bot has other queued work, or the bot has an open Ask,
  Proposal, options or Stuck card (a parked run), nothing is cleared. Then its site is cleared in the bot's Chromium
  and its Vault row goes. A clear that fails keeps the row, so it is tried again after the next run. A bot now on
  Mac Brave keeps the row (no Linux computer is started for it); a gone bot's rows are dropped.
- ``sign_out``: clears a kept login's site the same way, then removes it. Linux only.

Every lookup names ``user_id``: another user's card, bot or login is ``None`` (the routes answer 404). Logs carry
ids only, never a host or a label."""

from __future__ import annotations

import logging

from roost.approvals.store import ApprovalStore
from roost.bots.models import Bot
from roost.bots.store import BotStore
from roost.desk import DeskAsleep, DeskBusy, DeskFactory, DeskUnavailable
from roost.desk.control import ControlLock
from roost.desk.site_data import BadHost, SiteCleared
from roost.desk.stuck import host_of_url
from roost.desk.url_policy import check_url
from roost.stuck.models import CardClosed, CardState, NotSignInCard, StuckCard
from roost.stuck.store import StuckStore
from roost.vault.models import SiteLogin
from roost.vault.store import VaultStore
from roost.work.models import WorkState
from roost.work.queue import WorkQueue

logger = logging.getLogger(__name__)

_LINUX = "linux"
_STILL_RUNNING = frozenset({WorkState.QUEUED, WorkState.CLAIMED})
_CLEAR_FAILED = (DeskUnavailable, DeskBusy, DeskAsleep)


class SignOutLinuxOnly(Exception):
    """Sign out on a Mac Brave bot: Roost never touches your main Brave's logins (the route answers 400)."""


class SignInService:
    def __init__(self, stuck: StuckStore, vault: VaultStore, bots: BotStore, desks: DeskFactory,
                 control: ControlLock, queue: WorkQueue, approvals: ApprovalStore) -> None:
        self._stuck = stuck
        self._vault = vault
        self._bots = bots
        self._desks = desks
        self._control = control
        self._queue = queue
        self._approvals = approvals

    async def open_sign_in(self, user_id: str, card_id: str) -> StuckCard | None:
        """Open sign-in. ``None``: not your card. ``CardClosed`` / ``NotSignInCard``; ``DeskUnavailable`` or
        ``DeskBusy`` when the computer can't be reached (control is not taken then)."""
        card = await self._stuck.get(user_id, card_id)
        if card is None:
            return None
        if card.state is not CardState.OPEN:
            raise CardClosed(card_id)
        bot = await self._bots.get(user_id, card.bot_id)
        if not card.sign_in or bot is None or bot.computer != _LINUX:
            raise NotSignInCard(card_id)      # a bot switched to Mac Brave since: no Linux computer is started
        desk = self._desks.for_bot(card.bot_id, _LINUX)
        if card.url and host_of_url(await desk.current_url()) != card.host:
            await desk.open_page(check_url(card.url))
        self._control.take(card.bot_id)
        return card

    async def after_run(self, user_id: str, bot_id: str) -> None:
        """The runner's hook after each run: never raises (a failure is logged and tried again later)."""
        try:
            await self.clear_pending(user_id, bot_id)
        except Exception:
            logger.exception("Clearing pending sign-ins failed for bot %s", bot_id)

    async def clear_pending(self, user_id: str, bot_id: str) -> None:
        logins = await self._vault.pending_clears(user_id, bot_id)
        if not logins:
            return
        bot = await self._bots.get(user_id, bot_id)
        if bot is None:
            await self._drop(user_id, bot_id, logins)
            return
        if bot.computer != _LINUX or await self._task_goes_on(user_id, bot):
            return
        for login in logins:
            if await self._still_running(user_id, login.clear_after_item_id):
                continue
            await self._clear_and_forget(user_id, login)

    async def sweep_on_boot(self) -> None:
        """Boot: the pending clears of every user's bots whose tasks ended while Roost was down."""
        for user_id, bot_id in await self._vault.pending_bots():
            await self.after_run(user_id, bot_id)

    async def sign_out(self, user_id: str, bot_id: str, login_id: str) -> SiteCleared | None:
        """Sign out: clear the login's site in the bot's Linux Chromium, then remove the login. ``None``: not
        your bot or login. ``SignOutLinuxOnly``, ``BadHost``, ``DeskUnavailable`` or ``DeskBusy`` keep it."""
        bot = await self._bots.get(user_id, bot_id)
        login = await self._vault.get(user_id, login_id, bot_id) if bot is not None else None
        if bot is None or login is None:
            return None
        if bot.computer != _LINUX:
            raise SignOutLinuxOnly(bot_id)
        cleared = await self._desks.for_bot(bot_id, _LINUX).clear_site_data(login.host)
        await self._vault.forget(user_id, login.id, bot_id)
        return cleared

    async def _task_goes_on(self, user_id: str, bot: Bot) -> bool:
        """The bot's task isn't over: more work is queued, or a run is parked on an open card."""
        return (await self._queue.first_queued(user_id, bot.id) is not None
                or await self._approvals.open_for_bot(user_id, bot.id) is not None
                or await self._stuck.open_for_bot(user_id, bot.id) is not None)

    async def _drop(self, user_id: str, bot_id: str, logins: tuple[SiteLogin, ...]) -> None:
        logger.warning("Bot %s is gone; dropping its %d pending sign-in clears", bot_id, len(logins))
        for login in logins:
            await self._vault.forget(user_id, login.id, bot_id)

    async def _still_running(self, user_id: str, item_id: str | None) -> bool:
        if not item_id:
            return False
        item = await self._queue.get(user_id, item_id)
        return item is not None and item.state in _STILL_RUNNING

    async def _clear_and_forget(self, user_id: str, login: SiteLogin) -> None:
        try:
            await self._desks.for_bot(login.bot_id, _LINUX).clear_site_data(login.host)
        except BadHost:
            logger.warning("Sign-in %s of bot %s names no site Roost can clear; it is dropped", login.id, login.bot_id)
        except _CLEAR_FAILED:
            logger.warning("Could not clear sign-in %s of bot %s yet; trying again later", login.id, login.bot_id,
                           exc_info=True)
            return
        await self._vault.forget(user_id, login.id, login.bot_id)
