"""``GET /api/health`` — unauthenticated liveness probe.

Polled by the gateway container's compose healthcheck
(``docker-compose.yml``) from inside the container itself: no session, no
Origin header, no body. It answers only "the process is up and serving";
it reveals nothing about accounts, bots or the keeper.
"""

from __future__ import annotations

from fastapi import APIRouter

health_router = APIRouter(prefix="/api", tags=["health"])


@health_router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
