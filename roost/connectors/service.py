"""``ConnectorService``: the one place for the rules both doors share (the routes and the Add a key card).

Names are unique per user (case-folded), a user keeps at most ``CONNECTORS_PER_USER_MAX``, the bots named must be
the user's own, and a change of site needs the key again in the same save. ``ConnectorRefused`` carries a plain
sentence; ``NoSuchConnector`` is a 404."""

from __future__ import annotations

from typing import Any

from roost.bots.store import BotStore
from roost.connectors import texts
from roost.connectors.address import check_base_url
from roost.connectors.http import Credentials
from roost.connectors.models import Connector, ConnectorDraft, ConnectorPatch, check_auth_name, key_hint
from roost.connectors.store import ConnectorStore
from roost.constants import CONNECTORS_PER_USER_MAX


class ConnectorRefused(Exception):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


class NoSuchConnector(Exception):
    """Not this user's connector (or none)."""


def _auth_name(style: str, name: str | None) -> str:
    try:
        return check_auth_name(style, name)
    except ValueError as exc:
        raise ConnectorRefused(str(exc)) from None


class ConnectorService:
    def __init__(self, store: ConnectorStore, bots: BotStore) -> None:
        self._store = store
        self._bots = bots

    async def list(self, user_id: str) -> tuple[Connector, ...]:
        return await self._store.list(user_id)

    async def get(self, user_id: str, connector_id: str) -> Connector:
        found = await self._store.get(user_id, connector_id)
        if found is None:
            raise NoSuchConnector()
        return found

    async def add(self, user_id: str, draft: ConnectorDraft) -> Connector:
        if await self._store.count(user_id) >= CONNECTORS_PER_USER_MAX:
            raise ConnectorRefused(texts.FULL)
        await self._name_free(user_id, draft.name, None)
        await self._bots_ok(user_id, draft.bot_ids)
        return await self._store.create(user_id, {
            "name": draft.name, "purpose": draft.purpose, "base_url": draft.base_url,
            "auth_style": draft.auth_style, "auth_name": _auth_name(draft.auth_style, draft.auth_name),
            "secret": draft.secret, "secret_hint": key_hint(draft.secret),
            "allowed_prefixes": draft.allowed_prefixes, "bot_ids": draft.bot_ids,
        })

    async def update(self, user_id: str, connector_id: str, patch: ConnectorPatch) -> Connector:
        current = await self.get(user_id, connector_id)
        if patch.name is not None:
            await self._name_free(user_id, patch.name, connector_id)
        await self._bots_ok(user_id, patch.bot_ids)
        if (patch.base_url is not None and check_base_url(patch.base_url).host != current.host
                and patch.secret is None):
            raise ConnectorRefused(texts.NEW_HOST_NEEDS_KEY)
        changed = await self._store.update(user_id, connector_id, self._fields(current, patch))
        if changed is None:
            raise NoSuchConnector()
        return changed

    @staticmethod
    def _fields(current: Connector, patch: ConnectorPatch) -> dict[str, Any]:
        fields: dict[str, Any] = {
            key: getattr(patch, key) for key in ("name", "purpose", "base_url", "allowed_prefixes")
            if getattr(patch, key) is not None
        }
        style = patch.auth_style or current.auth_style
        if patch.auth_style is not None or patch.auth_name is not None:
            keep = current.auth_name if patch.auth_style in (None, current.auth_style) else None
            fields = {**fields, "auth_style": style, "auth_name": _auth_name(style, patch.auth_name or keep)}
        if patch.secret is not None:
            fields = {**fields, "secret": patch.secret, "secret_hint": key_hint(patch.secret)}
        if patch.all_bots:
            fields = {**fields, "bot_ids": None}
        elif patch.bot_ids is not None:
            fields = {**fields, "bot_ids": patch.bot_ids}
        return fields

    async def delete(self, user_id: str, connector_id: str) -> None:
        if not await self._store.delete(user_id, connector_id):
            raise NoSuchConnector()

    async def for_bot(self, user_id: str, bot_id: str) -> tuple[Connector, ...]:
        return tuple(c for c in await self._store.list(user_id) if c.usable_by(bot_id))

    async def find_for_bot(self, user_id: str, bot_id: str, name: str) -> Connector | None:
        wanted = name.strip().casefold()
        return next((c for c in await self.for_bot(user_id, bot_id) if c.name.casefold() == wanted), None)

    async def credentials(self, user_id: str, connector: Connector) -> Credentials | None:
        """How to send this connector's key; ``None`` when it was deleted meanwhile."""
        secret = await self._store.secret_of(user_id, connector.id)
        return None if secret is None else Credentials(connector.auth_style, connector.auth_name, secret)

    async def _name_free(self, user_id: str, name: str, own_id: str | None) -> None:
        wanted = name.casefold()
        if any(c.name.casefold() == wanted and c.id != own_id for c in await self._store.list(user_id)):
            raise ConnectorRefused(texts.NAME_TAKEN)

    async def _bots_ok(self, user_id: str, bot_ids: tuple[str, ...] | None) -> None:
        for bot_id in bot_ids or ():
            if await self._bots.get(user_id, bot_id) is None:
                raise ConnectorRefused(texts.BAD_BOTS)
