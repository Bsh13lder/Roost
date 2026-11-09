"""``VaultService``: remember which account a bot is signed in with, and tell the bot (Computers 2.0, C2).

Only the person says which account; a label is the one piece of text you typed that the bot reads. It is
sealed in the store. Nothing here sees a password, a key or a frame."""

from __future__ import annotations

from roost.events.hub import EventHub
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore, message_out
from roost.vault.models import NoSite, SiteLogin, clean_label, normalise_host, signed_in_line
from roost.vault.store import VaultStore
from roost.work.models import ORIGIN_YOU, WorkDraft, WorkKind


class VaultService:
    def __init__(self, store: VaultStore, talk: TalkStore, events: EventHub, turns: TurnRunner) -> None:
        self._store = store
        self._talk = talk
        self._events = events
        self._turns = turns

    async def sign_in(self, user_id: str, bot_id: str, url_or_host: str, label: str | None, *, kept: bool = True,
                      clear_after_item_id: str | None = None) -> SiteLogin:
        """Save the account (``label=None`` keeps a saved one) and whether it stays on the computer. ``NoSite``:
        there is no site in ``url_or_host``. ``VaultBotNotFound``: not your bot."""
        host = normalise_host(url_or_host)
        if not host:
            raise NoSite(bot_id)
        return await self._store.remember(user_id, bot_id, host, None if label is None else clean_label(label),
                                          kept=kept, clear_after_item_id=clear_after_item_id)

    async def tell_bot(self, user_id: str, login: SiteLogin) -> None:
        """Say it in the bot's chat as your own line, so it carries on with the right account in mind."""
        thread, _ = await self._talk.ensure_main_thread(user_id, login.bot_id)
        body = signed_in_line(login.host, login.label)
        message = await self._talk.add_message(user_id, thread.id, role="user", body=body)
        await self._events.publish(user_id, {"type": "message", "thread_id": thread.id,
                                             "message": message_out(message)})
        await self._turns.submit(user_id, WorkDraft(
            bot_id=login.bot_id, thread_id=thread.id, kind=WorkKind.MESSAGE, origin=ORIGIN_YOU,
            body=body, message_id=message.id,
        ))
