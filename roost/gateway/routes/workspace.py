"""Programs: ``GET /api/bots/{bot_id}/workspace/files?path=`` lists a folder of the bot's own workspace, read-only.

Owner check first (another user's bot is a 404), the path checked like the bot's own ``list_files`` (422), and
the listing made by the same fixed in-container script (``roost/programs/file_ops.py``). A refused path is a
404 with the script's reason in words; a workspace that can't be reached is a 503.

``POST /api/bots/{bot_id}/workspace/wipe`` (Wipe workspace) empties it and clears its workspace mark
(``roost/programs/wipe.py``), waiting for the bot's workspace lock; a wipe that did not finish is a 503.

``PUT /api/bots/{bot_id}/workspace-internet`` (A4, owner only) turns Internet in the workspace on or off: the keeper
recreates the workspace on the bot's own network through roost-egress (or with none), its files kept, waiting for
the workspace lock; then the switch is stored. A keeper that can't be reached is a 503 and nothing changes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StrictBool

from roost.bots.service import bot_out
from roost.constants import PROGRAM_FILE_OP_TIMEOUT_S
from roost.desk import DeskUnavailable
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.programs.args import workspace_path
from roost.programs.file_ops import ERROR_EXIT, error_code, file_ops_command, parse_listing
from roost.programs.marks import WorkspaceMarks
from roost.programs.wipe import wipe_workspace
from roost.programs.wrap import COULD_NOT_TEXT, UNAVAILABLE_TEXT, error_text

logger = logging.getLogger(__name__)
workspace_router = APIRouter(tags=["workspace"])


@workspace_router.get("/api/bots/{bot_id}/workspace/files")
async def list_workspace_files(bot_id: str, request: Request, user: CurrentUser, path: str = ""):
    bot = await request.app.state.bots.get(user.id, bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    try:
        folder = workspace_path(path, allow_root=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Give {exc}.") from exc
    desk = request.app.state.desks.for_bot(bot.id, bot.computer)
    try:
        result = await desk.exec(file_ops_command("list", folder), timeout_s=PROGRAM_FILE_OP_TIMEOUT_S)
    except DeskUnavailable as exc:
        raise HTTPException(status_code=503, detail=UNAVAILABLE_TEXT) from exc
    if result.exit_code == ERROR_EXIT:
        raise HTTPException(status_code=404, detail=error_text(error_code(result.stderr)))
    if result.exit_code != 0 or result.timed_out:
        raise HTTPException(status_code=503, detail=COULD_NOT_TEXT)
    listing = parse_listing(result.stdout)
    entries = [{"name": e.name, "kind": e.kind, "size": e.size} for e in listing.entries]
    return {"path": folder, "entries": entries, "more": listing.more}


@workspace_router.post("/api/bots/{bot_id}/workspace/wipe", dependencies=[RequireOrigin])
async def wipe_workspace_route(bot_id: str, request: Request, user: CurrentUser):
    """Wipe workspace: every file in the bot's workspace goes, and its workspace mark with it (owner only)."""
    bot = await request.app.state.bots.get(user.id, bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    desk = request.app.state.desks.for_bot(bot.id, bot.computer)
    lock = request.app.state.program_limits.lock(bot.id)
    outcome = await wipe_workspace(desk, WorkspaceMarks(request.app.state.config), lock, user.id, bot.id)
    if not outcome.ok:
        logger.warning("workspace wipe failed for bot %s: %s", bot.id, outcome.text)
        raise HTTPException(status_code=503, detail=outcome.text)
    return {"removed": outcome.removed}


class InternetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    on: StrictBool


@workspace_router.put("/api/bots/{bot_id}/workspace-internet", dependencies=[RequireOrigin])
async def set_workspace_internet(bot_id: str, body: InternetIn, request: Request, user: CurrentUser):
    """Internet in the workspace: the keeper switches the container first, then the bot's setting is stored."""
    store = request.app.state.bots
    bot = await store.get(user.id, bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    desk = request.app.state.desks.for_bot(bot.id, bot.computer)
    try:
        async with request.app.state.program_limits.lock(bot.id):
            await desk.set_workspace_internet(body.on)
    except DeskUnavailable as exc:
        logger.warning("workspace internet switch failed for bot %s", bot.id)
        raise HTTPException(status_code=503, detail=UNAVAILABLE_TEXT) from exc
    updated = await store.set_workspace_internet(user.id, bot.id, body.on)
    if updated is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    out = bot_out(updated, request.app.state.activity_board.get(updated.id))
    await request.app.state.events.publish(user.id, {"type": "bot_updated", "bot": out})
    return out
