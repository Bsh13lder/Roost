"""Low-level CDP JSON-RPC client over the keeper's authenticated WebSocket
relay (``roost.keeper.app``'s ``/desks/{bot_id}/cdp`` route,
``roost.keeper.pipe_relay``).

``CdpClient`` speaks the raw Chrome DevTools Protocol wire format — JSON
text frames with an incrementing ``id`` for request/reply pairs, or no
``id`` at all for unsolicited events — and nothing else. It never
interprets a CDP method name or its payload; that is
``roost/desk/browser.py``'s job. One background reader task drains the
socket and routes every incoming frame either to the ``send()`` call
waiting on that reply's ``id``, or to any ``wait_event()`` call waiting
on that event's ``method``/``sessionId`` (and accepted by that wait's
``predicate``, when it has one).
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import logging
from collections.abc import Callable
from typing import Any

import websockets

from roost.constants import CDP_MAX_MESSAGE_BYTES, CDP_SEND_TIMEOUT_S

_DESK_TOKEN_HEADER = "X-Roost-Desk-Token"

logger = logging.getLogger(__name__)

# A ``wait_event`` filter: True when this event is the one being waited for.
EventPredicate = Callable[[dict[str, Any]], bool]


def _accepts(predicate: EventPredicate | None, message: dict[str, Any]) -> bool:
    """Whether ``predicate`` takes ``message`` (no predicate takes every event).
    A predicate that raises skips the event and is logged: an error here would
    otherwise end the reader task and fail every pending ``send`` on a socket
    that is still fine."""
    if predicate is None:
        return True
    try:
        return bool(predicate(message))
    except Exception:
        logger.warning("a CDP event filter failed on %s; the event is skipped", message.get("method"), exc_info=True)
        return False


class CdpClientError(RuntimeError):
    """Raised when the relay connection is unusable — never connected,
    or closed while a ``send()`` was waiting on a reply."""


class CdpReplyError(CdpClientError):
    """The socket is still alive; only this one command failed — a
    CDP-level error reply (e.g. "Session with given id not found" for a
    tab that went away, or a method the far end refuses) or no reply
    within ``CDP_SEND_TIMEOUT_S`` (a hung renderer).

    Distinguished from the base ``CdpClientError`` — a genuinely dead
    connection (``not connected``/``connection closed``) — so a caller
    like ``KeeperDesk.screenshot`` can tell "this one capture failed"
    from "the socket is gone" and never tear down a page the bot is
    still actively browsing with just because a view failed once (S1.8
    Fix round 1, finding 1)."""


class CdpTimeoutError(CdpReplyError):
    """No reply within ``CDP_SEND_TIMEOUT_S``: the browser may be hung, so a caller with several
    best-effort steps left (the guards' disarm) stops instead of waiting that long for each."""


# The error replies that mean the tab behind a session is gone (closed by hand, crashed) while the socket is fine:
# ``KeeperDesk`` re-attaches the tab in front on the same connection instead of failing or reconnecting.
_SESSION_GONE_MARKERS = ("Session with given id not found", "Target closed", "No target with given id")


def session_gone(exc: BaseException) -> bool:
    """A ``CdpReplyError`` that says the bot's tab session no longer exists (never a dead socket)."""
    return isinstance(exc, CdpReplyError) and any(marker in str(exc) for marker in _SESSION_GONE_MARKERS)


class CdpClient:
    """One CDP connection to a bot's running browser, over the keeper's
    relay at ``relay_url`` (``ws://127.0.0.1:<keeper_port>/desks/{bot_id}/cdp``),
    authenticated with the per-bot ``token`` minted on browser start.

    ``connect()``/``close()`` own the socket and the reader task;
    everything else (``send``, ``wait_event``) only works while connected.
    """

    def __init__(self, relay_url: str, token: str) -> None:
        self._relay_url = relay_url
        self._token = token
        self._ws: websockets.ClientConnection | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._next_id = itertools.count(1)
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        # Each waiter is (method, session_id, predicate, future);
        # session_id=None matches an event on any session (or none), and
        # predicate=None takes every event that gets that far.
        self._event_waiters: list[
            tuple[str, str | None, EventPredicate | None, asyncio.Future[dict[str, Any]]]
        ] = []
        # Standing listeners (C3's browser guards): every event whose method is in the set is queued, in socket
        # order, until ``unlisten``. Unlike ``wait_event`` nothing between two reads is lost.
        self._listeners: tuple[tuple[frozenset[str], asyncio.Queue[dict[str, Any]]], ...] = ()

    @property
    def is_open(self) -> bool:
        """Connected, and the reader still running (a relay that closed the socket, a 4409 takeover, ends it)."""
        return self._ws is not None and self._reader_task is not None and not self._reader_task.done()

    def listen(self, methods: frozenset[str]) -> asyncio.Queue[dict[str, Any]]:
        """A queue that receives every later event named in ``methods`` (on any session)."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._listeners = (*self._listeners, (frozenset(methods), queue))
        return queue

    def unlisten(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._listeners = tuple(pair for pair in self._listeners if pair[1] is not queue)

    async def connect(self) -> None:
        # Fix round 1, finding 4: `websockets.connect`'s own default
        # `max_size` (1 MiB) is smaller than a real page's accessibility
        # tree routinely is; a reply over that limit would otherwise
        # close the socket with code 1009 (see CDP_MAX_MESSAGE_BYTES's
        # docstring in roost/constants.py).
        self._ws = await websockets.connect(
            self._relay_url,
            additional_headers={_DESK_TOKEN_HEADER: self._token},
            max_size=CDP_MAX_MESSAGE_BYTES,
        )
        self._reader_task = asyncio.create_task(self._read_loop())

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
            self._reader_task = None
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None
        self._fail_all_pending(CdpClientError("connection closed"))

    async def send(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None) -> dict:
        """Send one CDP command and return its matching reply (by ``id``).

        Raises ``CdpReplyError`` if the reply itself is a CDP-level
        error (``{"id": ..., "error": {...}}``) rather than a result --
        every caller (``DeskBrowserPage``) unwraps ``reply["result"]``
        without checking first, so an error reply must never reach them
        as an ordinary-looking dict (Fix round 1, finding 6: it used to,
        turning into a bare ``KeyError`` instead of a clean failure).

        Also raises ``CdpReplyError`` if no reply arrives within
        ``CDP_SEND_TIMEOUT_S`` (Final review, finding 4) -- a hostile
        page can hang its own renderer, so a call like
        ``Accessibility.getFullAXTree`` (which ``read_page`` always
        sends) never gets a reply at all. Without a bound here, the
        turn -- and every later message queued behind it for this bot
        -- never ends.

        Both are ``CdpReplyError`` rather than the base ``CdpClientError``
        -- the socket is still fine, only this one command wasn't
        answered usefully (S1.8 Fix round 1, finding 1).
        """
        if self._ws is None:
            raise CdpClientError("not connected")

        msg_id = next(self._next_id)
        payload: dict[str, Any] = {"id": msg_id, "method": method, "params": params or {}}
        if session_id is not None:
            payload["sessionId"] = session_id

        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = future
        try:
            try:
                await self._ws.send(json.dumps(payload))
            except websockets.ConnectionClosed as exc:   # the relay went away: the browser isn't answering
                raise CdpClientError(f"the connection closed before {method!r} was sent") from exc
            try:
                reply = await asyncio.wait_for(future, timeout=CDP_SEND_TIMEOUT_S)
            except asyncio.TimeoutError as exc:
                raise CdpTimeoutError(
                    f"timed out after {CDP_SEND_TIMEOUT_S}s waiting for a reply to {method!r}"
                ) from exc
        finally:
            self._pending.pop(msg_id, None)

        if "error" in reply:
            raise CdpReplyError(f"CDP error replying to {method!r}: {reply['error']}")
        return reply

    async def wait_event(
        self,
        method: str,
        session_id: str | None = None,
        timeout: float = 20.0,
        predicate: Callable[[dict[str, Any]], bool] | None = None,
    ) -> dict | None:
        """Wait up to ``timeout`` seconds for the next unsolicited event
        named ``method`` (optionally scoped to ``session_id``). Returns
        ``None`` on timeout rather than raising — callers that can
        tolerate a slow/never-firing event (``DeskBrowserPage.open_page``)
        decide what "give up and continue anyway" means, not this client.
        A connection that closes while waiting raises ``CdpClientError`` at once
        (the event can never come; the caller's reconnect takes over).

        ``predicate``, when given, picks one event out of many with the
        same name (the stuck flow: the main frame's ``Document`` response
        among every iframe's and sub-resource's
        ``Network.responseReceived``). An event it rejects is skipped and
        the wait goes on.
        """
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        waiter = (method, session_id, predicate, future)
        self._event_waiters.append(waiter)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            with contextlib.suppress(ValueError):
                self._event_waiters.remove(waiter)

    async def _read_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                self._route(json.loads(raw))
        except websockets.ConnectionClosed:
            pass
        finally:
            self._fail_all_pending(CdpClientError("connection closed"))

    def _route(self, message: dict[str, Any]) -> None:
        msg_id = message.get("id")
        if msg_id is not None:
            future = self._pending.get(msg_id)
            if future is not None and not future.done():
                future.set_result(message)
            return

        method = message.get("method")
        session_id = message.get("sessionId")
        for methods, queue in self._listeners:
            if method in methods:
                queue.put_nowait(message)
        for waiter_method, waiter_session, predicate, future in list(self._event_waiters):
            if future.done():
                continue
            if waiter_method != method or (waiter_session is not None and waiter_session != session_id):
                continue
            if _accepts(predicate, message):
                future.set_result(message)

    def _fail_all_pending(self, exc: Exception) -> None:
        """Every reply and every event still awaited fails at once: neither can come on a closed socket."""
        pending, self._pending = self._pending, {}
        waiting = [waiter[3] for waiter in self._event_waiters]
        for future in (*pending.values(), *waiting):
            if not future.done():
                future.set_exception(exc)
