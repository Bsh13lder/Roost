"""Desk HTTP API — ``GET /api/bots/{bot_id}/desk``, ``POST .../desk/
browser/start`` · ``/stop``, ``POST .../desk/workspace/exec`` (see the
contract's HTTP API table).

Same ownership-check pattern as ``roost/gateway/routes/threads.py``: the
bot is looked up via ``BotStore.get(user.id, bot_id)`` first — a foreign
or unknown bot id is a 404 before ``DeskFactory`` is ever touched, so a
second user never even learns whether the first user's bot has a desk at
all. ``DeskUnavailable`` (the keeper process can't be reached) is caught
at every route and turned into a clean 503 ``{"detail": "desk
unavailable"}`` rather than a raw connection error.

``open_page``/``read_page`` are deliberately not exposed as HTTP routes
here — the contract's HTTP API table only lists status/browser/workspace
endpoints; the model reaches a bot's browser through its own tools
(``roost/talk/tools.py``, Task 10/11), never directly over HTTP.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from roost.constants import MAX_EXEC_COMMAND_LENGTH, MIN_EXEC_COMMAND_LENGTH
from roost.bots.models import Bot
from roost.constants import COMPUTERS_BUSY_TEXT
from roost.desk import Desk, DeskAsleep, DeskBusy, DeskStatus, DeskUnavailable, ExecResult
from roost.desk.control import Hold
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.vault.models import NO_SITE_TEXT, GiveBackIn, NoSite, clean_label

desk_router = APIRouter(tags=["desk"])

_UNAVAILABLE_DETAIL = "desk unavailable"


class ExecRequest(BaseModel):
    command: str = Field(min_length=MIN_EXEC_COMMAND_LENGTH, max_length=MAX_EXEC_COMMAND_LENGTH)


def _status_out(status: DeskStatus) -> dict[str, str | None]:
    return {"browser": status.browser, "workspace": status.workspace, "computer": status.computer,
            "state": status.state}


def _exec_out(result: ExecResult) -> dict[str, object]:
    return {
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "timed_out": result.timed_out,
        "truncated": result.truncated,
    }


async def _owned_bot_or_404(request: Request, user, bot_id: str) -> Bot:
    bot = await request.app.state.bots.get(user.id, bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot


async def _desk_of(request: Request, user, bot_id: str) -> Desk:
    """The bot's own desk (its computer kind), after the owner check."""
    bot = await _owned_bot_or_404(request, user, bot_id)
    return request.app.state.desks.for_bot(bot.id, bot.computer)


def _unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail=_UNAVAILABLE_DETAIL)


@desk_router.get("/api/bots/{bot_id}/desk")
async def get_desk(bot_id: str, request: Request, user: CurrentUser):
    desk = await _desk_of(request, user, bot_id)
    try:
        status = await desk.status()
    except DeskUnavailable:
        raise _unavailable()
    return _status_out(status)


@desk_router.post("/api/bots/{bot_id}/desk/browser/start", dependencies=[RequireOrigin])
async def start_browser(bot_id: str, request: Request, user: CurrentUser):
    desk = await _desk_of(request, user, bot_id)
    try:
        status = await desk.start_browser()
    except DeskBusy:
        raise HTTPException(status_code=409, detail=COMPUTERS_BUSY_TEXT)
    except DeskUnavailable:
        raise _unavailable()
    return _status_out(status)


@desk_router.post("/api/bots/{bot_id}/desk/browser/stop", dependencies=[RequireOrigin])
async def stop_browser(bot_id: str, request: Request, user: CurrentUser):
    desk = await _desk_of(request, user, bot_id)
    try:
        status = await desk.stop_browser()
    except DeskUnavailable:
        raise _unavailable()
    return _status_out(status)


@desk_router.post("/api/bots/{bot_id}/desk/workspace/exec", dependencies=[RequireOrigin])
async def exec_workspace(bot_id: str, body: ExecRequest, request: Request, user: CurrentUser):
    desk = await _desk_of(request, user, bot_id)
    try:
        result = await desk.exec(body.command)
    except DeskUnavailable:
        raise _unavailable()
    return _exec_out(result)


def _control_out(hold: Hold | None, now_wall: datetime, now_clock: float) -> dict[str, object]:
    if hold is None:
        return {"held": False, "since": None}
    began = now_wall - timedelta(seconds=max(0.0, now_clock - hold.since))
    return {"held": True, "since": began.isoformat()}


def _control_state(request: Request, bot_id: str) -> dict[str, object]:
    lock = request.app.state.control
    return _control_out(lock.held(bot_id), datetime.now(timezone.utc), time.monotonic())


@desk_router.get("/api/bots/{bot_id}/desk/screenshot")
async def screenshot(bot_id: str, request: Request, user: CurrentUser) -> Response:
    """S1.8: viewing never starts a browser (409 "asleep"). Owner-checked, never cached."""
    await _owned_bot_or_404(request, user, bot_id)
    desk = request.app.state.desks.for_bot(bot_id)
    try:
        image = await desk.screenshot()
    except DeskAsleep:
        raise HTTPException(status_code=409, detail="asleep")
    except DeskUnavailable:
        raise _unavailable()
    return Response(content=image, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@desk_router.get("/api/bots/{bot_id}/control")
async def get_control(bot_id: str, request: Request, user: CurrentUser):
    await _owned_bot_or_404(request, user, bot_id)
    return _control_state(request, bot_id)


@desk_router.post("/api/bots/{bot_id}/control", dependencies=[RequireOrigin])
async def take_control(bot_id: str, request: Request, user: CurrentUser):
    """Take control: only the person, from the Computer tab. No model tool reaches this."""
    await _owned_bot_or_404(request, user, bot_id)
    request.app.state.control.take(bot_id)
    return _control_state(request, bot_id)


@desk_router.delete("/api/bots/{bot_id}/control", dependencies=[RequireOrigin])
async def give_back_control(bot_id: str, request: Request, user: CurrentUser, body: GiveBackIn | None = None):
    """Give it back. An optional ``account`` ("Which account did you use?") is saved for the site the computer
    is on and said to the bot. With no site to name, nothing is given back (400): try again without one. A teach
    recording in progress is thrown away: only I'm done teaching turns one into a skill."""
    bot = await _owned_bot_or_404(request, user, bot_id)
    label = clean_label(body.account) if body is not None and body.account else ""
    login = None
    if label:
        url = await request.app.state.desks.for_bot(bot.id, bot.computer).current_url()
        try:
            login = await request.app.state.vault.sign_in(user.id, bot.id, url, label)
        except NoSite as exc:
            raise HTTPException(status_code=400, detail=NO_SITE_TEXT) from exc
    request.app.state.control.give_back(bot_id)
    await request.app.state.teach.end(user.id, bot_id)        # a teach recording ends with its hold
    if login is not None:
        await request.app.state.vault.tell_bot(user.id, login)
    return _control_state(request, bot_id)
