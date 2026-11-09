"""The usage reading, token usage and a bot's full-limit switch.

``GET /api/usage?days=N`` says whether Roost can read the usage limit, and adds the user's token usage for the
last ``N`` local days (per day, per bot, the background bucket, the busiest bot); ``GET /api/bots/{id}/usage``
is one bot's (docs/plans/2026-11-04-roost-token-usage.md). ``PUT /api/bots/{bot_id}/full-limit`` is the only
door that sets ``bots.full_limit_until`` (no tool, proposal or question can): on lasts until the reading's reset
(or the next local midnight), and with no reading it is refused, because the 10% reserve could not be checked."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, StrictBool

from roost.bots.service import bot_out
from roost.constants import USAGE_DAYS_DEFAULT, USAGE_DAYS_MAX
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.usage.report import bot_report, user_report
from roost.usage.reading import FULL_LIMIT_REFUSAL, full_limit_end

usage_router = APIRouter(prefix="/api", tags=["usage"])

Days = Annotated[int, Query(ge=1, le=USAGE_DAYS_MAX)]


def _since(today: str, days: int) -> str:
    return (date.fromisoformat(today) - timedelta(days=days - 1)).isoformat()


class FullLimitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on: StrictBool


async def _reading(request: Request) -> dict:
    reading = await request.app.state.usage.read()
    if reading is None:
        return {"readable": False, "remaining_fraction": None, "resets_at": None}
    return {"readable": True, "remaining_fraction": reading.remaining_fraction,
            "resets_at": reading.resets_at.isoformat() if reading.resets_at else None}


@usage_router.get("/usage")
async def get_usage(request: Request, user: CurrentUser, days: Days = USAGE_DAYS_DEFAULT):
    state = request.app.state
    today = state.token_usage.today()
    rows = await state.token_usage.rows(user.id, since_day=_since(today, days))
    names = {bot.id: bot.name for bot in await state.bots.list(user.id)}
    return {**await _reading(request), **user_report(rows, today=today, days=days, names=names)}


@usage_router.get("/bots/{bot_id}/usage")
async def get_bot_usage(bot_id: str, request: Request, user: CurrentUser, days: Days = USAGE_DAYS_DEFAULT):
    state = request.app.state
    if await state.bots.get(user.id, bot_id) is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    today = state.token_usage.today()
    rows = await state.token_usage.rows(user.id, since_day=_since(today, days), bot_id=bot_id)
    return bot_report(bot_id, rows, today=today, days=days)


@usage_router.put("/bots/{bot_id}/full-limit", dependencies=[RequireOrigin])
async def set_full_limit(bot_id: str, body: FullLimitIn, request: Request, user: CurrentUser):
    state = request.app.state
    if await state.bots.get(user.id, bot_id) is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    until = None
    if body.on:
        reading = await state.usage.read()
        if reading is None:
            raise HTTPException(status_code=422, detail=FULL_LIMIT_REFUSAL)
        until = full_limit_end(reading, datetime.now(timezone.utc))
    bot = await state.bots.set_full_limit(user.id, bot_id, until)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    out = bot_out(bot, state.activity_board.get(bot.id))
    await state.events.publish(user.id, {"type": "bot_updated", "bot": out})
    return out
