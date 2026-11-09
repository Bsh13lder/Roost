"""``EventHub`` — the per-user live event stream's single choke point
(contract's "Events" section).

Every frame ``roost/talk/turn.py`` publishes passes through here once:
persisted (encrypted, the ``events`` table) unless it's ``text_delta``
(contract: "text_delta events are not stored (live only)"), then
broadcast to every live ``Subscription`` for that same user. Isolation
between users (Review Focus #1) falls out of this for free — a
subscription is keyed by ``user_id`` and a frame is only ever broadcast
to the subscriptions under the ``user_id`` it was published for.

``roost/gateway/routes/events.py`` is the only caller of ``since``/
``subscribe``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable

from roost.config import Config
from roost.crypto.encryption import decrypt, encrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session

logger = logging.getLogger(__name__)

_PAYLOAD_AAD = "events:payload"

# Contract: "text_delta events are not stored (live only); all others
# are stored."
# The computer card's steps, the activity pill's steps and a call's speech_ready are live only too.
LIVE_ONLY_TYPES = frozenset({"text_delta", "computer_step", "run_step", "speech_ready"})

_EventQueue = "asyncio.Queue[dict[str, Any] | None]"
Listener = Callable[[str, dict[str, Any]], None]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Subscription:
    """An async iterator of one user's live frames, backed by an
    unbounded ``asyncio.Queue`` the hub pushes onto. Never drops a
    frame — Night-1 has no backpressure story yet, and a slow/stalled
    client is a later problem, not this one.
    """

    def __init__(self, hub: "EventHub", user_id: str, queue: Any) -> None:
        self._hub = hub
        self._user_id = user_id
        self._queue = queue
        self._closed = False

    def __aiter__(self) -> "Subscription":
        return self

    async def __anext__(self) -> dict[str, Any]:
        if self._closed:
            raise StopAsyncIteration
        item = await self._queue.get()
        if item is None:  # the sentinel close() pushes
            raise StopAsyncIteration
        return item

    def close(self) -> None:
        """Detach from the hub and unblock a pending ``__anext__`` —
        idempotent, so a route's cleanup ``finally`` can always call it
        without checking whether it already did."""
        if self._closed:
            return
        self._closed = True
        self._hub._unsubscribe(self._user_id, self._queue)
        self._queue.put_nowait(None)


class EventHub:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._subscribers: dict[str, list[Any]] = defaultdict(list)
        # Cache of each user's highest STORED seq -- avoids a MAX(seq)
        # query on every publish/latest_seq call once warm.
        self._last_seq: dict[str, int] = {}
        self._listeners: tuple[Listener, ...] = ()

    async def publish(self, user_id: str, event: dict[str, Any]) -> int:
        """Persist ``event`` (unless it's live-only) and broadcast it,
        with its ``seq`` attached, to every live subscriber for
        ``user_id``. Returns that ``seq``."""
        if event.get("type") in LIVE_ONLY_TYPES:
            seq = await self.latest_seq(user_id)
        else:
            seq = await self._store(user_id, event)

        frame = {**event, "seq": seq}
        for queue in list(self._subscribers.get(user_id, ())):
            queue.put_nowait(frame)
        self._tell_listeners(user_id, frame)
        return seq

    def add_listener(self, listener: "Listener") -> None:
        """A server-side reader of every published frame (the vault export's debounce). It must be quick and
        must not publish; one that raises is logged and skipped."""
        self._listeners = (*self._listeners, listener)

    def _tell_listeners(self, user_id: str, frame: dict[str, Any]) -> None:
        for listener in self._listeners:
            try:
                listener(user_id, frame)
            except Exception as exc:
                logger.warning("an event listener failed: %s", type(exc).__name__)

    async def _store(self, user_id: str, event: dict[str, Any]) -> int:
        dek = await get_user_dek(self._config, user_id)
        payload = encrypt(json.dumps(event), dek, user_aad(user_id, _PAYLOAD_AAD))
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "INSERT INTO events (user_id, kind, payload, created_at) VALUES (?,?,?,?)",
                (user_id, str(event.get("type")), payload, _now_iso()),
            )
            await db.commit()
        seq = cursor.lastrowid
        self._last_seq[user_id] = seq
        return seq

    async def since(self, user_id: str, cursor: int, limit: int = 500) -> list[dict[str, Any]]:
        """Every stored event for ``user_id`` with ``seq > cursor``,
        decrypted and in order — what a reconnecting client replays via
        a ``resume`` frame. Never includes a ``text_delta`` (it was
        never stored)."""
        async with db_session(self._config) as db:
            cursor_result = await db.execute(
                "SELECT seq, payload FROM events WHERE user_id = ? AND seq > ? ORDER BY seq LIMIT ?",
                (user_id, cursor, limit),
            )
            rows = await cursor_result.fetchall()
        if not rows:
            return []

        dek = await get_user_dek(self._config, user_id)
        events: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(decrypt(row["payload"], dek, user_aad(user_id, _PAYLOAD_AAD)))
            events.append({**payload, "seq": row["seq"]})
        return events

    async def latest_seq(self, user_id: str) -> int:
        """The highest stored ``seq`` for ``user_id`` (0 if none yet) —
        the cursor a fresh ``snapshot`` frame reports, and the ``seq`` a
        live-only ``text_delta`` frame piggybacks on without advancing
        the real, replayable sequence."""
        cached = self._last_seq.get(user_id)
        if cached is not None:
            return cached

        async with db_session(self._config) as db:
            row = await (
                await db.execute("SELECT COALESCE(MAX(seq), 0) FROM events WHERE user_id = ?", (user_id,))
            ).fetchone()
        seq = row[0] if row else 0
        self._last_seq[user_id] = seq
        return seq

    def subscribe(self, user_id: str) -> Subscription:
        queue: Any = asyncio.Queue()
        self._subscribers[user_id].append(queue)
        return Subscription(self, user_id, queue)

    def _unsubscribe(self, user_id: str, queue: Any) -> None:
        subs = self._subscribers.get(user_id)
        if subs and queue in subs:
            subs.remove(queue)
