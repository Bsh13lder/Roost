"""The keeper's routes for a bot's Linux computer, as an ``APIRouter`` registered by ``create_app``.

HTTP: ``POST /desks/{id}/computer/start|attach|pause|stop`` (and ``/input``, C3, in ``computer_input.py``, and
``/apps``, Install an app, in ``computer_apps.py``), each signed (401), with a UUID4 bot id (400) and a
strict body (422). ``start`` is the only one that wakes a computer, through the room (the cap, the memory check).

WebSockets: ``/desks/{id}/computer/cdp`` (text frames, NUL-framed on the pipe, one client per bot, the newest takes
over with 4409) and ``/desks/{id}/computer/vnc`` (binary, up to ``LIVE_VIEWERS_MAX + 1`` at once, 4429 past
that). They accept first and then close with a code (keeper Ruling 9): 4400 bad id, 4404 not running, 4401 wrong
token. Each socket gets its own ``docker exec -i ... roost-pipe`` for that bot's container only. The audit gets
``connected`` / ``closed``, never bytes or content, and nothing relayed is logged.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import (
    LIVE_CLOSE_NOT_FOUND,
    LIVE_CLOSE_PROTOCOL,
    LIVE_CLOSE_TOO_MANY,
    LIVE_CLOSE_UNAUTHENTICATED,
    LIVE_CLOSE_UNAVAILABLE,
    LIVE_VIEWERS_MAX,
)
from roost.keeper.computer_apps import apps_routes
from roost.keeper.computer_input import input_routes
from roost.keeper.computer_room import NoRoom
from roost.keeper.computers import (
    ComputerControlError,
    ComputerHandle,
    ComputerStartError,
    build_pipe_argv,
    container_name,
)
from roost.keeper.exec_pipe import ExecPipe, NulFramer
from roost.keeper.networks import NetworkError
from roost.keeper.auth import require_signed_body
from roost.keeper.pipe_relay import RelayRegistry, tokens_match

logger = logging.getLogger(__name__)

_TOKEN_HEADER = "x-roost-desk-token"
_BUSY_MAX = 50
_UUID4 = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
_TOUCH_EVERY_S = 1.0
_NORMAL_CLOSE = 1000
_NO_ROOM = "no_room"
_START_FAILED = "failed to start the bot's computer"
_CONTROL_FAILED = "failed to change the bot's computer"

PipeOpener = Callable[[list[str]], Awaitable[ExecPipe]]


async def _open_pipe(argv: list[str]) -> ExecPipe:
    return await ExecPipe.open(argv)


class _EmptyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _StartBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    busy: list[Annotated[str, Field(pattern=_UUID4)]] = Field(default_factory=list, max_length=_BUSY_MAX)


def _check_id(bot_id: str) -> None:
    try:
        container_name(bot_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bot_id must be a UUID4") from exc


def _parse(model: type[BaseModel], body: bytes) -> BaseModel:
    try:
        return model.model_validate_json(body or b"{}")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_input=False, include_url=False)) from exc


class _Toucher:
    """``computers.touch`` at most once a second however many frames pass."""

    def __init__(self, touch: Callable[[], None]) -> None:
        self._touch = touch
        self._last = float("-inf")

    def __call__(self) -> None:
        now = time.monotonic()
        if now - self._last >= _TOUCH_EVERY_S:
            self._last = now
            self._touch()


async def _refuse(websocket: WebSocket, code: int) -> None:
    with contextlib.suppress(Exception):
        await websocket.close(code=code)


async def _gate(app: FastAPI, websocket: WebSocket, bot_id: str, audit: str) -> ComputerHandle | None:
    """Accept, then the id, the running computer and the token, each with its own close code."""
    await websocket.accept()
    try:
        container_name(bot_id)
    except ValueError:
        app.state.audit.record(audit, bot_id, "bad_bot_id")
        await _refuse(websocket, LIVE_CLOSE_PROTOCOL)
        return None
    handle = app.state.computers.handle(bot_id)
    if handle is None:
        app.state.audit.record(audit, bot_id, "not_running")
        await _refuse(websocket, LIVE_CLOSE_NOT_FOUND)
        return None
    return handle


async def _pump(inbound: Awaitable[None], outbound: Awaitable[None]) -> bool:
    """Run both directions until one ends. True when the computer's side ended first."""
    tasks = [asyncio.ensure_future(inbound), asyncio.ensure_future(outbound)]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        return tasks[1] in done and tasks[0] not in done
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def computer_routes(app: FastAPI) -> APIRouter:
    router = APIRouter()
    app.state.open_pipe = _open_pipe
    app.state.computer_relays = RelayRegistry()
    vnc_open: dict[str, int] = {}
    router.include_router(input_routes(app))
    router.include_router(apps_routes(app))

    @router.post("/desks/{bot_id}/computer/start")
    async def start_computer(bot_id: str, body: bytes = Depends(require_signed_body)):
        _check_id(bot_id)
        start_body = _parse(_StartBody, body)
        try:
            handle = await app.state.room.admit(bot_id, frozenset(start_body.busy))
        except NoRoom as exc:
            app.state.audit.record("computer_start", bot_id, "no_room")
            raise HTTPException(status_code=409, detail=_NO_ROOM) from exc
        except (ComputerStartError, NetworkError) as exc:
            app.state.audit.record("computer_start", bot_id, "error")
            raise HTTPException(status_code=500, detail=_START_FAILED) from exc
        app.state.audit.record("computer_start", bot_id, "ok")
        # fresh: this start created the container (a new image or a removed one), so its approved apps are gone.
        return {"computer": "running", "cdp_token": handle.cdp_token,
                "vnc_token": app.state.computers.mint_vnc_ticket(bot_id),
                "fresh": app.state.computers.take_fresh(bot_id)}

    @router.post("/desks/{bot_id}/computer/attach")
    async def attach_computer(bot_id: str, body: bytes = Depends(require_signed_body)):
        """The running computer's tokens. Never wakes a paused or stopped one: 409 asleep."""
        _check_id(bot_id)
        _parse(_EmptyBody, body)
        handle = app.state.computers.handle(bot_id)
        if handle is None:
            app.state.audit.record("computer_attach", bot_id, "not_running")
            raise HTTPException(status_code=409, detail="asleep")
        app.state.computers.touch(bot_id)
        app.state.audit.record("computer_attach", bot_id, "ok")
        return {"computer": "running", "cdp_token": handle.cdp_token, "vnc_token": app.state.computers.mint_vnc_ticket(bot_id)}

    async def _change(bot_id: str, body: bytes, verb: Literal["pause", "stop"]) -> dict[str, str]:
        _check_id(bot_id)
        _parse(_EmptyBody, body)
        manager = app.state.computers
        action = f"computer_{verb}"
        if manager.state(bot_id) not in (("running",) if verb == "pause" else ("running", "paused")):
            app.state.audit.record(action, bot_id, "not_running")
            return {"computer": manager.state(bot_id)}
        try:
            await getattr(manager, verb)(bot_id)
        except ComputerControlError as exc:
            app.state.audit.record(action, bot_id, "error")
            raise HTTPException(status_code=500, detail=_CONTROL_FAILED) from exc
        app.state.audit.record(action, bot_id, "ok")
        return {"computer": manager.state(bot_id)}

    @router.post("/desks/{bot_id}/computer/pause")
    async def pause_computer(bot_id: str, body: bytes = Depends(require_signed_body)):
        return await _change(bot_id, body, "pause")

    @router.post("/desks/{bot_id}/computer/stop")
    async def stop_computer(bot_id: str, body: bytes = Depends(require_signed_body)):
        return await _change(bot_id, body, "stop")

    async def _open(websocket: WebSocket, bot_id: str, which: Literal["cdp", "vnc"], audit: str) -> ExecPipe | None:
        try:
            return await app.state.open_pipe(build_pipe_argv(bot_id, which))
        except OSError:
            app.state.audit.record(audit, bot_id, "unavailable")
            await _refuse(websocket, LIVE_CLOSE_UNAVAILABLE)
            return None

    @router.websocket("/desks/{bot_id}/computer/cdp")
    async def cdp_socket(websocket: WebSocket, bot_id: str) -> None:
        handle = await _gate(app, websocket, bot_id, "computer_cdp")
        if handle is None:
            return
        if not tokens_match(handle.cdp_token, websocket.headers.get(_TOKEN_HEADER)):
            app.state.audit.record("computer_cdp", bot_id, "bad_token")
            await _refuse(websocket, LIVE_CLOSE_UNAUTHENTICATED)
            return
        pipe = await _open(websocket, bot_id, "cdp", "computer_cdp")
        if pipe is None:
            return
        await app.state.computer_relays.take_over(bot_id, websocket)
        app.state.audit.record("computer_cdp", bot_id, "connected")
        touch = _Toucher(lambda: app.state.computers.touch(bot_id))
        framer = NulFramer()

        async def to_computer() -> None:
            try:
                while True:
                    text = await websocket.receive_text()
                    touch()
                    await pipe.write(text.encode("utf-8") + b"\0")
            except (WebSocketDisconnect, OSError):
                return

        async def to_client() -> None:
            try:
                while chunk := await pipe.read():
                    for message in framer.feed(chunk):
                        touch()
                        await websocket.send_text(message)
            except (ValueError, OSError):
                return

        gone = False
        try:
            gone = await _pump(to_computer(), to_client())
        finally:
            await pipe.close()
            app.state.computer_relays.release(bot_id, websocket)
            app.state.audit.record("computer_cdp", bot_id, "closed")
            await _refuse(websocket, LIVE_CLOSE_UNAVAILABLE if gone else _NORMAL_CLOSE)

    @router.websocket("/desks/{bot_id}/computer/vnc")
    async def vnc_socket(websocket: WebSocket, bot_id: str) -> None:
        handle = await _gate(app, websocket, bot_id, "computer_vnc")
        if handle is None:
            return
        if not app.state.computers.consume_vnc_ticket(bot_id, websocket.headers.get(_TOKEN_HEADER)):
            app.state.audit.record("computer_vnc", bot_id, "bad_token")
            await _refuse(websocket, LIVE_CLOSE_UNAUTHENTICATED)
            return
        if vnc_open.get(bot_id, 0) >= LIVE_VIEWERS_MAX + 1:
            app.state.audit.record("computer_vnc", bot_id, "too_many")
            await _refuse(websocket, LIVE_CLOSE_TOO_MANY)
            return
        vnc_open[bot_id] = vnc_open.get(bot_id, 0) + 1
        app.state.room.hold(bot_id)
        pipe: ExecPipe | None = None
        gone = False
        try:
            pipe = await _open(websocket, bot_id, "vnc", "computer_vnc")
            if pipe is None:
                return
            app.state.audit.record("computer_vnc", bot_id, "connected")
            gone = await _pump(_vnc_to_computer(websocket, pipe), _vnc_to_client(websocket, pipe))
        finally:
            if pipe is not None:
                await pipe.close()
                app.state.audit.record("computer_vnc", bot_id, "closed")
            vnc_open[bot_id] = vnc_open.get(bot_id, 1) - 1
            if vnc_open[bot_id] <= 0:
                vnc_open.pop(bot_id, None)
            app.state.room.release(bot_id)
            await _refuse(websocket, LIVE_CLOSE_UNAVAILABLE if gone else _NORMAL_CLOSE)

    return router


async def _vnc_to_computer(websocket: WebSocket, pipe: ExecPipe) -> None:
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            data = message.get("bytes")
            if data is None:
                await _refuse(websocket, LIVE_CLOSE_PROTOCOL)
                return
            await pipe.write(data)
    except (WebSocketDisconnect, OSError):
        return


async def _vnc_to_client(websocket: WebSocket, pipe: ExecPipe) -> None:
    try:
        while chunk := await pipe.read():
            await websocket.send_bytes(chunk)
    except (OSError, RuntimeError):
        return
