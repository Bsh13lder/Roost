"""The keeper's own FastAPI app — a separate process from the gateway,
run by uvicorn on ``127.0.0.1:18801`` via ``python -m roost.keeper``.

Every HTTP route here requires ``roost.keeper.auth.require_signed_body``
first (401 on anything unsigned, replayed, tampered or stale), then
validates the ``bot_id`` path segment as a UUID4 (400 otherwise) and the
JSON body against a strict, extra-forbidding schema (422 on any unknown
field). The browser lifecycle, the workspace container lifecycle
(``roost/keeper/workspaces.py``), ``DELETE /desks/{bot_id}`` (retire
both at once) and ``POST /desks/{bot_id}/main-browser/open`` all land
here. That last route is the stuck flow's "Use my main Brave": it runs
``/usr/bin/open -a "Brave Browser" <url>`` for one checked address and
nothing more (``roost/keeper/main_browser.py``).

The Mac file routes (``/mac/grants``, ``/mac/check-folder``, ``/mac/pick-folder`` and
``/mac/fs/*``) are registered by ``roost/keeper/macfs/routes.py``. They share the same
signature check; grants live in this process's memory only.

The one WebSocket route, ``/desks/{bot_id}/cdp``, is deliberately not
HMAC-signed (a WebSocket upgrade has no body to sign) — it is gated
instead by the per-bot ``cdp_token`` minted on browser start, carried in
the ``X-Roost-Desk-Token`` header. Per the controller's ruling, it always
accepts the socket first and then closes with a specific code, so a
client always gets a real WebSocket close frame instead of a bare HTTP
rejection: 4400 for a malformed ``bot_id`` (same format rule as the HTTP
routes' 400, just a WebSocket close code instead), 4401 for a missing or
wrong token, 4404 for no running browser, or 4409 when a second
connection for the same bot takes over.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.config import RoostConfig
from roost.constants import MAIN_BROWSER_URL_MAX_CHARS
from roost.desk.signing import NonceCache
from roost.desk.url_policy import UrlBlocked, check_url
from roost.keeper.audit import AuditLog
from roost.keeper.auth import require_signed_body
from roost.keeper.browsers import BraveLauncher, BrowserStartError
from roost.keeper.computer_room import ComputerRoom
from roost.keeper.computer_routes import computer_routes
from roost.keeper.computers import ComputerControlError, ComputerManager
from roost.keeper.macfs.routes import register_mac_routes
from roost.keeper.macfs.state import MacFs
from roost.keeper.main_browser import MainBrowserOpener, MainBrowserOpenError
from roost.keeper.networks import EgressNetworks
from roost.keeper.paths import desk_dir
from roost.keeper.pipe_relay import PipeRelay, RelayRegistry, tokens_match
from roost.keeper.workspaces import WorkspaceManager, WorkspaceRemoveError, WorkspaceStartError, WorkspaceStopError

_BOT_ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)

_BAD_BOT_ID_DETAIL = "bot_id must be a UUID4"

# POST /desks/{bot_id}/main-browser/open (stuck flow, Task 6). Neither text,
# nor anything else this route answers or audits, ever carries the address.
_MAIN_BROWSER_OPEN_ACTION = "main_browser_open"
_URL_REFUSED_DETAIL = "that address can't be opened"
_MAIN_BROWSER_FAILED_DETAIL = "failed to open the main browser"

_DESK_TOKEN_HEADER = "x-roost-desk-token"

# Fix round 1, finding 1: the signed HTTP routes reject a malformed
# bot_id with 400. A WebSocket close code can't reuse an HTTP status,
# and a malformed id isn't described by any of 4401 (bad token) / 4404
# (not running) / 4409 (superseded) -- those mean the id was well-formed
# but something else was wrong -- so this route uses its own code in the
# private-use range instead of silently folding into 4404.
_BAD_BOT_ID_WS_CLOSE_CODE = 4400

# Defense in depth for DELETE /desks/{bot_id} (retire): a helper process Brave spawned may still hold a file in the
# profile dir for a moment after the browser is reaped, and rmtree(ignore_errors=True) would then leave it partly
# behind with no signal. A short retry absorbs that.
_DESK_DIR_REMOVE_ATTEMPTS = 10
_DESK_DIR_REMOVE_RETRY_DELAY_S = 0.2


class _EmptyBody(BaseModel):
    """Every browser-lifecycle, workspace-lifecycle and retire request
    body is an empty JSON object — this model exists purely to turn any
    unknown field into a 422 rather than silently ignoring it."""

    model_config = ConfigDict(extra="forbid")


class _WorkspaceExecBody(BaseModel):
    """``POST /desks/{bot_id}/workspace/exec``'s body, exactly: an argv
    list and a bounded timeout. ``extra="forbid"`` is what turns a
    smuggled ``user``/``privileged``/``env``/``workdir`` field into a 422
    here instead of it silently reaching ``WorkspaceManager.exec`` and
    overriding the fixed, locked-down exec argv this app always builds
    (see the Review Focus item in contract.md)."""

    model_config = ConfigDict(extra="forbid")

    argv: list[str] = Field(min_length=1)
    timeout_s: int = Field(ge=1, le=120)


class _WorkspaceInternetBody(BaseModel):
    """``POST /desks/{bot_id}/workspace/internet``'s body, exactly one strict boolean (A4)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    internet: bool


class _MainBrowserOpenBody(BaseModel):
    """``POST /desks/{bot_id}/main-browser/open``'s body, exactly one address.
    ``extra="forbid"`` turns a smuggled ``app`` or ``args`` field into a 422,
    so nothing but the checked address ever reaches ``open``'s argv."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=MAIN_BROWSER_URL_MAX_CHARS)


def _require_valid_bot_id(bot_id: str) -> None:
    if not _BOT_ID_RE.match(bot_id):
        raise HTTPException(status_code=400, detail=_BAD_BOT_ID_DETAIL)


def _require_empty_body(body: bytes) -> None:
    try:
        _EmptyBody.model_validate_json(body or b"{}")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


def _parse_workspace_exec_body(body: bytes) -> _WorkspaceExecBody:
    try:
        return _WorkspaceExecBody.model_validate_json(body or b"{}")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


def _parse_main_browser_open_body(body: bytes) -> _MainBrowserOpenBody:
    """Like ``_parse_workspace_exec_body``, except the 422 detail never echoes the input.
    A rejected body may still carry the address, and ``KeeperClient`` puts a non-2xx
    response's text into its ``DeskUnavailable`` message."""
    try:
        return _MainBrowserOpenBody.model_validate_json(body or b"{}")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_input=False, include_url=False)) from exc


async def _open_in_main_browser(app: FastAPI, bot_id: str, body: bytes) -> dict[str, bool]:
    """Stuck flow (design §3, R8): open one checked address in the user's own Brave.

    The order is bot id (400), body (422), ``check_url`` (400, audited
    ``refused``), then the opener (500, audited ``error``). The canonical URL
    ``check_url`` returns is what is opened, never the raw input. The audit
    line holds only the action, the bot id and the result."""
    _require_valid_bot_id(bot_id)
    open_body = _parse_main_browser_open_body(body)
    try:
        checked_url = check_url(open_body.url)
    except UrlBlocked as exc:
        app.state.audit.record(_MAIN_BROWSER_OPEN_ACTION, bot_id, "refused")
        raise HTTPException(status_code=400, detail=_URL_REFUSED_DETAIL) from exc
    try:
        await app.state.main_browser.open(checked_url)
    except MainBrowserOpenError as exc:
        app.state.audit.record(_MAIN_BROWSER_OPEN_ACTION, bot_id, "error")
        raise HTTPException(status_code=500, detail=_MAIN_BROWSER_FAILED_DETAIL) from exc
    app.state.audit.record(_MAIN_BROWSER_OPEN_ACTION, bot_id, "ok")
    return {"opened": True}


async def _remove_desk_dir_with_retry(path: Path) -> None:
    """``shutil.rmtree(path, ignore_errors=True)``, retried a few times
    (see ``_DESK_DIR_REMOVE_ATTEMPTS``'s comment above) if the directory
    is still there afterward. A no-op loop (one attempt, no sleep) on the
    overwhelmingly common case where the first call already removed it."""
    for attempt in range(_DESK_DIR_REMOVE_ATTEMPTS):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        if attempt < _DESK_DIR_REMOVE_ATTEMPTS - 1:
            await asyncio.sleep(_DESK_DIR_REMOVE_RETRY_DELAY_S)


async def _pump_client_to_browser(websocket: WebSocket, relay: PipeRelay) -> None:
    try:
        while True:
            text = await websocket.receive_text()
            await relay.send(text)
    except WebSocketDisconnect:
        return


async def _pump_browser_to_client(websocket: WebSocket, relay: PipeRelay) -> None:
    async for text in relay:
        await websocket.send_text(text)


def create_app(config: RoostConfig) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Docker containers outlive the keeper process; WorkspaceManager's
        # in-memory state does not -- reconcile against Docker's own
        # ground truth once, on real startup, so a restart never reports
        # a bot's still-there container as "absent" (see
        # WorkspaceManager.reconcile's docstring). Only a real server
        # boot (uvicorn) or `with TestClient(app) as c:` runs this --
        # the bare `TestClient(app)` every other test in this file uses
        # never does (same documented caveat as the gateway's lifespan,
        # roost/gateway/app.py), so those tests' in-memory state is
        # exactly as before.
        await app.state.workspaces.reconcile()
        await app.state.computers.reconcile()
        sweeper = asyncio.create_task(app.state.room.run_sweeper())
        try:
            yield
        finally:
            sweeper.cancel()
            await asyncio.gather(sweeper, return_exceptions=True)

    # No route in this app -- including FastAPI's own auto-generated
    # docs/schema endpoints -- is reachable without the shared
    # keeper_secret (see module docstring). docs_url/redoc_url/openapi_url
    # must stay disabled so those three routes 404 instead of serving
    # unsigned route/schema disclosure.
    app = FastAPI(title="roost-keeper", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.config = config
    app.state.nonce_cache = NonceCache()
    app.state.launcher = BraveLauncher(config)
    app.state.audit = AuditLog(config.database_dir / "keeper-audit.log")
    app.state.relays = RelayRegistry()
    app.state.networks = EgressNetworks()
    app.state.workspaces = WorkspaceManager(config, networks=app.state.networks)
    app.state.computers = ComputerManager(config, app.state.networks)
    app.state.room = ComputerRoom(app.state.computers)
    app.include_router(computer_routes(app))
    app.state.main_browser = MainBrowserOpener()
    app.state.mac = MacFs(config)
    register_mac_routes(app)

    @app.get("/desks/{bot_id}")
    async def get_desk(bot_id: str, body: bytes = Depends(require_signed_body)):
        _require_valid_bot_id(bot_id)
        _require_empty_body(body)
        running = app.state.launcher.is_running(bot_id)
        workspace_status = app.state.workspaces.status(bot_id)
        app.state.audit.record("desk_status", bot_id, "ok")
        return {"browser": "running" if running else "stopped", "workspace": workspace_status,
                "computer": app.state.computers.state(bot_id)}

    @app.post("/desks/{bot_id}/browser/start")
    async def start_browser(bot_id: str, body: bytes = Depends(require_signed_body)):
        _require_valid_bot_id(bot_id)
        _require_empty_body(body)
        try:
            handle = await app.state.launcher.start(bot_id)
        except BrowserStartError as exc:
            app.state.audit.record("browser_start", bot_id, "error")
            raise HTTPException(status_code=500, detail="failed to start the bot's browser") from exc
        app.state.audit.record("browser_start", bot_id, "ok")
        return {"browser": "running", "cdp_token": handle.cdp_token}

    @app.post("/desks/{bot_id}/browser/stop")
    async def stop_browser(bot_id: str, body: bytes = Depends(require_signed_body)):
        _require_valid_bot_id(bot_id)
        _require_empty_body(body)
        await app.state.launcher.stop(bot_id)
        app.state.audit.record("browser_stop", bot_id, "ok")
        return {"browser": "stopped"}

    @app.post("/desks/{bot_id}/browser/attach")
    async def attach_browser(bot_id: str, body: bytes = Depends(require_signed_body)):
        """S1.8 screenshots: the running browser's relay token. Never starts one: 409 when it is closed."""
        _require_valid_bot_id(bot_id)
        _require_empty_body(body)
        handle = app.state.launcher.get_handle(bot_id)
        if handle is None:
            app.state.audit.record("browser_attach", bot_id, "not_running")
            raise HTTPException(status_code=409, detail="asleep")
        app.state.audit.record("browser_attach", bot_id, "ok")
        return {"browser": "running", "cdp_token": handle.cdp_token}

    @app.post("/desks/{bot_id}/workspace/start")
    async def start_workspace(bot_id: str, body: bytes = Depends(require_signed_body)):
        _require_valid_bot_id(bot_id)
        _require_empty_body(body)
        try:
            await app.state.workspaces.start(bot_id)
        except WorkspaceStartError as exc:
            app.state.audit.record("workspace_start", bot_id, "error")
            raise HTTPException(status_code=500, detail="failed to start the bot's workspace") from exc
        app.state.audit.record("workspace_start", bot_id, "ok")
        return {"workspace": "running"}

    @app.post("/desks/{bot_id}/workspace/internet")
    async def set_workspace_internet(bot_id: str, body: bytes = Depends(require_signed_body)):
        """A4: Internet in the workspace on or off; a workspace made the other way is recreated (files kept)."""
        _require_valid_bot_id(bot_id)
        try:
            wanted = _WorkspaceInternetBody.model_validate_json(body or b"{}")
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors(include_input=False, include_url=False)) from exc
        try:
            await app.state.workspaces.set_internet(bot_id, wanted.internet)
        except (WorkspaceStartError, WorkspaceRemoveError) as exc:
            app.state.audit.record("workspace_internet", bot_id, "error")
            raise HTTPException(status_code=500, detail="failed to switch the bot's workspace network") from exc
        app.state.audit.record("workspace_internet", bot_id, "on" if wanted.internet else "off")
        return {"internet": wanted.internet}

    @app.post("/desks/{bot_id}/workspace/exec")
    async def exec_workspace(bot_id: str, body: bytes = Depends(require_signed_body)):
        _require_valid_bot_id(bot_id)
        exec_body = _parse_workspace_exec_body(body)
        result = await app.state.workspaces.exec(bot_id, exec_body.argv, exec_body.timeout_s)
        app.state.audit.record("workspace_exec", bot_id, "timeout" if result.timed_out else "ok")
        return {
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": result.timed_out,
            "truncated": result.truncated,
        }

    @app.post("/desks/{bot_id}/workspace/stop")
    async def stop_workspace(bot_id: str, body: bytes = Depends(require_signed_body)):
        _require_valid_bot_id(bot_id)
        _require_empty_body(body)
        try:
            await app.state.workspaces.stop(bot_id)
        except WorkspaceStopError as exc:
            app.state.audit.record("workspace_stop", bot_id, "error")
            raise HTTPException(status_code=500, detail="failed to stop the bot's workspace") from exc
        app.state.audit.record("workspace_stop", bot_id, "ok")
        return {"workspace": "stopped"}

    @app.post("/desks/{bot_id}/main-browser/open")
    async def open_main_browser(bot_id: str, body: bytes = Depends(require_signed_body)):
        """Stuck flow: "Use my main Brave" (see ``_open_in_main_browser``)."""
        return await _open_in_main_browser(app, bot_id, body)

    @app.delete("/desks/{bot_id}")
    async def retire_desk(bot_id: str, body: bytes = Depends(require_signed_body)):
        _require_valid_bot_id(bot_id)
        _require_empty_body(body)
        await app.state.launcher.stop(bot_id)
        # A docker failure must not fall through to deleting the desk dir below: that would compound a
        # leaked container with losing the host-side files that point at it. The workspace goes first: with
        # internet on (A4) it sits on the bot's network, which removing the computer deletes.
        try:
            await app.state.workspaces.remove(bot_id)
        except WorkspaceRemoveError as exc:
            app.state.audit.record("desk_retire", bot_id, "error")
            raise HTTPException(status_code=500, detail="failed to remove the bot's workspace") from exc
        try:
            await app.state.computers.remove(bot_id)
        except ComputerControlError as exc:
            app.state.audit.record("desk_retire", bot_id, "error")
            raise HTTPException(status_code=500, detail="failed to remove the bot's computer") from exc
        await _remove_desk_dir_with_retry(desk_dir(app.state.config.desks_dir, bot_id))
        app.state.audit.record("desk_retire", bot_id, "ok")
        return {"retired": True}

    @app.websocket("/desks/{bot_id}/cdp")
    async def cdp_relay(websocket: WebSocket, bot_id: str) -> None:
        # Ruling 9 (controller, 2026-10-13): always accept first, then
        # close with the specific code — a client always gets a real
        # WebSocket close frame, never a bare HTTP rejection.
        await websocket.accept()

        if not _BOT_ID_RE.match(bot_id):
            app.state.audit.record("cdp_relay", bot_id, "bad_bot_id")
            await websocket.close(code=_BAD_BOT_ID_WS_CLOSE_CODE)
            return

        handle = app.state.launcher.get_handle(bot_id)
        if handle is None:
            app.state.audit.record("cdp_relay", bot_id, "not_running")
            await websocket.close(code=4404)
            return

        provided_token = websocket.headers.get(_DESK_TOKEN_HEADER)
        if not tokens_match(handle.cdp_token, provided_token):
            app.state.audit.record("cdp_relay", bot_id, "bad_token")
            await websocket.close(code=4401)
            return

        # Takes over as the bot's one active relay client, closing any
        # previous connection for this bot with 4409 before this one
        # starts reading the (single-stream) browser pipe.
        await app.state.relays.take_over(bot_id, websocket)
        app.state.audit.record("cdp_relay", bot_id, "connected")

        relay = PipeRelay(handle)
        inbound = asyncio.create_task(_pump_client_to_browser(websocket, relay))
        outbound = asyncio.create_task(_pump_browser_to_client(websocket, relay))
        try:
            await asyncio.wait({inbound, outbound}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            inbound.cancel()
            outbound.cancel()
            await asyncio.gather(inbound, outbound, return_exceptions=True)
            relay.close()
            app.state.relays.release(bot_id, websocket)
            with contextlib.suppress(Exception):
                await websocket.close()

    return app
