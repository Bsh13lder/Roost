"""The Ask card's buttons over HTTP (approval plan Task 8).

- ``GET /api/approvals``: your open cards, newest first.
- ``GET /api/approvals/{id}?full=1``: one card; ``full`` keeps whole diffs (otherwise a diff is cut at
  ``APPROVAL_DIFF_SHOWN_LINES`` lines).
- ``POST /api/approvals/{id}/answer``: Yes, Yes for this session, No (and, later, the Proposal's buttons).

Every route needs a login and every answer the Origin check. Another user's card id is a 404, a second
answer is a 409 "Already answered.", and an answer that does not fit the card is a 422."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from roost.approvals.models import ApprovalCardOut, BadAnswer, CardClosed, approval_card_out
from roost.approvals.service import ApprovalService
from roost.approvals.texts import CARD_CLOSED_TEXT, CARD_NOT_FOUND_TEXT
from roost.constants import APPROVAL_EDIT_TEXT_MAX, CHOICE_OPTIONS_MAX
from roost.db.connection import db_session
from roost.gateway.deps import CurrentUser, RequireOrigin

approvals_router = APIRouter(prefix="/api/approvals", tags=["approvals"])

_TEXT_MAX = APPROVAL_EDIT_TEXT_MAX


class AnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    answer: Literal["yes", "yes_session", "no", "accept", "decline", "edit", "pick", "own"]
    text: str | None = Field(default=None, max_length=_TEXT_MAX)
    choice: int | None = Field(default=None, ge=0, le=CHOICE_OPTIONS_MAX - 1)


def _service(request: Request) -> ApprovalService:
    return request.app.state.approval_service


@approvals_router.get("")
async def list_approvals(request: Request, user: CurrentUser) -> list[ApprovalCardOut]:
    cards = await _service(request).list_open(user.id)
    routines = await _routines_of(request, user.id, {card.thread_id for card in cards})
    return [approval_card_out(card).model_copy(update={"routine_id": routines.get(card.thread_id)})
            for card in cards]


async def _routines_of(request: Request, user_id: str, thread_ids: set[str]) -> dict[str, str]:
    """The routine whose run log each thread is, so My turn opens the card where it shows (owner, 2026-11-05)."""
    if not thread_ids:
        return {}
    marks = ",".join("?" for _ in thread_ids)
    async with db_session(request.app.state.config) as db:
        rows = await (await db.execute(
            f"SELECT id, thread_id FROM routines WHERE user_id = ? AND thread_id IN ({marks})",
            (user_id, *thread_ids))).fetchall()
    return {row["thread_id"]: row["id"] for row in rows}


@approvals_router.get("/{card_id}")
async def get_approval(card_id: str, request: Request, user: CurrentUser, full: int = 0) -> ApprovalCardOut:
    card = await _service(request).get(user.id, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail=CARD_NOT_FOUND_TEXT)
    return approval_card_out(card, full=bool(full))


@approvals_router.post("/{card_id}/answer", dependencies=[RequireOrigin])
async def answer_approval(card_id: str, body: AnswerIn, request: Request, user: CurrentUser) -> ApprovalCardOut:
    try:
        card = await _service(request).answer(user.id, card_id, body.answer, body.text, body.choice)
    except CardClosed:
        raise HTTPException(status_code=409, detail=CARD_CLOSED_TEXT) from None
    except BadAnswer as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if card is None:
        raise HTTPException(status_code=404, detail=CARD_NOT_FOUND_TEXT)
    return approval_card_out(card)
