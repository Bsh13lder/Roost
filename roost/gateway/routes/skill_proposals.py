"""Skill proposals over HTTP: the card's Save skill and Not now (Skills design §3).

- ``GET /api/skill-proposals?state=open`` and ``GET /api/skill-proposals/{id}``.
- ``POST /api/skill-proposals/{id}/save``: the server writes the skill; 409 when it was already decided, 422 with a
  plain sentence when the skill changed since (``STALE``), the name is taken or the list is full.
- ``POST /api/skill-proposals/{id}/decline``.

Every route has ``CurrentUser`` and every write ``RequireOrigin``. Another user's proposal is a 404."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request

from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.skills.proposals import (
    NoSuchSkillProposal, SkillProposalClosed, SkillProposalRefused, SkillProposalService, SkillProposalView,
)

skill_proposals_router = APIRouter(prefix="/api", tags=["skills"])

PROPOSAL_NOT_FOUND = "Skill proposal not found"


def _service(request: Request) -> SkillProposalService:
    return request.app.state.skill_proposals


def proposal_out(view: SkillProposalView) -> dict[str, Any]:
    p = view.proposal
    return {
        "id": p.id, "bot_id": p.bot_id, "skill_id": p.skill_id, "action": p.action,
        "payload": {"name": p.payload.name, "use_when": p.payload.use_when, "body": p.payload.body},
        "skill_name": view.skill_name, "diff": list(view.diff), "tainted": p.tainted,
        "from_routine": p.from_routine, "state": p.state, "created_at": p.created_at,
    }


async def _guarded(pending) -> SkillProposalView:
    try:
        return await pending
    except NoSuchSkillProposal:
        raise HTTPException(status_code=404, detail=PROPOSAL_NOT_FOUND) from None
    except SkillProposalClosed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except SkillProposalRefused as exc:
        raise HTTPException(status_code=422, detail=exc.text) from None


@skill_proposals_router.get("/skill-proposals")
async def list_skill_proposals(request: Request, user: CurrentUser,
                               state: Literal["open"] = "open") -> list[dict[str, Any]]:
    return [proposal_out(v) for v in await _service(request).list_open(user.id)]


@skill_proposals_router.get("/skill-proposals/{proposal_id}")
async def get_skill_proposal(proposal_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    return proposal_out(await _guarded(_service(request).get(user.id, proposal_id)))


@skill_proposals_router.post("/skill-proposals/{proposal_id}/save", dependencies=[RequireOrigin])
async def save_skill_proposal(proposal_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    return proposal_out(await _guarded(_service(request).save(user.id, proposal_id)))


@skill_proposals_router.post("/skill-proposals/{proposal_id}/decline", dependencies=[RequireOrigin])
async def decline_skill_proposal(proposal_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    return proposal_out(await _guarded(_service(request).decline(user.id, proposal_id)))
