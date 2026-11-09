"""The Add a key card: a bot asks for a key it doesn't have (``request_connector``), and only the user's Save makes
the connector (design §4, owner addition 2026-10-22).

The request stores the service, the base URL, the bot's reason and how the key is sent, sealed under
``connector_requests:<column>``; never a key. Save is a compare-and-set on ``open`` (of two presses one wins) and
creates the connector through ``ConnectorService.add`` with the user's key, the same checks as
``POST /api/connectors``; a refusal opens the card again. The bot hears ``KEY_ADDED`` or ``NOT_NOW`` as a
``card_answer`` line and work item, never the key."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.connectors import texts
from roost.connectors.address import check_base_url
from roost.connectors.models import ConnectorDraft
from roost.connectors.service import ConnectorRefused, ConnectorService
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.events.hub import EventHub
from roost.talk.store import TalkStore, message_out
from roost.work.models import ORIGIN_CARD, WorkDraft, WorkKind

KEY_ADDED = "Key added for {name}."
NOT_NOW = "The user said not now: no key for {service}."
MESSAGE_KIND = "connector_request"
REQUESTS_CHANGED = "connector_requests_changed"
_SEALED = ("service", "base_url", "why", "auth_name")
_COLUMNS = ("id, user_id, bot_id, thread_id, service, base_url, why, auth_style, auth_name, tainted, state, "
            "connector_id, message_id, created_at, decided_at")


class NoSuchRequest(LookupError):
    """Not this user's request (or none)."""


class RequestClosed(RuntimeError):
    """Another press answered it first (409)."""


class Submitter(Protocol):
    async def submit(self, user_id: str, draft: WorkDraft, *, item_id: str | None = None) -> Any: ...


@dataclass(frozen=True)
class KeyRequest:
    id: str
    user_id: str
    bot_id: str
    thread_id: str
    service: str
    base_url: str
    host: str
    why: str
    auth_style: str
    auth_name: str
    tainted: bool
    state: str
    connector_id: str | None
    created_at: str


@dataclass(frozen=True)
class NewRequest:
    user_id: str
    bot_id: str
    thread_id: str
    service: str
    base_url: str
    why: str
    auth_style: str
    auth_name: str
    tainted: bool


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"connector_requests:{column}")


def _to_request(row: aiosqlite.Row, dek: bytes) -> KeyRequest:
    uid = row["user_id"]
    opened = {c: decrypt_field(row[c], dek, _aad(uid, c)) or "" for c in _SEALED}
    return KeyRequest(id=row["id"], user_id=uid, bot_id=row["bot_id"], thread_id=row["thread_id"],
                      host=check_base_url(opened["base_url"]).host, auth_style=row["auth_style"],
                      tainted=bool(row["tainted"]), state=row["state"], connector_id=row["connector_id"],
                      created_at=row["created_at"], **opened)


class ConnectorRequestStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def create(self, new: NewRequest) -> KeyRequest:
        dek = await get_user_dek(self._config, new.user_id)
        sealed = {c: encrypt_field(getattr(new, c), dek, _aad(new.user_id, c)) for c in _SEALED}
        request_id = str(uuid4())
        async with db_session(self._config) as db:
            await db.execute(
                f"INSERT INTO connector_requests ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,'open',NULL,NULL,?,NULL)",
                (request_id, new.user_id, new.bot_id, new.thread_id, sealed["service"], sealed["base_url"],
                 sealed["why"], new.auth_style, sealed["auth_name"], int(new.tainted), _now()))
            await db.commit()
        made = await self.get(new.user_id, request_id)
        if made is None:
            raise RuntimeError("The key request could not be read back.")
        return made

    async def get(self, user_id: str, request_id: str) -> KeyRequest | None:
        found = await self._select(user_id, "AND id = ?", (request_id,))
        return found[0] if found else None

    async def list_open(self, user_id: str, bot_id: str | None = None) -> tuple[KeyRequest, ...]:
        if bot_id is None:
            return await self._select(user_id, "AND state = 'open' ORDER BY created_at, rowid", ())
        return await self._select(user_id, "AND state = 'open' AND bot_id = ? ORDER BY created_at, rowid", (bot_id,))

    async def set_message(self, user_id: str, request_id: str, message_id: str) -> None:
        await self._update(user_id, "SET message_id = ? WHERE id = ? AND user_id = ?", (message_id, request_id, user_id))

    async def set_connector(self, user_id: str, request_id: str, connector_id: str) -> None:
        await self._update(user_id, "SET connector_id = ? WHERE id = ? AND user_id = ?",
                           (connector_id, request_id, user_id))

    async def decide(self, user_id: str, request_id: str, state: str, *, expected: str = "open") -> KeyRequest | None:
        """Compare-and-set ``expected`` -> ``state``; ``None`` when it is not the user's or already answered."""
        decided = None if state == "open" else _now()
        count = await self._update(user_id, "SET state = ?, decided_at = ? WHERE id = ? AND user_id = ? AND state = ?",
                                   (state, decided, request_id, user_id, expected))
        return await self.get(user_id, request_id) if count == 1 else None

    async def _update(self, user_id: str, clause: str, params: tuple) -> int:
        async with db_session(self._config) as db:
            cursor = await db.execute(f"UPDATE connector_requests {clause}", params)
            await db.commit()
        return cursor.rowcount

    async def _select(self, user_id: str, extra: str, params: tuple) -> tuple[KeyRequest, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {_COLUMNS} FROM connector_requests WHERE user_id = ? {extra}", (user_id, *params))).fetchall()
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_to_request(row, dek) for row in rows)


class ConnectorRequestService:
    def __init__(self, store: ConnectorRequestStore, connectors: ConnectorService, talk: TalkStore,
                 events: EventHub) -> None:
        self._store, self._connectors, self._talk, self._events = store, connectors, talk, events
        self._turns: Submitter | None = None

    @property
    def store(self) -> ConnectorRequestStore:
        return self._store

    def attach(self, turns: Submitter) -> None:
        """The runner that carries the bot on after an answer (built after this service)."""
        self._turns = turns

    async def open_request(self, new: NewRequest) -> KeyRequest:
        """Store the request and post its card in the bot's chat."""
        request = await self._store.create(new)
        body = json.dumps({"request_id": request.id, "service": request.service, "host": request.host})
        message = await self._talk.add_message(new.user_id, new.thread_id, "bot", body, tainted=new.tainted,
                                               kind=MESSAGE_KIND, author_bot_id=new.bot_id)
        await self._events.publish(new.user_id, {"type": "message", "thread_id": new.thread_id,
                                                 "message": message_out(message)})
        await self._store.set_message(new.user_id, request.id, message.id)
        await self._changed(request)
        return request

    async def get(self, user_id: str, request_id: str) -> KeyRequest:
        found = await self._store.get(user_id, request_id)
        if found is None:
            raise NoSuchRequest(request_id)
        return found

    async def save(self, user_id: str, request_id: str, secret: str) -> KeyRequest:
        """Make the connector with the user's key. ``ConnectorRefused`` (the card stays open) or ``RequestClosed``."""
        request = await self._store.decide(user_id, request_id, "saved")
        if request is None:
            await self._missing_or_closed(user_id, request_id)
        try:
            draft = ConnectorDraft(name=request.service, purpose=request.why, base_url=request.base_url,
                                   auth_style=request.auth_style, auth_name=request.auth_name, secret=secret)
            made = await self._connectors.add(user_id, draft)
        except BaseException:
            await self._store.decide(user_id, request_id, "open", expected="saved")
            raise
        await self._store.set_connector(user_id, request_id, made.id)
        await self._answer(request, KEY_ADDED.format(name=made.name))
        return await self.get(user_id, request_id)

    async def decline(self, user_id: str, request_id: str) -> KeyRequest:
        request = await self._store.decide(user_id, request_id, "declined")
        if request is None:
            await self._missing_or_closed(user_id, request_id)
        await self._answer(request, NOT_NOW.format(service=request.service))
        return request

    async def _answer(self, request: KeyRequest, line: str) -> None:
        """Your answer as your own line, and a work item that carries the bot on."""
        posted = await self._talk.add_message(request.user_id, request.thread_id, role="user", body=line,
                                              tainted=request.tainted, kind="card_answer")
        await self._events.publish(request.user_id, {"type": "message", "thread_id": request.thread_id,
                                                     "message": message_out(posted)})
        await self._changed(request)
        if self._turns is not None:
            await self._turns.submit(request.user_id, WorkDraft(
                bot_id=request.bot_id, thread_id=request.thread_id, kind=WorkKind.CARD_ANSWER, origin=ORIGIN_CARD,
                body=line, tainted=request.tainted, message_id=posted.id))

    async def _missing_or_closed(self, user_id: str, request_id: str):
        if await self._store.get(user_id, request_id) is None:
            raise NoSuchRequest(request_id)
        raise RequestClosed(texts.REQUEST_CLOSED)

    async def _changed(self, request: KeyRequest) -> None:
        await self._events.publish(request.user_id, {"type": REQUESTS_CHANGED, "bot_id": request.bot_id})


__all__ = ["ConnectorRefused", "ConnectorRequestService", "ConnectorRequestStore", "KEY_ADDED", "KeyRequest",
           "NOT_NOW", "NewRequest", "NoSuchRequest", "RequestClosed"]
