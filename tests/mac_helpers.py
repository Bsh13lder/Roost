"""Helpers for the gateway-side Mac tests (not a test module): grant values and a keeper switch."""

from __future__ import annotations

import httpx

from roost.mac.models import Grant

BOT_A = "11111111-1111-4111-8111-111111111111"
GRANT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def grant(root: str, *, grant_id: str = GRANT_ID, access: str = "read_write", bot_id: str | None = None,
          label: str = "MySpace", user_id: str = "u1", read_policy: str = "ask_each", is_vault: bool = False) -> Grant:
    return Grant(id=grant_id, user_id=user_id, bot_id=bot_id, path=root, label=label, access=access,
                 read_policy=read_policy, is_vault=is_vault, created_at="2026-10-22T00:00:00+00:00", revoked_at=None)


class SwitchTransport(httpx.AsyncBaseTransport):
    """Sends every request to whichever keeper app (an ASGI transport) is current."""

    def __init__(self, current: httpx.AsyncBaseTransport) -> None:
        self.current = current

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self.current.handle_async_request(request)
