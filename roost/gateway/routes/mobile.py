"""In-app update: ``GET /api/mobile/latest`` and ``GET /api/mobile/apk/{file}`` (signed in).

The phone app asks for the newest release on start and from Settings, and downloads the APK with its session
cookie. Nothing here writes: the files come from ``scripts/publish_mobile.sh`` (see ``roost/mobile_update/``)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from roost.constants import MOBILE_APK_MEDIA_TYPE
from roost.gateway.deps import CurrentUser
from roost.mobile_update.release import apk_path, read_latest

mobile_router = APIRouter(prefix="/api/mobile", tags=["mobile"])

NOTHING_PUBLISHED = "No app update has been published yet."
NO_SUCH_APK = "That app file is not available."


@mobile_router.get("/latest")
async def latest_release(request: Request, user: CurrentUser) -> JSONResponse:
    release = read_latest(request.app.state.config.mobile_dir)
    if release is None:
        raise HTTPException(status_code=404, detail=NOTHING_PUBLISHED)
    return JSONResponse(release.model_dump(), headers={"Cache-Control": "no-store"})


@mobile_router.get("/apk/{file}")
async def download_apk(file: str, request: Request, user: CurrentUser) -> FileResponse:
    path = apk_path(request.app.state.config.mobile_dir, file)
    if path is None:
        raise HTTPException(status_code=404, detail=NO_SUCH_APK)
    return FileResponse(path, media_type=MOBILE_APK_MEDIA_TYPE, filename=file,
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
