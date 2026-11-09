"""``GET /api/my-turn``: everything waiting on you in one answer (the phone's My turn, one round trip).

The answer holds the five lists the web's My turn reads, each in its own route's shape and limited to bots still on
the team: ``stuck`` (``GET /api/stuck``), ``routine_proposals`` (``GET /api/routine-proposals``),
``skill_proposals`` (``GET /api/skill-proposals``), ``key_requests`` (``GET /api/connector-requests``) and
``questions`` (``GET /api/questions``); then ``rows`` (``{kind, id, bot_id, thread_id, panel, text, created_at}``,
the lines My turn draws, in the web's words and order, ``roost/my_turn.py``) and ``count``. Every list is read with
the signed-in user's id, so another user's items never appear."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from roost.gateway.deps import CurrentUser
from roost.gateway.routes.connectors import request_out
from roost.gateway.routes.routine_asks import proposal_out as routine_proposal_out
from roost.gateway.routes.routine_asks import question_out
from roost.gateway.routes.skill_proposals import proposal_out as skill_proposal_out
from roost.my_turn import MyTurnLists, my_turn_rows
from roost.stuck.models import stuck_card_out

my_turn_router = APIRouter(prefix="/api", tags=["my-turn"])


async def _lists(state: Any, user_id: str, names: dict[str, str]) -> MyTurnLists:
    def on_team(items: list[Any]) -> list[Any]:
        return [item for item in items if item.bot_id in names]

    questions = await state.questions.list(user_id, state="open", bot_id=None)
    return MyTurnLists(
        stuck=on_team(list(await state.stuck_service.list_open(user_id))),
        routine_proposals=[routine_proposal_out(v) for v in await state.proposals.list_open(user_id)
                           if v.proposal.bot_id in names],
        skill_proposals=[skill_proposal_out(v) for v in await state.skill_proposals.list_open(user_id)
                         if v.proposal.bot_id in names],
        key_requests=[request_out(r) for r in on_team(list(await state.connector_requests.store.list_open(user_id)))],
        questions=[question_out(q) for q in on_team(list(questions))],
    )


@my_turn_router.get("/my-turn")
async def my_turn(request: Request, user: CurrentUser) -> dict[str, Any]:
    state = request.app.state
    names = {bot.id: bot.name for bot in await state.bots.list(user.id)}
    lists = await _lists(state, user.id, names)
    rows = my_turn_rows(lists, names)
    return {
        "stuck": [stuck_card_out(card).model_dump(mode="json") for card in lists.stuck],
        "routine_proposals": list(lists.routine_proposals), "skill_proposals": list(lists.skill_proposals),
        "key_requests": list(lists.key_requests), "questions": list(lists.questions),
        "rows": rows, "count": len(rows),
    }
