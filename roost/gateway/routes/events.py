"""Live event stream — ``WS /api/events`` (contract's "Events" section
and HTTP API table).

Same Origin allowlist every mutating HTTP route enforces
(``roost/gateway/origin.py``), checked here directly against the
WebSocket's own headers -- ``require_origin``'s ``Depends`` wiring is an
HTTP-request dependency, and a WebSocket upgrade has no response status
code to carry a plain 403 on anyway. Same "always accept, then close
with a specific private-use code" rule the keeper's CDP relay route
established (Ruling 9, ``roost/keeper/app.py``): a client always gets a
real WebSocket close frame, never a bare rejection.

On connect: a ``snapshot`` frame (this user's own bots only -- Review
Focus #1) is sent before anything else, including before a single live
frame is ever forwarded. From then on, two things happen: every live
frame the event hub broadcasts for this user is forwarded as it arrives,
and a client's ``resume`` frame triggers a replay of every STORED event
after its cursor (``EventHub.since``, paged to exhaustion) -- the
contract's reconnect story.

Fix round 1 (two findings on the same lines): frame ORDER was a race --
(a) the live pump used to start before the snapshot was even built, so a
frame published during that build could reach the client first; (b) a
``resume`` replay ran concurrently with the live pump, so a slower,
paginated replay of OLD events could be overtaken by a NEWER live frame,
and an event already covered by the snapshot or a replay could be
resent. ``_FrameSender`` below is the one object that now owns every
``websocket.send_json`` call for a connection: the pump is created only
after the snapshot is sent (never before), and a lock serializes a
resume's replay against the live pump so their sends can never
interleave out of order, while ``_last_sent_seq`` drops any live frame a
snapshot or a replay already delivered instead of resending it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from roost.bots.service import bot_out
from roost.db.connection import ensure_initialized
from roost.events.hub import LIVE_ONLY_TYPES, EventHub, Subscription
from roost.gateway.activity import bot_activity
from roost.gateway.auth import SESSION_COOKIE_NAME, get_session_user

logger = logging.getLogger(__name__)

events_router = APIRouter(tags=["events"])

_ORIGIN_REFUSED_CLOSE_CODE = 4403
_UNAUTHENTICATED_CLOSE_CODE = 4401

# Fix round 1: how many stored events ``EventHub.since`` is asked for per
# page while replaying a ``resume`` -- a page this size or smaller means
# there's nothing further after it (see ``_FrameSender.replay``).
_REPLAY_PAGE_SIZE = 500


class _FrameSender:
    """Owns every ``websocket.send_json`` call for one connection.

    Both a live subscription frame and a ``resume``'s replayed frames
    funnel through this one object so they can never interleave out of
    ``seq`` order: ``_lock`` is held for the full duration of a replay
    (every page of it), so ``send_live`` calls arriving while a replay is
    in flight simply wait their turn rather than racing ahead of it.
    ``_last_sent_seq`` tracks the highest ``seq`` sent so far (seeded from
    the snapshot's own cursor) so a live frame already covered by the
    snapshot or a replay is dropped instead of being delivered twice.
    """

    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self._last_sent_seq = 0
        self._lock = asyncio.Lock()

    async def send_snapshot(self, events: EventHub, state: Any, user_id: str) -> None:
        bots = await state.bots.list(user_id)
        cursor = await events.latest_seq(user_id)
        async with self._lock:
            await self._websocket.send_json({
                "type": "snapshot",
                "cursor": cursor,
                "bots": [bot_out(bot, await bot_activity(state, user_id, bot)) for bot in bots],
                # The computer card: each working bot's current run's steps (live only, so a resume can't).
                "computer_steps": _computer_steps(state, user_id),
                # Each bot's newest finished run per chat (live only too), so a restarted app keeps its card.
                "computer_kept": _computer_kept(state, user_id),
                # The activity pill: each working bot's current run's steps in plain words.
                "run_steps": _run_steps(state, user_id),
            })
            self._last_sent_seq = cursor

    async def send_live(self, frame: dict[str, Any]) -> None:
        async with self._lock:
            if frame.get("type") in LIVE_ONLY_TYPES:
                # Never stored (EventHub.publish's LIVE_ONLY_TYPES), so
                # never something a snapshot or a resume's replay could
                # have already delivered -- and its `seq` piggybacks on
                # the latest STORED event's seq WITHOUT advancing it, so
                # comparing it against `_last_sent_seq` below would drop
                # every text_delta the instant any stored event at that
                # same seq had already been sent (a real regression this
                # fixed: every live reply streamed with zero deltas).
                await self._websocket.send_json(frame)
                return
            seq = frame.get("seq")
            if isinstance(seq, int) and seq <= self._last_sent_seq:
                return  # already covered by the snapshot or a resume's replay
            await self._websocket.send_json(frame)
            if isinstance(seq, int):
                self._last_sent_seq = seq

    async def replay(self, events: EventHub, user_id: str, cursor: int) -> None:
        """Send every stored event after ``cursor``, paging through
        ``EventHub.since`` to exhaustion (Fix round 1: a single capped
        page used to silently stop after the first 500 rows)."""
        async with self._lock:
            while True:
                batch = await events.since(user_id, cursor, limit=_REPLAY_PAGE_SIZE)
                if not batch:
                    return
                for frame in batch:
                    await self._websocket.send_json(frame)
                    self._last_sent_seq = max(self._last_sent_seq, frame["seq"])
                cursor = batch[-1]["seq"]
                if len(batch) < _REPLAY_PAGE_SIZE:
                    return


def _computer_steps(state: Any, user_id: str) -> dict[str, list[dict[str, Any]]]:
    steps = getattr(state, "computer_steps", None)
    return steps.for_user(user_id) if steps is not None else {}


def _computer_kept(state: Any, user_id: str) -> dict[str, list[list[dict[str, Any]]]]:
    steps = getattr(state, "computer_steps", None)
    return steps.kept_for_user(user_id) if steps is not None else {}


def _run_steps(state: Any, user_id: str) -> dict[str, list[dict[str, Any]]]:
    steps = getattr(state, "run_steps", None)
    return steps.for_user(user_id) if steps is not None else {}


async def _pump_live_frames(subscription: Subscription, sender: _FrameSender) -> None:
    async for frame in subscription:
        await sender.send_live(frame)


@events_router.websocket("/api/events")
async def events_ws(websocket: WebSocket) -> None:
    # Ruling 9: always accept first, then close with a specific code --
    # a client always gets a real close frame, never a bare rejection.
    await websocket.accept()

    config = websocket.app.state.config
    origin = websocket.headers.get("origin")
    if origin not in config.allowed_origins:
        await websocket.close(code=_ORIGIN_REFUSED_CLOSE_CODE)
        return

    await ensure_initialized(config)
    session_id = websocket.cookies.get(SESSION_COOKIE_NAME)
    user = await get_session_user(config, session_id) if session_id else None
    if user is None:
        await websocket.close(code=_UNAUTHENTICATED_CLOSE_CODE)
        return

    events: EventHub = websocket.app.state.events
    # Subscribe FIRST, before building the snapshot: anything published
    # in the meantime queues here rather than being missed outright, and
    # the sender's seeded `_last_sent_seq` (from the snapshot's own
    # cursor, set once it's sent below) drops it as an already-covered
    # duplicate instead of letting it jump ahead of the snapshot.
    subscription = events.subscribe(user.id)
    sender = _FrameSender(websocket)
    pump_task: "asyncio.Task[None] | None" = None
    try:
        await sender.send_snapshot(events, websocket.app.state, user.id)
        # Only start forwarding live frames once the snapshot itself has
        # actually been sent (Fix round 1) -- never before.
        pump_task = asyncio.create_task(_pump_live_frames(subscription, sender))
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "resume":
                await sender.replay(events, user.id, int(data.get("cursor", 0)))
    except WebSocketDisconnect:
        pass
    finally:
        if pump_task is not None:
            pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pump_task
        subscription.close()
