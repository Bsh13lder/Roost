"""Teach a task over HTTP (docs/plans/2026-10-22-roost-teach.md).

- ``GET /api/bots/{id}/teach``: teaching or not, how many steps, whether the cap was reached.
- ``POST /api/bots/{id}/teach/start``: a fresh recording and Take control; 409 for a Mac Brave bot.
- ``POST /api/bots/{id}/teach/stop`` ``{description?, discard?}``: a skill proposal card in the bot's chat (or the
  recording thrown away) and the computer given back; 409 when not teaching, 422 when nothing was recorded or the
  proposal is refused (the recording stays).

Every route has ``CurrentUser`` and every write ``RequireOrigin``; another user's bot is a 404 first. Only the
person reaches these: no model tool does."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from roost.bots.models import Bot
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.teach import texts
from roost.teach.models import TeachRefused, TeachStopIn
from roost.teach.service import NotTeaching, TeachService, TeachStatus

teach_router = APIRouter(prefix="/api/bots", tags=["teach"])

BOT_NOT_FOUND = "Bot not found"


def _service(request: Request) -> TeachService:
    return request.app.state.teach


async def _owned(request: Request, user, bot_id: str) -> Bot:
    bot = await request.app.state.bots.get(user.id, bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND)
    return bot


def _status_out(status: TeachStatus) -> dict[str, Any]:
    return {"teaching": status.teaching, "steps": status.steps, "capped": status.capped,
            "started_at": status.started_at}


@teach_router.get("/{bot_id}/teach")
async def get_teach(bot_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    await _owned(request, user, bot_id)
    return _status_out(await _service(request).status(user.id, bot_id))


@teach_router.post("/{bot_id}/teach/start", dependencies=[RequireOrigin])
async def start_teach(bot_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    bot = await _owned(request, user, bot_id)
    try:
        return _status_out(await _service(request).start(user.id, bot))
    except TeachRefused as exc:
        raise HTTPException(status_code=409, detail=exc.text) from None


@teach_router.post("/{bot_id}/teach/stop", dependencies=[RequireOrigin])
async def stop_teach(bot_id: str, request: Request, user: CurrentUser,
                     body: TeachStopIn | None = None) -> dict[str, Any]:
    await _owned(request, user, bot_id)
    body = body or TeachStopIn()
    try:
        outcome = await _service(request).stop(user.id, bot_id, body.description, discard=body.discard)
    except NotTeaching:
        raise HTTPException(status_code=409, detail=texts.NOT_TEACHING) from None
    except TeachRefused as exc:
        raise HTTPException(status_code=422, detail=exc.text) from None
    return {"proposal_id": outcome.proposal_id, "steps": outcome.steps, "discarded": outcome.discarded}
