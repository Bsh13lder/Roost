"""``GrantService``: add, change and revoke the folders the user shares, and keep the keeper's
copy current. ``GrantSync`` pushes the whole set on boot and every ``MAC_GRANT_PUSH_INTERVAL_S``,
so a keeper that restarted gets its grants back within seconds.

Refusals are ``GrantRefused`` with a plain sentence (HTTP 422), or ``DeskUnavailable`` when the
keeper is away. Logs carry ids and exception type names only: never a path or a label."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Awaitable, Callable

from roost.bots.store import BotStore
from roost.constants import MAC_GRANT_PUSH_INTERVAL_S, MAC_GRANTS_MAX, MAC_LABEL_MAX_CHARS
from roost.desk import DeskUnavailable
from roost.keeper.macfs.errors import MacFsError
from roost.mac.files import MacFiles
from roost.mac.grants import GrantStore
from roost.mac.models import Access, Grant, GrantDraft, ReadPolicy
from roost.mac.texts import (
    GRANT_LIMIT_TEXT, LABEL_BAD_TEXT, LABEL_TAKEN_TEXT, NO_SUCH_BOT_TEXT, folder_error_text,
)

log = logging.getLogger(__name__)

RevokeHook = Callable[[str, str], Awaitable[None] | None]


class GrantRefused(Exception):
    """A grant request the user can fix. The message is a plain sentence for the screen."""


def _noop_revoke_hook(user_id: str, grant_id: str) -> None:
    return None


def clean_label(label: str) -> str:
    cleaned = " ".join(label.split())
    if not cleaned or len(cleaned) > MAC_LABEL_MAX_CHARS:
        raise GrantRefused(LABEL_BAD_TEXT)
    return cleaned


class GrantService:
    def __init__(self, store: GrantStore, bots: BotStore, files: MacFiles,
                 on_revoke: RevokeHook = _noop_revoke_hook) -> None:
        self._store, self._bots, self._files, self._on_revoke = store, bots, files, on_revoke

    def set_revoke_hook(self, hook: RevokeHook) -> None:
        """Task 8 ends that grant's session OKs here."""
        self._on_revoke = hook

    async def list_all(self, user_id: str) -> tuple[Grant, ...]:
        return await self._store.list_live(user_id)

    async def for_bot(self, user_id: str, bot_id: str) -> tuple[Grant, ...] | None:
        """This bot's grants and the all-bots ones; ``None`` when the bot is not the user's."""
        if await self._bots.get(user_id, bot_id) is None:
            return None
        return await self._store.list_for_bot(user_id, bot_id)

    async def all_live(self) -> tuple[Grant, ...]:
        return await self._store.all_live()

    async def add(self, user_id: str, *, path: str, label: str, access: Access, read_policy: ReadPolicy,
                  bot_id: str | None) -> Grant:
        label = clean_label(label)
        if bot_id is not None and await self._bots.get(user_id, bot_id) is None:
            raise GrantRefused(NO_SUCH_BOT_TEXT)
        live = await self._store.list_live(user_id)
        if len(live) >= MAC_GRANTS_MAX:
            raise GrantRefused(GRANT_LIMIT_TEXT)
        self._require_unique(live, label)
        try:
            checked = await self._files.check_folder(path)
        except MacFsError as exc:
            raise GrantRefused(folder_error_text(exc.code)) from None
        grant = await self._store.create(user_id, GrantDraft(bot_id, checked.resolved, label, access, read_policy, checked.is_vault))
        await self._push()
        return grant

    async def update(self, user_id: str, grant_id: str, *, label: str | None, access: Access | None,
                     read_policy: ReadPolicy | None) -> Grant | None:
        current = await self._store.get(user_id, grant_id)
        if current is None:
            return None
        new_label = clean_label(label) if label is not None else current.label
        if label is not None:
            self._require_unique(tuple(g for g in await self._store.list_live(user_id) if g.id != grant_id), new_label)
        changed = await self._store.update(
            user_id, grant_id, label=new_label, access=access or current.access,
            read_policy=read_policy or current.read_policy,
        )
        if changed is not None:
            await self._push()
        return changed

    async def revoke(self, user_id: str, grant_id: str) -> Grant | None:
        grant = await self._store.revoke(user_id, grant_id)
        if grant is None:
            return None
        outcome = self._on_revoke(user_id, grant_id)
        if outcome is not None:
            await outcome
        await self._push()
        return grant

    async def pick_folder(self) -> str | None:
        try:
            return await self._files.pick_folder()
        except MacFsError as exc:
            raise GrantRefused(folder_error_text(exc.code)) from None

    @staticmethod
    def _require_unique(live: tuple[Grant, ...], label: str) -> None:
        if any(g.label.casefold() == label.casefold() for g in live):
            raise GrantRefused(LABEL_TAKEN_TEXT.format(label=label))

    async def _push(self) -> None:
        """Send the live set to the keeper. A keeper that is away is not an error here: ``GrantSync`` retries."""
        try:
            await self._files.push_grants(await self._store.all_live())
        except (DeskUnavailable, MacFsError) as exc:
            log.warning("the keeper did not take the grants: %s", type(exc).__name__)


class GrantSync:
    """Pushes every user's live grants on ``start`` and then every ``interval_s`` seconds."""

    def __init__(self, store: GrantStore, files: MacFiles, interval_s: float = MAC_GRANT_PUSH_INTERVAL_S) -> None:
        self._store, self._files, self._interval_s = store, files, interval_s
        self._task: asyncio.Task | None = None

    async def push_once(self) -> None:
        try:
            await self._files.push_grants(await self._store.all_live())
        except (DeskUnavailable, MacFsError) as exc:
            log.warning("the keeper did not take the grants: %s", type(exc).__name__)

    async def _loop(self) -> None:
        while True:
            await self.push_once()
            await asyncio.sleep(self._interval_s)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._loop())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
