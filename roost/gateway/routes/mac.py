"""Your Mac's folders over HTTP (Your Mac, grants): add, change and stop sharing a folder.

- ``GET /api/mac/grants?bot_id=``: that bot's grants and the all-bots ones, or all of yours.
- ``POST /api/mac/grants``: share a folder (the keeper checks it first).
- ``PATCH /api/mac/grants/{id}``: rename it, change its access or its read policy.
- ``DELETE /api/mac/grants/{id}``: stop sharing (the keeper learns it at once).
- ``POST /api/mac/pick-folder``: the Mac's own folder window; answers the path or ``null``.
- ``POST /api/mac/activity/{message_id}/undo``: the Undo of a Mac activity line, at once and with no card.

Every route needs a login and every mutation the Origin check. Another user's grant or bot is a
404; a refusal the user can fix is a 422 with a plain sentence. The path is shown to its owner only."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from roost.constants import MAC_LABEL_MAX_CHARS
from roost.desk import DeskUnavailable
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.mac.grant_service import GrantRefused, GrantService
from roost.mac.models import Grant
from roost.mac.undo import MacUndo, UndoRefused
from roost.mac.texts import GRANT_NOT_FOUND_TEXT, MAC_AWAY_TEXT
from roost.talk.store import message_out

mac_router = APIRouter(prefix="/api/mac", tags=["mac"])

_BOT_NOT_FOUND = "Bot not found"
_ACTIVITY_NOT_FOUND = "That line was not found."
_PATH_MAX = 4096
_LABEL_INPUT_MAX = MAC_LABEL_MAX_CHARS * 4


class GrantOut(BaseModel):
    id: str
    bot_id: str | None
    label: str
    path: str
    access: Literal["read", "read_write"]
    read_policy: Literal["ask_each", "ask_session"]
    is_vault: bool
    created_at: str


class GrantIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1, max_length=_PATH_MAX)
    label: str = Field(max_length=_LABEL_INPUT_MAX)
    access: Literal["read", "read_write"]
    read_policy: Literal["ask_each", "ask_session"] = "ask_each"
    bot_id: str | None = None


class GrantPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str | None = Field(default=None, max_length=_LABEL_INPUT_MAX)
    access: Literal["read", "read_write"] | None = None
    read_policy: Literal["ask_each", "ask_session"] | None = None


class PickIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def grant_out(grant: Grant) -> GrantOut:
    return GrantOut(id=grant.id, bot_id=grant.bot_id, label=grant.label, path=grant.path, access=grant.access,
                    read_policy=grant.read_policy, is_vault=grant.is_vault, created_at=grant.created_at)


def _service(request: Request) -> GrantService:
    return request.app.state.grants


def _refused(exc: GrantRefused) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _away() -> HTTPException:
    return HTTPException(status_code=503, detail=MAC_AWAY_TEXT)


@mac_router.get("/grants")
async def list_grants(request: Request, user: CurrentUser, bot_id: str | None = None) -> list[GrantOut]:
    service = _service(request)
    if bot_id is None:
        return [grant_out(g) for g in await service.list_all(user.id)]
    found = await service.for_bot(user.id, bot_id)
    if found is None:
        raise HTTPException(status_code=404, detail=_BOT_NOT_FOUND)
    return [grant_out(g) for g in found]


@mac_router.post("/grants", status_code=201, dependencies=[RequireOrigin])
async def add_grant(body: GrantIn, request: Request, user: CurrentUser) -> GrantOut:
    try:
        grant = await _service(request).add(
            user.id, path=body.path, label=body.label, access=body.access, read_policy=body.read_policy,
            bot_id=body.bot_id,
        )
    except GrantRefused as exc:
        raise _refused(exc) from None
    except DeskUnavailable:
        raise _away() from None
    return grant_out(grant)


@mac_router.patch("/grants/{grant_id}", dependencies=[RequireOrigin])
async def change_grant(grant_id: str, body: GrantPatch, request: Request, user: CurrentUser) -> GrantOut:
    try:
        grant = await _service(request).update(
            user.id, grant_id, label=body.label, access=body.access, read_policy=body.read_policy,
        )
    except GrantRefused as exc:
        raise _refused(exc) from None
    if grant is None:
        raise HTTPException(status_code=404, detail=GRANT_NOT_FOUND_TEXT)
    return grant_out(grant)


@mac_router.delete("/grants/{grant_id}", status_code=204, dependencies=[RequireOrigin])
async def revoke_grant(grant_id: str, request: Request, user: CurrentUser) -> Response:
    if await _service(request).revoke(user.id, grant_id) is None:
        raise HTTPException(status_code=404, detail=GRANT_NOT_FOUND_TEXT)
    return Response(status_code=204)


@mac_router.post("/pick-folder", dependencies=[RequireOrigin])
async def pick_folder(body: PickIn, request: Request, user: CurrentUser) -> dict[str, str | None]:
    try:
        return {"path": await _service(request).pick_folder()}
    except GrantRefused as exc:
        raise _refused(exc) from None
    except DeskUnavailable:
        raise _away() from None


class UndoOut(BaseModel):
    message: dict


@mac_router.post("/activity/{message_id}/undo", dependencies=[RequireOrigin])
async def undo_activity(message_id: str, body: PickIn, request: Request, user: CurrentUser) -> UndoOut:
    undo: MacUndo = request.app.state.mac_undo
    try:
        said = await undo.undo(user.id, message_id)
    except UndoRefused as exc:
        raise HTTPException(status_code=503 if exc.away else 409, detail=str(exc)) from None
    if said is None:
        raise HTTPException(status_code=404, detail=_ACTIVITY_NOT_FOUND)
    return UndoOut(message=message_out(said))
