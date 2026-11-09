"""Origin-header allowlist check for state-changing gateway requests.

Per the shared contract's HTTP API table: every POST/PATCH/DELETE route
and the events WebSocket upgrade must present an ``Origin`` header
matching one of ``config.allowed_origins``, else 403. Session cookies are
already ``SameSite=Strict``, but that alone doesn't cover same-site-but-
different-port requests (the dev Vite server on :5173 talking to the
gateway on :18800), so every mutating route depends on this explicitly
too.
"""

from __future__ import annotations

from fastapi import HTTPException, Request


async def require_origin(request: Request) -> None:
    """Raise 403 unless the request's Origin header is allowlisted.

    A missing header is treated the same as a disallowed one: a direct
    (non-browser) client and a misconfigured deployment both fail closed
    rather than silently being let through.
    """
    config = request.app.state.config
    origin = request.headers.get("origin")
    if origin not in config.allowed_origins:
        raise HTTPException(status_code=403, detail="Origin not allowed")
