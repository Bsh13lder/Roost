"""What a bot asks the user, over HTTP: routine proposals and the question book.

- ``GET /api/routine-proposals?state=open``: the open proposals, each with its words, the next fires (local), and
  for a change the field-by-field differences.
- ``GET /api/routine-proposals/{id}``: one proposal in the list's shape, also once decided (its final state).
- ``POST /api/routine-proposals/{id}/approve`` and ``/decline``: the user's decision. Approve is what makes the
  server write the routine; 409 "Try again" when another press already decided it; another user's id is 404.

- ``GET /api/questions?state=open&bot_id=``: the user's questions (all bots when ``bot_id`` is left out, for My turn).
- ``POST /api/questions/{id}/answer`` (``{answer}``) posts the answer as the user's own message and queues a run;
  ``POST /api/questions/{id}/dismiss`` closes it with no message. 409 when it isn't open; another user's id is 404.

Every route has ``CurrentUser`` and every write has ``RequireOrigin``."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from roost.constants import QUESTION_ANSWER_MAX_CHARS

from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.routines.runs import iso
from roost.questions.service import NoSuchQuestion, QuestionClosed, QuestionRefused, QuestionService
from roost.questions.store import Question
from roost.routines.proposals import (
    PROPOSED, NoSuchProposal, ProposalClosed, ProposalRefused, ProposalService, ProposalView,
)
from roost.gateway.routes.standing import PermissionBody
from roost.standing.service import PermissionRefused, parse_permission
from roost.routines.service import Conflict, NoSuchBot, NoSuchRoutine, Refused

routine_asks_router = APIRouter(prefix="/api", tags=["routine-asks"])

PROPOSAL_NOT_FOUND = "Proposal not found"


def _proposals(request: Request) -> ProposalService:
    return request.app.state.proposals


def proposal_out(view: ProposalView) -> dict[str, Any]:
    proposal = view.proposal
    payload = proposal.payload
    return {
        "id": proposal.id, "bot_id": proposal.bot_id, "action": proposal.action, "routine_id": proposal.routine_id,
        "routine_name": view.routine_name, "state": proposal.state,
        "payload": payload.model_dump(mode="json") if payload is not None else None,
        "words": view.words, "next": list(view.next), "diff": list(view.diff),
        "tainted": proposal.tainted, "from_routine": proposal.from_routine,
        "created_at": iso(proposal.created_at),
    }


async def _guarded(pending):
    try:
        return await pending
    except (NoSuchProposal, NoSuchBot, NoSuchRoutine):
        raise HTTPException(status_code=404, detail=PROPOSAL_NOT_FOUND) from None
    except ProposalClosed as exc:
        raise HTTPException(status_code=409, detail=exc.args[0]) from None
    except (ProposalRefused, Refused) as exc:
        raise HTTPException(status_code=422, detail=exc.text) from None
    except Conflict as exc:
        raise HTTPException(status_code=409, detail=exc.text) from None


@routine_asks_router.get("/routine-proposals")
async def list_proposals(request: Request, user: CurrentUser, state: str = "open") -> dict[str, Any]:
    if state != "open":
        raise HTTPException(status_code=422, detail="Only open proposals can be listed.")
    views = await _proposals(request).list_open(user.id)
    return {"proposals": [proposal_out(v) for v in views]}


@routine_asks_router.get("/routine-proposals/{proposal_id}")
async def get_proposal(proposal_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    return proposal_out(await _guarded(_proposals(request).get(user.id, proposal_id)))


class ApproveIn(BaseModel):
    """Optional: the standing permission to store with the routine. Left out: the proposed one as it is; null: none;
    an object: the one the user set on the card."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    permission: PermissionBody | None = None


def _permit(body: ApproveIn | None):
    if body is None or "permission" not in body.model_fields_set:
        return PROPOSED
    if body.permission is None:
        return None
    try:
        return parse_permission(body.permission.model_dump())
    except PermissionRefused as exc:
        raise HTTPException(status_code=422, detail=exc.text) from None


@routine_asks_router.post("/routine-proposals/{proposal_id}/approve", dependencies=[RequireOrigin])
async def approve_proposal(
    proposal_id: str, request: Request, user: CurrentUser, body: ApproveIn | None = None,
) -> dict[str, Any]:
    permit = _permit(body)
    return proposal_out(await _guarded(_proposals(request).approve(user.id, proposal_id, permission=permit)))


@routine_asks_router.post("/routine-proposals/{proposal_id}/decline", dependencies=[RequireOrigin])
async def decline_proposal(proposal_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    return proposal_out(await _guarded(_proposals(request).decline(user.id, proposal_id)))


QUESTION_NOT_FOUND = "Question not found"
_STATES = frozenset({"open", "answered", "dismissed"})


class AnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    answer: str = Field(max_length=QUESTION_ANSWER_MAX_CHARS)


def _questions(request: Request) -> QuestionService:
    return request.app.state.questions


def question_out(question: Question) -> dict[str, Any]:
    return {
        "id": question.id, "bot_id": question.bot_id, "routine_id": question.routine_id,
        "question": question.question, "default_choice": question.default_choice, "why": question.why,
        "answer": question.answer, "tainted": question.tainted, "state": question.state,
        "created_at": iso(question.created_at),
        "answered_at": iso(question.answered_at) if question.answered_at else None,
    }


async def _guarded_question(pending):
    try:
        return await pending
    except NoSuchQuestion:
        raise HTTPException(status_code=404, detail=QUESTION_NOT_FOUND) from None
    except QuestionClosed as exc:
        raise HTTPException(status_code=409, detail=exc.args[0]) from None
    except QuestionRefused as exc:
        raise HTTPException(status_code=422, detail=exc.text) from None


@routine_asks_router.get("/questions")
async def list_questions(
    request: Request, user: CurrentUser, state: str = "open", bot_id: str | None = None,
) -> dict[str, Any]:
    if state not in _STATES:
        raise HTTPException(status_code=422, detail="State must be open, answered or dismissed.")
    found = await _questions(request).list(user.id, state=state, bot_id=bot_id)
    return {"questions": [question_out(q) for q in found]}


@routine_asks_router.post("/questions/{question_id}/answer", dependencies=[RequireOrigin])
async def answer_question(question_id: str, body: AnswerIn, request: Request, user: CurrentUser) -> dict[str, Any]:
    return question_out(await _guarded_question(_questions(request).answer(user.id, question_id, body.answer)))


@routine_asks_router.post("/questions/{question_id}/dismiss", dependencies=[RequireOrigin])
async def dismiss_question(question_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    return question_out(await _guarded_question(_questions(request).dismiss(user.id, question_id)))
