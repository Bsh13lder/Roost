"""FastAPI dependency gating every keeper endpoint: an HMAC-signed request
or a 401, nothing in between.

Reads the request body once via ``await request.body()`` — Starlette
caches the raw bytes after the first read, so the route handler's own
later parsing of the same body (for the 422-on-unknown-fields check in
``roost/keeper/app.py``) sees the identical bytes without re-consuming
the stream.
"""

from __future__ import annotations

import time

from fastapi import HTTPException, Request

from roost.desk.signing import verify

_UNAUTHORIZED_DETAIL = "missing or invalid request signature"


async def require_signed_body(request: Request) -> bytes:
    body = await request.body()
    config = request.app.state.config
    nonce_cache = request.app.state.nonce_cache

    ok = verify(
        config.keeper_secret,
        request.method,
        request.url.path,
        body,
        request.headers,
        now=int(time.time()),
        seen=nonce_cache,
    )
    if not ok:
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED_DETAIL)
    return body
