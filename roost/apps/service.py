"""``AppService``: the one place that reaches a bot's computer for apps (docs/plans/2026-10-22-roost-install-app.md).

Every call names the user and checks the bot is theirs and on its Linux computer, wakes the computer through the
desk (the room decides), then goes through the keeper seam. Results are plain sentences; nothing the computer says
reaches a bot except the fixed words, mapped here."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from roost.apps import texts
from roost.apps.audit import AppAudit
from roost.apps.constants import APPS_PER_BOT_MAX
from roost.apps.keeper import AppKeeper, AppRefused
from roost.apps.models import AppInfo, BotApp
from roost.apps.names import package_refusal
from roost.apps.store import AppBotNotFound, AppStore
from roost.bots.models import Bot
from roost.computer_use.tool_specs import LINUX_COMPUTER
from roost.config import Config
from roost.desk import DeskBusy, DeskUnavailable

logger = logging.getLogger(__name__)

_WORDS = {
    "denied": texts.DENIED, "not_found": texts.NOT_FOUND, "not_debian": texts.NOT_DEBIAN,
    "already_installed": texts.ALREADY, "would_remove_others": texts.WOULD_REMOVE_OTHERS,
}


class AppUnavailable(RuntimeError):
    """The computer could not be reached; ``text`` says so in plain words."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


@dataclass(frozen=True)
class AppResult:
    ok: bool
    text: str


class AppService:
    def __init__(self, config: Config, store: AppStore, keeper: AppKeeper, bots: Any, desks: Any) -> None:
        self._store, self._keeper, self._bots, self._desks = store, keeper, bots, desks
        self._audit = AppAudit(config)

    @property
    def store(self) -> AppStore:
        return self._store

    async def linux_bot(self, user_id: str, bot_id: str) -> Bot | str:
        """The user's bot on its Linux computer, or the sentence that says why not."""
        bot = await self._bots.get(user_id, bot_id)
        if bot is None:
            return texts.BOT_NOT_FOUND
        return bot if bot.computer == LINUX_COMPUTER else texts.LINUX_ONLY

    async def _wake(self, bot_id: str) -> None:
        try:
            await self._desks.for_bot(bot_id, LINUX_COMPUTER).start_browser()
        except DeskBusy as exc:
            raise AppUnavailable(texts.BUSY) from exc
        except DeskUnavailable as exc:
            raise AppUnavailable(texts.UNREACHABLE) from exc

    async def describe(self, user_id: str, bot_id: str, package: str) -> AppInfo | str:
        """Debian's words for a package not yet on the computer, or the sentence that refuses it."""
        refused = await self._precheck(user_id, bot_id, package)
        if refused is not None:
            return refused
        if await self._store.find(user_id, bot_id, package) is not None:
            return texts.ALREADY.format(package=package)
        if len(await self._store.list_for_bot(user_id, bot_id)) >= APPS_PER_BOT_MAX:
            return texts.TOO_MANY
        try:
            await self._wake(bot_id)
            return await self._keeper.describe(bot_id, package)
        except AppUnavailable as exc:
            return exc.text
        except AppRefused as exc:
            return _said(exc.word, package, texts.UNREACHABLE)
        except DeskUnavailable:
            return texts.UNREACHABLE

    async def install(self, user_id: str, bot_id: str, package: str, *, tainted: bool) -> AppResult:
        refused = await self._precheck(user_id, bot_id, package)
        if refused is not None:
            return AppResult(False, refused)
        try:
            await self._wake(bot_id)
            await self._keeper.install(bot_id, package)
        except (AppUnavailable, AppRefused, DeskUnavailable) as exc:
            logger.warning("installing an app for bot %s failed: %s", bot_id, type(exc).__name__)
            await self._audit.record(user_id, bot_id, "install_app", "install_failed", tainted=tainted)
            return AppResult(False, _failure_text(exc, package, texts.FAILED))
        await self._store.add(user_id, bot_id, package, tainted=tainted)
        await self._audit.record(user_id, bot_id, "install_app", "installed", tainted=tainted)
        return AppResult(True, texts.INSTALLED.format(package=package))

    async def remove(self, user_id: str, bot_id: str, package: str, *, tainted: bool = False) -> AppResult:
        """Remove one package install_app put there (the bot's card, after the owner's Yes)."""
        refused = await self._precheck(user_id, bot_id, package)
        if refused is not None:
            return AppResult(False, refused)
        app = await self._store.find(user_id, bot_id, package)
        if app is None:
            return AppResult(False, texts.NOT_MINE.format(package=package))
        return await self._remove(user_id, app, "removed", tainted=tainted)

    async def owner_remove(self, user_id: str, bot_id: str, app_id: str) -> Literal["removed", "not_found"]:
        """The owner's own Remove: no card. ``AppUnavailable`` when the computer can't be reached (the row stays)."""
        app = await self._store.get(user_id, bot_id, app_id)
        if app is None:
            return "not_found"
        result = await self._remove(user_id, app, "owner_removed", tainted=False)
        if not result.ok:
            raise AppUnavailable(result.text)
        return "removed"

    async def _remove(self, user_id: str, app: BotApp, done: Literal["removed", "owner_removed"], *,
                      tainted: bool) -> AppResult:
        try:
            await self._wake(app.bot_id)
            await self._keeper.remove(app.bot_id, app.package)
        except AppRefused as exc:
            if exc.word != "not_installed":       # already gone from the computer: only the row is left
                return await self._remove_failed(user_id, app, exc, tainted)
        except (AppUnavailable, DeskUnavailable) as exc:
            return await self._remove_failed(user_id, app, exc, tainted)
        await self._store.delete(user_id, app.bot_id, app.id)
        await self._audit.record(user_id, app.bot_id, "remove_app", done, tainted=tainted)
        return AppResult(True, texts.REMOVED.format(package=app.package))

    async def _remove_failed(self, user_id: str, app: BotApp, exc: Exception, tainted: bool) -> AppResult:
        logger.warning("removing an app for bot %s failed: %s", app.bot_id, type(exc).__name__)
        await self._audit.record(user_id, app.bot_id, "remove_app", "remove_failed", tainted=tainted)
        return AppResult(False, _failure_text(exc, app.package, texts.REMOVE_FAILED))

    async def reinstall(self, bot_id: str) -> None:
        """A fresh computer: put the owner's approved apps back with one ensure. Never raises."""
        try:
            user_id = await self._store.owner_of(bot_id)
            if user_id is None:
                return
            packages = await self._store.packages(user_id, bot_id)
            if not packages:
                return
            try:
                await self._keeper.ensure(bot_id, packages)
            except (AppRefused, DeskUnavailable) as exc:
                logger.warning("reinstalling the apps of bot %s failed: %s", bot_id, type(exc).__name__)
                await self._audit.record(user_id, bot_id, "reinstall_app", "reinstall_failed")
        except Exception:     # a background job: a failure is a log line, never a crash
            logger.exception("reinstalling the apps of bot %s failed", bot_id)

    async def _precheck(self, user_id: str, bot_id: str, package: str) -> str | None:
        refused = package_refusal(package)
        if refused is not None:
            return refused
        bot = await self.linux_bot(user_id, bot_id)
        return bot if isinstance(bot, str) else None


def _said(word: str, package: str, otherwise: str) -> str:
    template = _WORDS.get(word)
    return otherwise if template is None else template.format(package=package)


def _failure_text(exc: Exception, package: str, otherwise: str) -> str:
    if isinstance(exc, AppUnavailable):
        return exc.text
    if isinstance(exc, AppRefused):
        return _said(exc.word, package, otherwise.format(package=package))
    return otherwise.format(package=package)


__all__ = ["AppBotNotFound", "AppResult", "AppService", "AppUnavailable"]
