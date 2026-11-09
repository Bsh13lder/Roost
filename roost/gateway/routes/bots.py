"""Bots HTTP API — ``GET/POST /api/bots``, ``GET/PATCH/DELETE
/api/bots/{bot_id}`` (see the contract's HTTP API table).

Every route reads ``BotStore``/``ActivityBoard`` off
``request.app.state`` (set by ``create_app``) rather than a module-level
instance — the same per-app-instance pattern ``roost/gateway/auth.py``
uses for its rate limiters, so two ``create_app()`` calls (e.g. two
tests) never share bots.

Validation lives here, at the HTTP boundary: pydantic enforces the
contract's exact field shapes (name pattern, hex color, length caps)
before anything reaches ``BotStore``, which accepts already-trusted
``BotDraft``/``BotPatch`` dataclasses.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from roost.approvals.models import ApprovalMode, BotApproval, Topic
from roost.bots.instruction_sections import structure_instructions
from roost.bots.limits import fits_on_one_line
from roost.bots.models import BotStatus, Avatar, AvatarBadge, AvatarScreen, AvatarShape, BotDraft, BotPatch, BotRole, DuplicateBotName
from roost.bots.service import bot_out
from roost.constants import (
    APPROVAL_TOPICS,
    AVATAR_COLOR_PATTERN as _COLOR_PATTERN,
    BOT_NAME_PATTERN as _NAME_PATTERN,
    COMPUTER_KINDS,
    DEFAULT_ROBOT_SCREEN,
    MAX_BOT_GROUP_LENGTH,
    MAX_BOT_INSTRUCTIONS_LENGTH,
)
from roost.desk import DeskUnavailable
from roost.llm.registry import BOT_MODELS, EFFORTS, pickable_model_ids
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.gateway.activity import bot_activity

logger = logging.getLogger(__name__)


class AvatarIn(BaseModel):
    shape: AvatarShape            # a Lensbot, or an old ghost, head or bird shape (still accepted, drawn as a Lensbot)
    color: str = Field(pattern=_COLOR_PATTERN)
    badge: AvatarBadge = "none"   # old clients send one; S1 writes "none" (badges are not drawn any more)
    screen: AvatarScreen = DEFAULT_ROBOT_SCREEN  # the robot screen's signal style; a client that sends none gets the default
    role: BotRole | None = None   # the job's emblem (avatars v7); none counts as general

    def to_avatar(self) -> Avatar:
        return Avatar(shape=self.shape, color=self.color, badge=self.badge, screen=self.screen, role=self.role)


class BotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40, pattern=_NAME_PATTERN)
    job: str = Field(min_length=1, max_length=200)
    instructions: str = Field(default="", max_length=MAX_BOT_INSTRUCTIONS_LENGTH)
    avatar: AvatarIn
    template_id: str | None = Field(default=None, max_length=40)

    @field_validator("name", "job")
    @classmethod
    def _one_line(cls, value: str) -> str:
        if not fits_on_one_line(value):
            raise ValueError("must fit on one line")
        return value


class BotUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40, pattern=_NAME_PATTERN)
    job: str | None = Field(default=None, min_length=1, max_length=200)
    instructions: str | None = Field(default=None, max_length=MAX_BOT_INSTRUCTIONS_LENGTH)
    avatar: AvatarIn | None = None
    group: str | None = Field(default=None, max_length=MAX_BOT_GROUP_LENGTH)
    computer: Literal[*COMPUTER_KINDS] | None = None   # absent or null keeps it

    @field_validator("name", "job", "group")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        if value is not None and not fits_on_one_line(value):
            raise ValueError("must fit on one line")
        return value


def _group_patch(body: BotUpdate) -> str | None:
    """Absent keeps the label (None); null or blank clears it (""); text sets it, stripped."""
    if "group" not in body.model_fields_set:
        return None
    return (body.group or "").strip()


class NotifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notify: bool


class ApprovalIn(BaseModel):
    """A bot's approval mode and the topics it always asks about (posting is locked on and never stored)."""
    model_config = ConfigDict(extra="forbid")
    mode: ApprovalMode
    ask_topics: list[Topic] = Field(default_factory=list, max_length=len(APPROVAL_TOPICS))
    auto_review: StrictBool | None = None   # Full auto; left out keeps the stored value


class PinIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pinned: StrictBool


class ModelIn(BaseModel):
    """The bot's model and effort; null for either means the default."""
    model_config = ConfigDict(extra="forbid")
    model: str | None = Field(default=None, max_length=100)
    effort: Literal[*EFFORTS] | None = None


bots_router = APIRouter(prefix="/api/bots", tags=["bots"])


async def _activity(request: Request, user_id: str, bot, board) -> str | None:
    """What the bot is doing now (``roost/gateway/activity.py``)."""
    return await bot_activity(request.app.state, user_id, bot)


@bots_router.get("")
async def list_bots(request: Request, user: CurrentUser):
    store = request.app.state.bots
    board = request.app.state.activity_board
    bots = await store.list(user.id)
    return [bot_out(bot, await _activity(request, user.id, bot, board)) for bot in bots]


@bots_router.post("", status_code=201, dependencies=[RequireOrigin])
async def create_bot(body: BotCreate, request: Request, user: CurrentUser):
    store = request.app.state.bots
    draft = BotDraft(
        name=body.name,
        job=body.job,
        # The New bot form's text is stored in the five sections (replies track); a PATCH stores what you typed.
        instructions=structure_instructions(body.instructions, name=body.name, job=body.job),
        avatar=body.avatar.to_avatar(),
        template_id=body.template_id,
    )
    try:
        bot = await store.create(user.id, draft)
    except DuplicateBotName as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    out = bot_out(bot, None)
    # The live store knows only the bots in its connect-time snapshot: this
    # frame adds the new one, so its status updates reach the web face.
    await request.app.state.events.publish(user.id, {"type": "bot_updated", "bot": out})
    return out


@bots_router.get("/{bot_id}")
async def get_bot(bot_id: str, request: Request, user: CurrentUser):
    store = request.app.state.bots
    board = request.app.state.activity_board
    bot = await store.get(user.id, bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot_out(bot, await _activity(request, user.id, bot, board))


@bots_router.patch("/{bot_id}", dependencies=[RequireOrigin])
async def update_bot(bot_id: str, body: BotUpdate, request: Request, user: CurrentUser):
    store = request.app.state.bots
    board = request.app.state.activity_board
    patch = BotPatch(
        name=body.name,
        job=body.job,
        instructions=body.instructions,
        avatar=body.avatar.to_avatar() if body.avatar is not None else None,
        group=_group_patch(body),
        computer=body.computer,
    )
    try:
        bot = await store.update(user.id, bot_id, patch)
    except DuplicateBotName as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    out = bot_out(bot, board.get(bot.id))
    # Every view (Home's list, a chat header, the profile) sees a rename or a new look live.
    await request.app.state.events.publish(user.id, {"type": "bot_updated", "bot": out})
    return out


@bots_router.put("/{bot_id}/notify", dependencies=[RequireOrigin])
async def set_bot_notify(bot_id: str, body: NotifyIn, request: Request, user: CurrentUser):
    bot = await request.app.state.bots.set_notify(user.id, bot_id, body.notify)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    out = bot_out(bot, request.app.state.activity_board.get(bot.id))
    await request.app.state.events.publish(user.id, {"type": "bot_updated", "bot": out})
    return out


@bots_router.put("/{bot_id}/approval", dependencies=[RequireOrigin])
async def set_bot_approval(bot_id: str, body: ApprovalIn, request: Request, user: CurrentUser):
    approval = BotApproval(body.mode, frozenset(body.ask_topics))
    bot = await request.app.state.bots.set_approval(user.id, bot_id, approval, auto_review=body.auto_review)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    out = bot_out(bot, request.app.state.activity_board.get(bot.id))
    await request.app.state.events.publish(user.id, {"type": "bot_updated", "bot": out})
    return out


@bots_router.put("/{bot_id}/pin", dependencies=[RequireOrigin])
async def set_bot_pin(bot_id: str, body: PinIn, request: Request, user: CurrentUser):
    bot = await request.app.state.bots.set_pinned(user.id, bot_id, body.pinned)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    out = bot_out(bot, request.app.state.activity_board.get(bot.id))
    await request.app.state.events.publish(user.id, {"type": "bot_updated", "bot": out})
    return out


@bots_router.put("/{bot_id}/model", dependencies=[RequireOrigin])
async def set_bot_model(bot_id: str, body: ModelIn, request: Request, user: CurrentUser):
    state = request.app.state
    labels = await state.seen_models.labels()
    if body.model is not None and body.model not in pickable_model_ids(frozenset(labels)):
        raise HTTPException(status_code=422, detail="That model isn't available.")
    bot = await state.bots.set_model(user.id, bot_id, body.model, body.effort)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    out = bot_out(bot, state.activity_board.get(bot.id), labels)
    await state.events.publish(user.id, {"type": "bot_updated", "bot": out})
    return out


@bots_router.delete("/{bot_id}", status_code=204, dependencies=[RequireOrigin])
async def delete_bot(bot_id: str, request: Request, user: CurrentUser) -> None:
    """Deletes the bot, then retires its desk (spec vocabulary: "Retire
    this bot"). The DB row is the source of truth for whether the bot
    still exists, so it's deleted first; the desk (browser + workspace
    container + on-disk desk dir) is then retired best-effort -- a
    keeper that's unreachable must not turn an otherwise-successful
    delete into an error the user can't act on.

    Final review, finding 5: a turn still ``on_it`` for this bot is
    cancelled BEFORE the desk is retired, so it can't race the retire
    (or, worse, relaunch a browser for a bot that's already gone) --
    and the desk is forgotten from ``DeskFactory``'s cache right after,
    so nothing in this process goes on reusing it either.

    Final review, finding 6: publishes the contract's ``bot_removed``
    frame so a live client drops the bot from its sidebar immediately,
    instead of only after a full reload.
    """
    store = request.app.state.bots
    bot = await store.get(user.id, bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    if bot.is_primary:
        raise HTTPException(status_code=409, detail=f"Make another bot the main bot before you retire {bot.name}.")
    # D-E: a coordinator's rooms get a new coordinator (and keep their
    # thread) before the bot row — and its cascades — go away.
    await request.app.state.room_service.on_bot_retiring(user.id, bot_id)
    deleted = await store.delete(user.id, bot_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Bot not found")

    await request.app.state.turns.cancel(bot_id)

    desks = request.app.state.desks
    for kind in COMPUTER_KINDS:        # both kinds: the Brave profile and the Linux computer
        try:
            await desks.for_bot(bot_id, kind).retire()
        except DeskUnavailable as exc:
            # Fix round 1, finding 2: best-effort must not mean silent. The DB
            # row (the source of truth for "does this bot exist") is already
            # gone, so the delete still succeeds -- but a keeper that's
            # unreachable here leaves that bot's Brave profile and workspace
            # container running with nothing to show for it. Logging gives an
            # operator a trail to find and manually clean up the leak.
            logger.warning("desk retire failed for bot %s: %s", bot_id, exc)
    desks.forget(bot_id)
    request.app.state.control.forget(bot_id)

    await request.app.state.events.publish(user.id, {"type": "bot_removed", "bot_id": bot_id})
