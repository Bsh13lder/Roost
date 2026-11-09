"""The 'Update my instructions?' card over HTTP (docs/plans/2026-10-22-roost-replies.md, part 3).

- ``GET /api/instruction-proposals?state=open`` and ``GET /api/instruction-proposals/{id}``.
- ``POST /api/instruction-proposals/{id}/accept`` with ``{text?}``: the server writes the bot's instructions (your
  edit when you send one, else the card's) and publishes ``bot_updated`` like ``PATCH /api/bots/{id}``. 409 when it
  was already decided, 422 with a plain sentence when the instructions changed since the card was made.
- ``POST /api/instruction-proposals/{id}/decline``.

Every route has ``CurrentUser`` and every write ``RequireOrigin``. Another user's card is a 404."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from roost.bots.service import bot_out
from roost.constants import MAX_BOT_INSTRUCTIONS_LENGTH
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.instruction_proposals.models import ProposalView
from roost.instruction_proposals.service import (
    InstructionProposalClosed, InstructionProposalRefused, InstructionProposalService, NoSuchInstructionProposal,
)
from roost.instruction_proposals.texts import PROPOSAL_NOT_FOUND

instruction_proposals_router = APIRouter(prefix="/api", tags=["bots"])


class AcceptIn(BaseModel):
    """Accept as it is, or with your own edit of the new instructions."""
    model_config = ConfigDict(extra="forbid")
    text: str | None = Field(default=None, min_length=1, max_length=MAX_BOT_INSTRUCTIONS_LENGTH)


def _service(request: Request) -> InstructionProposalService:
    return request.app.state.instruction_proposals


def proposal_out(view: ProposalView) -> dict[str, Any]:
    p = view.proposal
    return {
        "id": p.id, "bot_id": p.bot_id, "before": p.payload.before, "after": p.payload.after, "why": p.payload.why,
        "diff": list(view.diff), "stale": view.stale, "tainted": p.tainted, "from_routine": p.from_routine,
        "state": p.state, "created_at": p.created_at, "decided_at": p.decided_at,
    }


async def _guarded(pending):
    try:
        return await pending
    except NoSuchInstructionProposal:
        raise HTTPException(status_code=404, detail=PROPOSAL_NOT_FOUND) from None
    except InstructionProposalClosed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except InstructionProposalRefused as exc:
        raise HTTPException(status_code=422, detail=exc.text) from None


@instruction_proposals_router.get("/instruction-proposals")
async def list_instruction_proposals(request: Request, user: CurrentUser,
                                     state: Literal["open"] = "open") -> list[dict[str, Any]]:
    return [proposal_out(v) for v in await _service(request).list_open(user.id)]


@instruction_proposals_router.get("/instruction-proposals/{proposal_id}")
async def get_instruction_proposal(proposal_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    return proposal_out(await _guarded(_service(request).get(user.id, proposal_id)))


@instruction_proposals_router.post("/instruction-proposals/{proposal_id}/accept", dependencies=[RequireOrigin])
async def accept_instruction_proposal(proposal_id: str, request: Request, user: CurrentUser,
                                      body: AcceptIn | None = None) -> dict[str, Any]:
    text = body.text if body is not None else None
    view, bot = await _guarded(_service(request).accept(user.id, proposal_id, text))
    out = bot_out(bot, request.app.state.activity_board.get(bot.id))
    await request.app.state.events.publish(user.id, {"type": "bot_updated", "bot": out})
    return proposal_out(view)


@instruction_proposals_router.post("/instruction-proposals/{proposal_id}/decline", dependencies=[RequireOrigin])
async def decline_instruction_proposal(proposal_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    return proposal_out(await _guarded(_service(request).decline(user.id, proposal_id)))
