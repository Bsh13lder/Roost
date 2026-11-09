"""Skills over HTTP: the user's saved how-tos (docs/plans/2026-10-21-roost-skills.md).

- ``GET /api/skills`` (``?bot_id=`` adds each skill's ``on`` for that bot) and ``POST /api/skills``.
- ``GET``, ``PUT`` (a compare-and-swap on ``base_revision``: 409 with the current copy) and ``DELETE
  /api/skills/{id}``. The user's save clears the *from web content* mark.
- ``PUT /api/bots/{bot_id}/skills/{skill_id}`` ``{on}``: the per-bot switch.
- ``POST /api/skills/import`` ``{skills, bot_id?}``: a template file's ticked skills, marked as outside content.

Every route has ``CurrentUser`` and every write has ``RequireOrigin``. A bot or a skill that is not the user's is a
404, never the object. Refusals are 422 with one plain sentence that never echoes a secret."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import SKILL_BODY_MAX, SKILL_NAME_MAX, SKILL_USE_WHEN_MAX, TEMPLATE_SKILLS_MAX
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.skills.models import Skill, SkillDraft, SkillPatch, plain_error
from roost.skills.service import NoSuchBot, NoSuchSkill, SkillConflict, SkillRefused, SkillService
from roost.skills.template_skills import TemplateSkill
from roost.skills.texts import CONFLICT

skills_router = APIRouter(prefix="/api", tags=["skills"])

SKILL_NOT_FOUND = "Skill not found"
BOT_NOT_FOUND = "Bot not found"
WIRE_SLACK = 2   # a hard wire cap above the friendly limits, which keep their own sentences


class SkillIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(max_length=SKILL_NAME_MAX * WIRE_SLACK)
    use_when: str = Field(max_length=SKILL_USE_WHEN_MAX * WIRE_SLACK)
    body: str = Field(max_length=SKILL_BODY_MAX * WIRE_SLACK)


class SkillSaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str | None = Field(default=None, max_length=SKILL_NAME_MAX * WIRE_SLACK)
    use_when: str | None = Field(default=None, max_length=SKILL_USE_WHEN_MAX * WIRE_SLACK)
    body: str | None = Field(default=None, max_length=SKILL_BODY_MAX * WIRE_SLACK)
    base_revision: int = Field(ge=1)


class ImportIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    skills: tuple[TemplateSkill, ...] = Field(max_length=TEMPLATE_SKILLS_MAX)
    bot_id: str | None = None


class SwitchIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    on: bool


def _service(request: Request) -> SkillService:
    return request.app.state.skills


def skill_out(skill: Skill, on: bool | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": skill.id, "name": skill.name, "use_when": skill.use_when, "body": skill.body, "origin": skill.origin,
        "tainted": skill.tainted, "created_by_bot": skill.created_by_bot, "revision": skill.revision,
        "created_at": skill.created_at, "updated_at": skill.updated_at,
    }
    if on is not None:
        out["on"] = on
    return out


def draft_or_422(model: type[SkillDraft] | type[SkillPatch], fields: dict[str, Any]) -> Any:
    try:
        return model(**fields)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=plain_error(exc)) from None


async def guarded(pending):
    """Await ``pending``, turning the service's answers into status codes."""
    try:
        return await pending
    except NoSuchBot:
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND) from None
    except NoSuchSkill:
        raise HTTPException(status_code=404, detail=SKILL_NOT_FOUND) from None
    except SkillRefused as exc:
        raise HTTPException(status_code=422, detail=exc.text) from None


@skills_router.get("/skills")
async def list_skills(request: Request, user: CurrentUser, bot_id: str | None = None) -> list[dict[str, Any]]:
    service = _service(request)
    if bot_id is None:
        return [skill_out(s) for s in await service.list(user.id)]
    rows = await guarded(service.list_for_bot(user.id, bot_id))
    return [skill_out(row.skill, row.on) for row in rows]


@skills_router.post("/skills", status_code=201, dependencies=[RequireOrigin])
async def add_skill(body: SkillIn, request: Request, user: CurrentUser) -> dict[str, Any]:
    draft = draft_or_422(SkillDraft, body.model_dump())
    return skill_out(await guarded(_service(request).add(user.id, draft)))


@skills_router.post("/skills/import", dependencies=[RequireOrigin])
async def import_skills(body: ImportIn, request: Request, user: CurrentUser) -> dict[str, Any]:
    """The Add its skills? sheet: adds only the ticked skills, marked as outside content; names you have are
    skipped and listed in ``have``."""
    added, have = await guarded(_service(request).import_from_template(user.id, body.skills, body.bot_id))
    return {"added": [skill_out(s) for s in added], "have": list(have)}


@skills_router.get("/skills/{skill_id}")
async def get_skill(skill_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    return skill_out(await guarded(_service(request).get(user.id, skill_id)))


@skills_router.put("/skills/{skill_id}", dependencies=[RequireOrigin])
async def save_skill(skill_id: str, body: SkillSaveIn, request: Request, user: CurrentUser) -> Any:
    patch = draft_or_422(SkillPatch, body.model_dump(exclude={"base_revision"}, exclude_none=True))
    try:
        saved = await guarded(_service(request).save(user.id, skill_id, patch, base_revision=body.base_revision))
    except SkillConflict as exc:
        return JSONResponse(status_code=409, content={"detail": CONFLICT, "current": skill_out(exc.current)})
    return skill_out(saved)


@skills_router.delete("/skills/{skill_id}", status_code=204, dependencies=[RequireOrigin])
async def delete_skill(skill_id: str, request: Request, user: CurrentUser) -> Response:
    await guarded(_service(request).delete(user.id, skill_id))
    return Response(status_code=204)


@skills_router.put("/bots/{bot_id}/skills/{skill_id}", dependencies=[RequireOrigin])
async def switch_skill(bot_id: str, skill_id: str, body: SwitchIn, request: Request,
                       user: CurrentUser) -> dict[str, bool]:
    return {"on": await guarded(_service(request).set_on(user.id, bot_id, skill_id, body.on))}
