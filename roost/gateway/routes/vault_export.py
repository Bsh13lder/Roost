"""The Obsidian export over HTTP (obsidian track, part 3).

``GET /api/vault-export`` — the settings, the folders the user may choose (live ``read_write`` grants), the
projects switched on and the last result. ``PUT /api/vault-export`` — choose the folder (or none) and
"Export journals". ``POST /api/vault-export/run`` — Export now. ``PUT /api/projects/{id}/vault-export`` —
the project's "Export to my vault" switch (off by default). Another user's project or folder is a 404 / 422."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from roost.constants import MAX_RECORD_ID_LENGTH
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.mac.models import Grant
from roost.vault_export.store import ExportResult, ExportSettings

vault_export_router = APIRouter(tags=["vault-export"])

NO_FOLDER_TEXT = "Choose one of your shared folders that Roost may write to."
NO_PROJECT_TEXT = "Project not found"


class VaultExportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grant_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)
    journals: bool = False


class ProjectExportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on: bool


def _grant_out(grant: Grant) -> dict[str, Any]:
    return {"id": grant.id, "label": grant.label, "bot_id": grant.bot_id, "is_vault": grant.is_vault}


def result_out(result: ExportResult) -> dict[str, Any]:
    return {"result": result.code, "written": result.written, "conflicts": result.conflicts, "failed": result.failed}


async def _settings_out(request: Request, user_id: str, settings: ExportSettings) -> dict[str, Any]:
    grants = await request.app.state.grants.list_all(user_id)
    return {
        "grant_id": settings.grant_id, "journals": settings.journals,
        "grants": [_grant_out(g) for g in grants if g.access == "read_write"],
        "projects": list(await request.app.state.vault_export_store.exported_projects(user_id)),
        "last": {"result": settings.last_result, "written": settings.last_written,
                 "conflicts": settings.last_conflicts, "at": settings.last_export_at},
    }


@vault_export_router.get("/api/vault-export")
async def get_vault_export(request: Request, user: CurrentUser):
    store = request.app.state.vault_export_store
    return await _settings_out(request, user.id, await store.settings(user.id))


@vault_export_router.put("/api/vault-export", dependencies=[RequireOrigin])
async def put_vault_export(body: VaultExportIn, request: Request, user: CurrentUser):
    if body.grant_id is not None:
        grant = await request.app.state.grant_store.get(user.id, body.grant_id)
        if grant is None or grant.access != "read_write":
            raise HTTPException(status_code=422, detail=NO_FOLDER_TEXT)
    settings = await request.app.state.vault_export_store.save_settings(
        user.id, grant_id=body.grant_id, journals=body.journals)
    request.app.state.vault_export_scheduler.poke(user.id)
    return await _settings_out(request, user.id, settings)


@vault_export_router.post("/api/vault-export/run", dependencies=[RequireOrigin])
async def run_vault_export(request: Request, user: CurrentUser):
    return result_out(await request.app.state.vault_exporter.run(user.id))


@vault_export_router.put("/api/projects/{project_id}/vault-export", dependencies=[RequireOrigin])
async def put_project_export(project_id: str, body: ProjectExportIn, request: Request, user: CurrentUser):
    if not await request.app.state.vault_export_store.set_project(user.id, project_id, body.on):
        raise HTTPException(status_code=404, detail=NO_PROJECT_TEXT)
    if body.on:
        request.app.state.vault_export_scheduler.poke(user.id)
    return {"project_id": project_id, "on": body.on}
