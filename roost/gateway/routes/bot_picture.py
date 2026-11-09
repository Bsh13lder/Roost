"""A bot's own picture (look & feel redesign P1, the avatar editor's Upload): ``POST`` puts one on
its robot's screen, ``DELETE`` takes it off, ``GET`` serves it to the owner's pages. The body is the
raw image, like a PDF upload (``POST /api/documents/pdf``). Every change publishes ``bot_updated``."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from roost.bots.models import Bot
from roost.bots.picture import NotAPicture, Picture, PictureTooBig, TOO_BIG_TEXT, read_picture
from roost.bots.service import bot_out
from roost.constants import AVATAR_PICTURE_MAX_BYTES
from roost.gateway.deps import CurrentUser, RequireOrigin

bot_picture_router = APIRouter(prefix="/api/bots", tags=["bots"])
BOT_NOT_FOUND_TEXT = "Bot not found"
NO_PICTURE_TEXT = "This bot has no picture"
# A picture is user content, so like a PDF or a screenshot it is never kept in a cache. The address
# still carries the picture's version (?v=), so a new picture is a new address.
PICTURE_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


async def _capped_body(request: Request) -> bytes:
    """The body, read piece by piece and refused as soon as it passes the cap, so a body sent
    without a Content-Length is never held whole in memory."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > AVATAR_PICTURE_MAX_BYTES:
        raise HTTPException(status_code=413, detail=TOO_BIG_TEXT)
    pieces: list[bytes] = []
    size = 0
    async for piece in request.stream():
        size += len(piece)
        if size > AVATAR_PICTURE_MAX_BYTES:
            raise HTTPException(status_code=413, detail=TOO_BIG_TEXT)
        pieces.append(piece)
    return b"".join(pieces)


async def _picture_body(request: Request) -> Picture:
    data = await _capped_body(request)
    try:
        return read_picture(request.headers.get("content-type", ""), data)
    except PictureTooBig as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except NotAPicture as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc


async def _changed(request: Request, user_id: str, bot: Bot | None) -> dict[str, Any]:
    if bot is None:
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND_TEXT)
    out = bot_out(bot, request.app.state.activity_board.get(bot.id))
    await request.app.state.events.publish(user_id, {"type": "bot_updated", "bot": out})
    return out


@bot_picture_router.post("/{bot_id}/picture", dependencies=[RequireOrigin])
async def upload_picture(bot_id: str, request: Request, user: CurrentUser):
    picture = await _picture_body(request)
    return await _changed(request, user.id, await request.app.state.bots.set_picture(user.id, bot_id, picture))


@bot_picture_router.delete("/{bot_id}/picture", dependencies=[RequireOrigin])
async def remove_picture(bot_id: str, request: Request, user: CurrentUser):
    return await _changed(request, user.id, await request.app.state.bots.set_picture(user.id, bot_id, None))


@bot_picture_router.get("/{bot_id}/picture")
async def get_picture(bot_id: str, request: Request, user: CurrentUser) -> Response:
    picture = await request.app.state.bots.get_picture(user.id, bot_id)
    if picture is None:
        raise HTTPException(status_code=404, detail=NO_PICTURE_TEXT)
    return Response(content=picture.data, media_type=picture.media_type, headers=PICTURE_HEADERS)
