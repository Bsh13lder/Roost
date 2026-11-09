"""Team routes: the main-bot star (D-B, S1 D4): it moves, it never vanishes.

``POST``/``DELETE /api/bots/{bot_id}/star`` move or clear the star and
publish a ``bot_updated`` frame for every bot whose star changed."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from roost.bots.models import Bot
from roost.bots.service import bot_out
from roost.gateway.deps import CurrentUser, RequireOrigin

team_router = APIRouter(prefix="/api/bots", tags=["team"])

MAIN_BOT_STAYS = "There is always a main bot. Make another bot the main bot instead."


async def _publish_updated(request: Request, user_id: str, bots: tuple[Bot, ...]) -> None:
    board = request.app.state.activity_board
    for bot in bots:
        await request.app.state.events.publish(user_id, {"type": "bot_updated", "bot": bot_out(bot, board.get(bot.id))})


@team_router.post("/{bot_id}/star", dependencies=[RequireOrigin])
async def star_bot(bot_id: str, request: Request, user: CurrentUser):
    changed = await request.app.state.bots.set_primary(user.id, bot_id)
    if changed is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    await _publish_updated(request, user.id, changed)
    return bot_out(changed[0], request.app.state.activity_board.get(bot_id))


@team_router.delete("/{bot_id}/star", dependencies=[RequireOrigin])
async def unstar_bot(bot_id: str, request: Request, user: CurrentUser):
    """S1 D4: the star moves (``POST .../star`` on another bot) but never vanishes."""
    if await request.app.state.bots.get(user.id, bot_id) is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    raise HTTPException(status_code=409, detail=MAIN_BOT_STAYS)
