"""Standing permissions over HTTP (docs/plans/2026-10-23-roost-full-computer.md Step 2).

- ``GET /api/routines/{id}/permissions``: the routine's live permissions ("Let it post on x.com up to 1 a day until
  …"), each with how many it has used today (local).
- ``POST`` the same path: the owner's own click makes one (``RequireOrigin``); 422 with one plain sentence for a
  bad site, action, count or date, or a routine that already holds the most.
- ``DELETE /api/routines/{id}/permissions/{permission_id}``: Revoke, at once (204).

Every route has ``CurrentUser``; a routine or permission that is not the user's is 404, never the object."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.standing.constants import STANDING_HOST_MAX
from roost.standing.models import Permission
from roost.standing.service import NoSuchPermission, PermissionRefused, PermissionRoutineNotFound, PermissionService

standing_router = APIRouter(prefix="/api", tags=["standing"])

ROUTINE_NOT_FOUND = "Routine not found"
PERMISSION_NOT_FOUND = "Permission not found"
_WIRE_TEXT_MAX = 32


class PermissionBody(BaseModel):
    """Loose types on the wire, so ``PermissionService`` answers each mistake with its own sentence."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str = Field(max_length=STANDING_HOST_MAX * 2)
    action: str = Field(max_length=_WIRE_TEXT_MAX)
    max_per_day: int
    until: str = Field(max_length=_WIRE_TEXT_MAX)


def permission_out(permission: Permission, today: str) -> dict[str, Any]:
    return {
        "id": permission.id, "routine_id": permission.routine_id, "host": permission.host,
        "action": permission.action, "max_per_day": permission.max_per_day, "until": permission.until,
        "used_today": permission.used_on(today), "created_at": permission.created_at,
    }


def _service(request: Request) -> PermissionService:
    return request.app.state.standing


async def _own_routine(request: Request, user_id: str, routine_id: str) -> None:
    if await request.app.state.routine_store.get(user_id, routine_id) is None:
        raise HTTPException(status_code=404, detail=ROUTINE_NOT_FOUND)


@standing_router.get("/routines/{routine_id}/permissions")
async def list_permissions(routine_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    await _own_routine(request, user.id, routine_id)
    service = _service(request)
    today = service.today()
    return {"permissions": [permission_out(p, today) for p in await service.list(user.id, routine_id)]}


@standing_router.post("/routines/{routine_id}/permissions", status_code=201, dependencies=[RequireOrigin])
async def add_permission(routine_id: str, body: PermissionBody, request: Request, user: CurrentUser) -> dict[str, Any]:
    await _own_routine(request, user.id, routine_id)
    service = _service(request)
    try:
        made = await service.add(user.id, routine_id, body.model_dump())
    except PermissionRefused as exc:
        raise HTTPException(status_code=422, detail=exc.text) from None
    except PermissionRoutineNotFound:
        raise HTTPException(status_code=404, detail=ROUTINE_NOT_FOUND) from None
    return permission_out(made, service.today())


@standing_router.delete("/routines/{routine_id}/permissions/{permission_id}", status_code=204,
                        dependencies=[RequireOrigin])
async def revoke_permission(routine_id: str, permission_id: str, request: Request, user: CurrentUser) -> Response:
    await _own_routine(request, user.id, routine_id)
    try:
        await _service(request).revoke(user.id, routine_id, permission_id)
    except NoSuchPermission:
        raise HTTPException(status_code=404, detail=PERMISSION_NOT_FOUND) from None
    return Response(status_code=204)
