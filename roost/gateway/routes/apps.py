"""Apps on a bot's Linux computer over HTTP (docs/plans/2026-10-22-roost-install-app.md §7).

- ``GET /api/bots/{id}/apps``: the packages the owner said Yes to, oldest first.
- ``DELETE /api/bots/{id}/apps/{app_id}``: Remove. The owner's own click, so no card: the computer removes the
  package and the row goes. 503 when the computer can't be reached (the row stays), 409 when every computer is busy.

Another user's bot or app is a 404, never the row."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from roost.apps import texts
from roost.apps.models import BotAppOut, bot_app_out
from roost.apps.service import AppUnavailable
from roost.gateway.deps import CurrentUser, RequireOrigin

apps_router = APIRouter(tags=["apps"])


async def _owned_bot_or_404(request: Request, user, bot_id: str) -> None:
    if await request.app.state.bots.get(user.id, bot_id) is None:
        raise HTTPException(status_code=404, detail=texts.BOT_NOT_FOUND)


@apps_router.get("/api/bots/{bot_id}/apps")
async def list_apps(bot_id: str, request: Request, user: CurrentUser) -> list[BotAppOut]:
    await _owned_bot_or_404(request, user, bot_id)
    return [bot_app_out(app) for app in await request.app.state.apps.store.list_for_bot(user.id, bot_id)]


@apps_router.delete("/api/bots/{bot_id}/apps/{app_id}", status_code=204, dependencies=[RequireOrigin])
async def remove_app(bot_id: str, app_id: str, request: Request, user: CurrentUser) -> Response:
    await _owned_bot_or_404(request, user, bot_id)
    try:
        result = await request.app.state.apps.owner_remove(user.id, bot_id, app_id)
    except AppUnavailable as exc:
        status = 409 if exc.text == texts.BUSY else 503
        raise HTTPException(status_code=status, detail=exc.text) from exc
    if result == "not_found":
        raise HTTPException(status_code=404, detail=texts.APP_NOT_FOUND)
    return Response(status_code=204)
