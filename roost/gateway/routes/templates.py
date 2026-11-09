"""Templates (S1.7). ``GET /api/templates`` lists the New bot screen's
"Start from" templates; ``POST /api/templates/check`` reads a shared bot file
for "From a file"; ``GET /api/bots/{id}/template`` is Share as Template.
Reading a template or checking a file creates nothing. Skills: a shared file
carries the skills on for that bot, and check lists a file's skills with
``have`` (the user already has that name); they are added only through
``POST /api/skills/import`` (the Add its skills? sheet)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from roost.bots.look import avatar_dict
from roost.bots.models import Avatar
from roost.bots.template_file import (
    SecretInTemplate, TemplateFileError, read_template_file, template_file_for, template_filename,
)
from roost.bots.templates import TEMPLATES, template_out
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.skills.template_skills import import_plan, skills_for_template

templates_router = APIRouter(prefix="/api", tags=["templates"])


class TemplateCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file: Any


@templates_router.get("/templates")
async def list_templates(user: CurrentUser):
    return [template_out(template) for template in TEMPLATES.values()]


@templates_router.post("/templates/check", dependencies=[RequireOrigin])
async def check_template(body: TemplateCheckIn, request: Request, user: CurrentUser):
    """From a file (S1.7): checks it and returns the form's values. Creates nothing."""
    try:
        parsed = read_template_file(body.file)
    except TemplateFileError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    look = Avatar(shape=parsed.avatar.shape, color=parsed.avatar.color, badge="none", screen=parsed.avatar.screen,
                  role=parsed.avatar.role)
    have = [s.name for s in await request.app.state.skills.list(user.id)]
    skills = [{"name": line.skill.name, "use_when": line.skill.use_when, "body": line.skill.steps,
               "have": line.state == "have"} for line in import_plan(have, parsed.skills)]
    return {"name": parsed.name, "job": parsed.job, "instructions": parsed.instructions, "avatar": avatar_dict(look),
            "skills": skills}


@templates_router.get("/bots/{bot_id}/template")
async def export_template(bot_id: str, request: Request, user: CurrentUser) -> JSONResponse:
    """Share as Template (S1.7): the bot's file, never cached; 422 when a field looks like a secret."""
    bot = await request.app.state.bots.get(user.id, bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    on = await request.app.state.skills.on_for_bot(user.id, bot.id)
    try:
        file = template_file_for(bot, skills_for_template(on))
    except SecretInTemplate as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    disposition = f'attachment; filename="{template_filename(bot.name)}"'
    return JSONResponse(content=file.model_dump(), headers={"Content-Disposition": disposition, "Cache-Control": "no-store"})
