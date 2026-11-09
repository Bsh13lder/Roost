"""Vault: site logins over HTTP (Computers 2.0, C2, Task 14).

- ``GET /api/bots/{id}/site-logins``: the accounts you said this bot is signed in with, newest first.
- ``DELETE /api/bots/{id}/site-logins/{login_id}``: Forget one (that bot and site only).
- ``POST /api/bots/{id}/site-logins/{login_id}/sign-out``: Sign out (the Sign-in card): clear that site's
  cookies and storage in the bot's Linux Chromium, then remove the login.

Another user's bot or login is a 404, never the row. Hosts and labels come back decrypted to their owner only."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from roost.constants import COMPUTERS_BUSY_TEXT
from roost.desk import DeskAsleep, DeskBusy, DeskUnavailable
from roost.desk.site_data import BadHost
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.signin.service import SignOutLinuxOnly
from roost.signin.texts import SIGN_OUT_BAD_SITE_DETAIL, SIGN_OUT_LINUX_ONLY_DETAIL
from roost.vault.models import SiteLoginOut, site_login_out

vault_router = APIRouter(tags=["vault"])


async def _owned_bot_or_404(request: Request, user, bot_id: str) -> None:
    if await request.app.state.bots.get(user.id, bot_id) is None:
        raise HTTPException(status_code=404, detail="Bot not found")


@vault_router.get("/api/bots/{bot_id}/site-logins")
async def list_site_logins(bot_id: str, request: Request, user: CurrentUser) -> list[SiteLoginOut]:
    await _owned_bot_or_404(request, user, bot_id)
    return [site_login_out(login) for login in await request.app.state.vault_store.list_for_bot(user.id, bot_id)]


@vault_router.delete("/api/bots/{bot_id}/site-logins/{login_id}", status_code=204, dependencies=[RequireOrigin])
async def forget_site_login(bot_id: str, login_id: str, request: Request, user: CurrentUser) -> Response:
    await _owned_bot_or_404(request, user, bot_id)
    if not await request.app.state.vault_store.forget(user.id, login_id, bot_id):
        raise HTTPException(status_code=404, detail="Login not found")
    return Response(status_code=204)


_SIGN_OUT_REFUSALS: tuple[tuple[type[Exception], int, str], ...] = (
    (SignOutLinuxOnly, 400, SIGN_OUT_LINUX_ONLY_DETAIL),
    (BadHost, 400, SIGN_OUT_BAD_SITE_DETAIL),
    (DeskBusy, 409, COMPUTERS_BUSY_TEXT),
    (DeskUnavailable, 503, "desk unavailable"),
    (DeskAsleep, 503, "desk unavailable"),
)


@vault_router.post("/api/bots/{bot_id}/site-logins/{login_id}/sign-out", status_code=204,
                   dependencies=[RequireOrigin])
async def sign_out_site_login(bot_id: str, login_id: str, request: Request, user: CurrentUser) -> Response:
    """Sign out: the bot's Linux computer forgets the site (cookies and storage), and the login goes."""
    try:
        cleared = await request.app.state.signin.sign_out(user.id, bot_id, login_id)
    except tuple(kind for kind, _status, _detail in _SIGN_OUT_REFUSALS) as exc:
        status, detail = next((st, de) for kind, st, de in _SIGN_OUT_REFUSALS if isinstance(exc, kind))
        raise HTTPException(status_code=status, detail=detail) from exc
    if cleared is None:
        raise HTTPException(status_code=404, detail="Login not found")
    return Response(status_code=204)
