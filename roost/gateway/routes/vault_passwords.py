"""Vault: passwords over HTTP (owner, 2026-11-08, docs/plans/2026-11-08-roost-vault-passwords.md V2, V3).

- ``GET /api/vault/passwords``: your saved logins: the site, the user name, Always for this site and the dates.
- ``POST /api/vault/passwords``: save one (the same site and user name again replaces its password).
- ``PATCH /api/vault/passwords/{id}``: a new password and/or Always for this site.
- ``DELETE /api/vault/passwords/{id}``.

A password is write-only: no reply holds one. Bodies are validated by hand, so a refusal never echoes what was sent
(FastAPI's own 422 would). Another user's login is a 404."""

from __future__ import annotations

from typing import Any, Final

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import VAULT_HOST_MAX_CHARS, VAULT_PASSWORD_MAX_CHARS, VAULT_USERNAME_MAX_CHARS
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.vault.models import normalise_host
from roost.vault.passwords import NewLogin, PasswordNotFound, PasswordsFull, SavedLogin, VaultPasswordStore

vault_passwords_router = APIRouter(prefix="/api/vault/passwords", tags=["vault"])

LOGIN_BODY_TEXT: Final = "Those login details don't fit. Check the site, user name and password."
NO_CHANGE_TEXT: Final = "Send a new password or Always for this site."
LOGIN_GONE_TEXT: Final = "That login isn't in Vault: passwords."
VAULT_FULL_TEXT: Final = "Vault: passwords is full. Delete a login you no longer use first."


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    host: str = Field(min_length=1, max_length=VAULT_HOST_MAX_CHARS)
    username: str = Field(default="", max_length=VAULT_USERNAME_MAX_CHARS)
    password: str = Field(min_length=1, max_length=VAULT_PASSWORD_MAX_CHARS)
    always: bool = False


class LoginPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    password: str | None = Field(default=None, min_length=1, max_length=VAULT_PASSWORD_MAX_CHARS)
    always: bool | None = None


class SavedLoginOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    host: str
    username: str
    always: bool
    created_at: str
    updated_at: str
    last_used_at: str | None


def login_out(login: SavedLogin) -> SavedLoginOut:
    return SavedLoginOut(id=login.id, host=login.host, username=login.username, always=login.always,
                         created_at=login.created_at, updated_at=login.updated_at, last_used_at=login.last_used_at)


def _store(request: Request) -> VaultPasswordStore:
    return request.app.state.vault_passwords


async def _body(request: Request, model: type[BaseModel]) -> Any:
    """The body, or a 422 that never says what was sent."""
    try:
        return model.model_validate(await request.json())
    except (ValueError, ValidationError):
        raise HTTPException(status_code=422, detail=LOGIN_BODY_TEXT) from None


@vault_passwords_router.get("")
async def list_logins(request: Request, user: CurrentUser) -> list[SavedLoginOut]:
    return [login_out(login) for login in await _store(request).list(user.id)]


@vault_passwords_router.post("", status_code=201, dependencies=[RequireOrigin])
async def save_login(request: Request, user: CurrentUser) -> SavedLoginOut:
    body: LoginIn = await _body(request, LoginIn)
    host = normalise_host(body.host)
    if not host:
        raise HTTPException(status_code=422, detail=LOGIN_BODY_TEXT)
    store = _store(request)
    try:
        saved = await store.save(user.id, NewLogin(host=host, username=body.username.strip(), password=body.password))
    except PasswordsFull:
        raise HTTPException(status_code=409, detail=VAULT_FULL_TEXT) from None
    return login_out(await store.patch(user.id, saved.id, password=None, always=True) if body.always else saved)


@vault_passwords_router.patch("/{login_id}", dependencies=[RequireOrigin])
async def patch_login(login_id: str, request: Request, user: CurrentUser) -> SavedLoginOut:
    body: LoginPatchIn = await _body(request, LoginPatchIn)
    if body.password is None and body.always is None:
        raise HTTPException(status_code=422, detail=NO_CHANGE_TEXT)
    try:
        return login_out(await _store(request).patch(user.id, login_id, password=body.password, always=body.always))
    except PasswordNotFound:
        raise HTTPException(status_code=404, detail=LOGIN_GONE_TEXT) from None


@vault_passwords_router.delete("/{login_id}", status_code=204, dependencies=[RequireOrigin])
async def delete_login(login_id: str, request: Request, user: CurrentUser) -> None:
    try:
        await _store(request).delete(user.id, login_id)
    except PasswordNotFound:
        raise HTTPException(status_code=404, detail=LOGIN_GONE_TEXT) from None
