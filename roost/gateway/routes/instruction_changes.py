"""The Undo of an "Updated my instructions" line (A2).

- ``POST /api/instruction-changes/{message_id}/undo``: restores the text the change replaced, at once and with no
  card, only while the bot's instructions are still the ones the change wrote (409 otherwise, and 409 once spent).
  Another user's line, or a message that is not such a line, is a 404."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.instruction_proposals.changes import InstructionChanges, UndoRefused
from roost.instruction_proposals.texts import CHANGE_NOT_FOUND
from roost.talk.store import message_out

instruction_changes_router = APIRouter(prefix="/api/instruction-changes", tags=["bots"])


class ChangeUndoOut(BaseModel):
    message: dict


@instruction_changes_router.post("/{message_id}/undo", dependencies=[RequireOrigin])
async def undo_instruction_change(message_id: str, request: Request, user: CurrentUser) -> ChangeUndoOut:
    changes: InstructionChanges = request.app.state.instruction_changes
    try:
        line = await changes.undo(user.id, message_id)
    except UndoRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    if line is None:
        raise HTTPException(status_code=404, detail=CHANGE_NOT_FOUND)
    return ChangeUndoOut(message=message_out(line))
