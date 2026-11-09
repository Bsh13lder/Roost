"""Chat pictures (owner, 2026-11-05; docs/plans/2026-11-05-roost-chat-pictures.md): ``POST
/api/threads/{thread_id}/media`` takes one picture (or one frame of a video) and keeps it, re-encoded and sealed,
until a message carries it; ``GET /api/media/{id}`` serves one back. Another user's thread or picture is a 404."""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request, Response, UploadFile

from roost.constants import (
    CHAT_MEDIA_CACHE,
    CHAT_MEDIA_MAX_BYTES,
    CHAT_MEDIA_UPLOAD_WINDOW_S,
    CHAT_MEDIA_UPLOADS_PER_WINDOW,
    CHAT_MEDIA_VIDEO,
)
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.media.process import NotAPicture, normalise_picture

media_router = APIRouter(tags=["media"])
THREAD_NOT_FOUND = "Thread not found"
PICTURE_NOT_FOUND = "Picture not found"
TOO_BIG_TEXT = "That file is too big. Send a picture under 15 MB."
TOO_MANY_TEXT = "That's a lot of pictures at once. Send these first, then add more."
_CHUNK = 1024 * 1024


async def _capped(file: UploadFile) -> bytes:
    """The upload, read piece by piece and refused as soon as it passes the cap."""
    pieces: list[bytes] = []
    size = 0
    while piece := await file.read(_CHUNK):
        size += len(piece)
        if size > CHAT_MEDIA_MAX_BYTES:
            raise HTTPException(status_code=413, detail=TOO_BIG_TEXT)
        pieces.append(piece)
    return b"".join(pieces)


@media_router.post("/api/threads/{thread_id}/media", dependencies=[RequireOrigin])
async def upload_media(thread_id: str, request: Request, user: CurrentUser, file: UploadFile,
                       video: str | None = Form(default=None)):
    state = request.app.state
    if await state.talk.get_thread(user.id, thread_id) is None:
        raise HTTPException(status_code=404, detail=THREAD_NOT_FOUND)
    if await state.media.loose_since(user.id, thread_id, CHAT_MEDIA_UPLOAD_WINDOW_S) >= CHAT_MEDIA_UPLOADS_PER_WINDOW:
        raise HTTPException(status_code=429, detail=TOO_MANY_TEXT)
    try:
        picture = normalise_picture(await _capped(file))
    except NotAPicture as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    group = CHAT_MEDIA_VIDEO if video == "1" else None
    added = await state.media.add(user.id, thread_id, picture, source="you", group=group)
    return {"id": added["id"], "width": added["width"], "height": added["height"]}


@media_router.get("/api/media/{media_id}")
async def get_media(media_id: str, request: Request, user: CurrentUser) -> Response:
    jpeg = await request.app.state.media.jpeg(user.id, media_id)
    if jpeg is None:
        raise HTTPException(status_code=404, detail=PICTURE_NOT_FOUND)
    return Response(content=jpeg, media_type="image/jpeg",
                    headers={"Cache-Control": CHAT_MEDIA_CACHE, "X-Content-Type-Options": "nosniff"})
