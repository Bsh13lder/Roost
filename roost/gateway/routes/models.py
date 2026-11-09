"""``GET /api/models`` (what a bot can be switched to) and the dismissal of the new-model notice."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.llm.registry import BOT_MODELS, WORKER, DEFAULT_BOT_MODEL, DEFAULT_EFFORT, EFFORTS

models_router = APIRouter(prefix="/api/models", tags=["models"])

_NEW_LINE = "new"   # a model the daily check found has no family line of its own


@models_router.get("")
async def list_models(request: Request, user: CurrentUser):
    store = request.app.state.seen_models
    seen = await store.labels()
    known = {choice.id for choice in BOT_MODELS}
    choices = [{"id": c.id, "label": c.label, "line": c.line, "new": False} for c in BOT_MODELS]
    choices += [{"id": mid, "label": label, "line": _NEW_LINE, "new": True}
                for mid, label in seen.items() if mid not in known and mid != WORKER]
    notice = await store.newest_undismissed(user.id)
    return {
        "choices": choices,
        "efforts": list(EFFORTS),
        "default_model": DEFAULT_BOT_MODEL,
        "default_effort": DEFAULT_EFFORT,
        "notice": None if notice is None else {"id": notice[0], "label": notice[1]},
    }


@models_router.post("/notice/{model_id}/dismiss", status_code=204, dependencies=[RequireOrigin])
async def dismiss_notice(model_id: str, request: Request, user: CurrentUser) -> Response:
    await request.app.state.seen_models.dismiss(user.id, model_id)
    return Response(status_code=204)
