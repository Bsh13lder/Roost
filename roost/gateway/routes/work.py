"""Work controls — ``POST /api/bots/{bot_id}/stop`` and ``PUT
/api/bots/{bot_id}/duty`` (spec §4.2 Stop and Off duty, §11 step 5).
Both 404 for an unknown or another user's bot (every lookup is scoped
by ``user_id``)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, StrictBool

from roost.bots.service import bot_out
from roost.gateway.deps import CurrentUser, RequireOrigin

work_router = APIRouter(prefix="/api/bots", tags=["work"])


class DutyIn(BaseModel):
    off_duty: StrictBool


@work_router.post("/{bot_id}/stop", dependencies=[RequireOrigin])
async def stop_bot(bot_id: str, request: Request, user: CurrentUser):
    if await request.app.state.bots.get(user.id, bot_id) is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    report = await request.app.state.turns.stop(user.id, bot_id)
    return {"dropped": len(report.waiting), "interrupted": len(report.interrupted), "done": list(report.done)}


@work_router.put("/{bot_id}/duty", dependencies=[RequireOrigin])
async def set_duty(bot_id: str, body: DutyIn, request: Request, user: CurrentUser):
    bot = await request.app.state.turns.set_off_duty(user.id, bot_id, body.off_duty)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot_out(bot, request.app.state.activity_board.get(bot_id))
