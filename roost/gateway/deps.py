"""Shared FastAPI dependency aliases for gateway routers.

Centralizes the two cross-cutting dependencies every Night-1 route
needs — the authenticated user and the origin allowlist check — so
later routers (``routes/bots.py``, ``threads.py``, ``desk.py``,
``events.py``) import one small module instead of reaching into
``roost.gateway.auth`` / ``roost.gateway.origin`` directly.

``roost/gateway/auth.py`` itself doesn't import this module (its routes
predate and bootstrap the session/origin machinery these aliases wrap —
importing deps.py back into auth.py would be circular), so it still uses
``Depends(get_current_user)`` / ``Depends(require_origin)`` inline.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from roost.gateway.auth import User, get_current_user
from roost.gateway.origin import require_origin

# `async def handler(user: CurrentUser): ...` resolves to the logged-in User.
CurrentUser = Annotated[User, Depends(get_current_user)]

# `@router.post(..., dependencies=[RequireOrigin])` enforces the Origin
# allowlist on a mutating route.
RequireOrigin = Depends(require_origin)
