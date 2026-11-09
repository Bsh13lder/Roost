"""``WS /api/bots/{bot_id}/live?mode=view|control``: watch a bot's computer (Computers 2.0, C1, Task 9).

Accept order (``live_refusal``): Origin 4403, this Mac 4403, session 4401, the user's bot 4404, mode, then here:
a Mac Brave bot 4503 (it has no screen), too many tabs 4429, and the desk's screen (asleep 4410, unreachable
4503). Then ``relay_screen`` carries RFB bytes both ways until either side ends.

Review focus (security review a): the browser's bytes pass through ``RfbClientFilter`` and ``verdict`` on every
message with ``input_allowed()`` read each time. In this task it is always ``False``: view only. Nothing the
user sends or sees is logged; an error is logged by bot id and exception type name alone.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter, WebSocket

from roost.constants import (
    LIVE_SHORT_SESSION_S,
    LIVE_CLOSE_ASLEEP,
    LIVE_CLOSE_GIVEN_BACK,
    LIVE_CLOSE_PROTOCOL,
    LIVE_CLOSE_TOO_MANY,
    LIVE_CLOSE_UNAVAILABLE,
)
from roost.desk import DeskAsleep, DeskUnavailable, ScreenStream
from roost.desk.rfb import InputRateLimit, RfbClientFilter, RfbMessage, RfbProtocolError, verdict
from roost.gateway.live_socket import (
    ASLEEP_REASON,
    GIVEN_BACK_REASON,
    PROTOCOL_REASON,
    TOO_MANY_REASON,
    UNAVAILABLE_REASON,
    LiveMode,
    LiveViewers,
    Refusal,
    live_refusal,
)
from roost.teach.observer import TeachObserver

logger = logging.getLogger(__name__)

live_router = APIRouter(tags=["live"])

RelayEnd = Literal["client", "screen", "protocol", "given_back"]
InputHook = Callable[[RfbMessage], Awaitable[None]]


async def _close(websocket: WebSocket, code: int, reason: str = "") -> None:
    with contextlib.suppress(Exception):
        await websocket.close(code=code, reason=reason)


async def _client_to_screen(
    websocket: WebSocket, screen: ScreenStream, input_allowed: Callable[[], bool], on_input: InputHook | None = None,
) -> RelayEnd:
    """The browser's bytes toward the computer, one checked message at a time. ``on_input`` (Teach) sees each
    input message just before it is forwarded; the lock is read again after it, since it can wait on the page."""
    filt, limit = RfbClientFilter(), InputRateLimit()
    while True:
        event = await websocket.receive()
        if event["type"] == "websocket.disconnect":
            # Owner, 2026-11-01: 1000/1001 is the app closing it, 1006 a link that broke on the way.
            logger.warning("viewer closed the live screen with code %s", event.get("code", "-"))
            return "client"
        data = event.get("bytes")
        if data is None:
            return "protocol"                      # a text frame is not RFB
        try:
            messages = filt.feed(data)
        except RfbProtocolError:
            return "protocol"
        for message in messages:
            if verdict(message, message.is_input and input_allowed()) != "forward":
                continue
            if message.is_input and not limit.allow():
                continue
            if message.is_input and on_input is not None:
                await on_input(message)
                if not input_allowed():            # given back while the page was read: never sent after
                    continue
            await screen.send(message.data)


async def _screen_to_client(websocket: WebSocket, screen: ScreenStream) -> RelayEnd:
    """The computer's bytes toward the browser, unchanged."""
    while chunk := await screen.receive():
        await websocket.send_bytes(chunk)
    return "screen"


async def relay_screen(
    websocket: WebSocket, screen: ScreenStream, *, input_allowed: Callable[[], bool],
    watchers: tuple[Awaitable[RelayEnd], ...] = (), on_input: InputHook | None = None,
) -> RelayEnd:
    """Carry bytes both ways until one side ends (or a watcher does). Returns which ended it."""
    tasks = [asyncio.ensure_future(_client_to_screen(websocket, screen, input_allowed, on_input)),
             asyncio.ensure_future(_screen_to_client(websocket, screen)),
             *(asyncio.ensure_future(watcher) for watcher in watchers)]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        return next(iter(done)).result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.wait(tasks)
        for task in tasks:
            if not task.cancelled():
                task.exception()          # marks a late failure as seen; it was already decided


@live_router.websocket("/api/bots/{bot_id}/live")
async def live_ws(websocket: WebSocket, bot_id: str, mode: str = "view") -> None:
    # Ruling 9: always accept first, then close with a specific code.
    await websocket.accept()
    found = await live_refusal(websocket, bot_id, mode)
    if isinstance(found, Refusal):
        await _close(websocket, found.code, found.reason)
        return
    bot, live_mode = found
    viewers: LiveViewers = websocket.app.state.live_viewers
    if bot.computer != "linux":
        await _close(websocket, LIVE_CLOSE_UNAVAILABLE, UNAVAILABLE_REASON)
        return
    if live_mode == "control":
        kicked = viewers.claim_control(bot.id)
        try:
            await _serve(websocket, bot.id, bot.computer, live_mode, kicked)
        finally:
            viewers.release_control(bot.id, kicked)
        return
    if not viewers.enter(bot.id, live_mode):
        await _close(websocket, LIVE_CLOSE_TOO_MANY, TOO_MANY_REASON)
        return
    try:
        await _serve(websocket, bot.id, bot.computer, live_mode, None)
    finally:
        viewers.leave(bot.id, live_mode)


async def _given_back(control, bot_id: str, replaced: asyncio.Event | None) -> RelayEnd:
    """Ends when the person gives the computer back, or a newer control socket replaces this one."""
    waits = [asyncio.ensure_future(control.wait_released(bot_id))]
    if replaced is not None:
        waits.append(asyncio.ensure_future(replaced.wait()))
    try:
        await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for wait in waits:
            wait.cancel()
    return "given_back"


async def _serve(websocket: WebSocket, bot_id: str, computer, mode: LiveMode,
                 replaced: asyncio.Event | None) -> None:
    desk = websocket.app.state.desks.for_bot(bot_id, computer)
    try:
        screen = await desk.open_screen()
    except DeskAsleep:
        await _close(websocket, LIVE_CLOSE_ASLEEP, ASLEEP_REASON)
        return
    except DeskUnavailable:
        await _close(websocket, LIVE_CLOSE_UNAVAILABLE, UNAVAILABLE_REASON)
        return
    ended: RelayEnd = "client"
    began = time.monotonic()
    try:
        ended = await _relay(websocket, bot_id, screen, mode, replaced, desk.page())
    except Exception as exc:       # never the message: it could carry what was typed or shown
        logger.warning("live screen failed for bot %s: %s", bot_id, type(exc).__name__)
        ended = "screen"
    finally:
        # Owner, 2026-10-29: a dropped screen said nothing. Who ended it and when, never what passed.
        lived = time.monotonic() - began
        logger.log(logging.WARNING if lived < LIVE_SHORT_SESSION_S else logging.INFO,
                   "live screen for bot %s (%s) ended by %s, code %s, after %.0f s",
                   bot_id, mode, ended, _END_CODES.get(ended, "-"), lived)
        with contextlib.suppress(Exception):
            await screen.close()
    code = _END_CODES.get(ended)
    if code is not None:
        await _close(websocket, code, _END_REASONS[ended])


_END_CODES: dict[str, int] = {
    "given_back": LIVE_CLOSE_GIVEN_BACK, "protocol": LIVE_CLOSE_PROTOCOL, "screen": LIVE_CLOSE_UNAVAILABLE}
_END_REASONS: dict[str, str] = {
    "given_back": GIVEN_BACK_REASON, "protocol": PROTOCOL_REASON, "screen": UNAVAILABLE_REASON}


async def _relay(websocket: WebSocket, bot_id: str, screen: ScreenStream, mode: LiveMode,
                 replaced: asyncio.Event | None, page=None) -> RelayEnd:
    """View: no input ever. Control: input only while the lock is held, read on every message; while you teach
    the bot, a ``TeachObserver`` reads the page under each press (never what is typed)."""
    if mode == "view":
        return await relay_screen(websocket, screen, input_allowed=lambda: False)
    control = websocket.app.state.control
    return await relay_screen(
        websocket, screen, input_allowed=lambda: control.held(bot_id) is not None,
        watchers=(_given_back(control, bot_id, replaced),),
        on_input=TeachObserver(websocket.app.state.teach, bot_id, page),
    )
