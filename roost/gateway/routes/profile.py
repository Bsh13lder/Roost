"""A bot profile's data (S1.9): its Links tab and its Documents tab ("Made by").
Both read only this user's rows; another user's bot id is 404."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from roost.constants import LINK_SCAN_MESSAGES, LINKS_LIMIT, MADE_LIST_LIMIT
from roost.documents.format import document_out
from roost.gateway.deps import CurrentUser
from roost.money.summary import expense_row
from roost.notes.format import note_summary_out
from roost.talk.links import collect_links, link_out
from roost.tasks.format import task_out

profile_router = APIRouter(prefix="/api/bots", tags=["profile"])


async def _owned_or_404(request: Request, user_id: str, bot_id: str) -> None:
    if await request.app.state.bots.get(user_id, bot_id) is None:
        raise HTTPException(status_code=404, detail="Bot not found")


@profile_router.get("/{bot_id}/links")
async def bot_links(bot_id: str, request: Request, user: CurrentUser):
    await _owned_or_404(request, user.id, bot_id)
    messages = await request.app.state.talk.list_bot_messages(user.id, bot_id, LINK_SCAN_MESSAGES)
    return [link_out(link) for link in collect_links(messages, LINKS_LIMIT)]


@profile_router.get("/{bot_id}/made")
async def bot_made(bot_id: str, request: Request, user: CurrentUser):
    await _owned_or_404(request, user.id, bot_id)
    state = request.app.state
    tasks = await state.tasks.made_by(user.id, bot_id, MADE_LIST_LIMIT)
    expenses = await state.money.made_by(user.id, bot_id, MADE_LIST_LIMIT)
    notes = await state.notes.made_by(user.id, bot_id, MADE_LIST_LIMIT)
    documents = await state.documents.made_by(user.id, bot_id, MADE_LIST_LIMIT)
    return {"tasks": [task_out(t) for t in tasks], "expenses": [expense_row(e, c) for e, c in expenses],
            "notes": [note_summary_out(n) for n in notes], "documents": [document_out(d) for d in documents]}
