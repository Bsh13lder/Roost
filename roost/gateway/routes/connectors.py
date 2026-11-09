"""Connectors over HTTP (docs/plans/2026-10-22-roost-connectors.md §5).

- ``GET /api/connectors``, ``POST /api/connectors``, ``PATCH`` and ``DELETE /api/connectors/{id}``.

The key is write-only: no response ever holds it, only ``key_hint``. Bodies are parsed here, not by FastAPI,
because FastAPI's own 422 echoes the request (key included); every refusal is one plain sentence. Every route has
``CurrentUser`` and every write ``RequireOrigin``; another user's connector is a 404."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from roost.connectors import texts
from roost.connectors.models import Connector, ConnectorDraft, ConnectorPatch, check_secret, plain_error
from roost.connectors.requests import ConnectorRequestService, KeyRequest, NoSuchRequest, RequestClosed
from roost.connectors.service import ConnectorRefused, ConnectorService, NoSuchConnector
from roost.constants import CONNECTOR_SECRET_MAX
from roost.gateway.deps import CurrentUser, RequireOrigin

connectors_router = APIRouter(prefix="/api", tags=["connectors"])

_BODY_MAX_BYTES = CONNECTOR_SECRET_MAX * 4


def connector_out(connector: Connector) -> dict[str, Any]:
    return {
        "id": connector.id, "name": connector.name, "purpose": connector.purpose, "base_url": connector.base_url,
        "host": connector.host, "auth_style": connector.auth_style, "auth_name": connector.auth_name,
        "key_hint": connector.key_hint, "allowed_prefixes": list(connector.allowed_prefixes),
        "bot_ids": None if connector.bot_ids is None else list(connector.bot_ids),
        "created_at": connector.created_at, "updated_at": connector.updated_at,
    }


def _service(request: Request) -> ConnectorService:
    return request.app.state.connectors


async def parse_body(request: Request, model: type[BaseModel]) -> Any:
    """The body as ``model``, or a 422 with one plain sentence (never the input)."""
    raw = await request.body()
    try:
        if len(raw) > _BODY_MAX_BYTES:
            raise ValueError
        data = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=422, detail=texts.BAD_BODY) from None
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail=texts.BAD_BODY)
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=plain_error(exc)) from None


async def guarded(pending):
    try:
        return await pending
    except NoSuchConnector:
        raise HTTPException(status_code=404, detail=texts.NOT_FOUND) from None
    except ConnectorRefused as exc:
        raise HTTPException(status_code=422, detail=exc.text) from None


@connectors_router.get("/connectors")
async def list_connectors(request: Request, user: CurrentUser) -> list[dict[str, Any]]:
    return [connector_out(c) for c in await _service(request).list(user.id)]


@connectors_router.post("/connectors", status_code=201, dependencies=[RequireOrigin])
async def add_connector(request: Request, user: CurrentUser) -> dict[str, Any]:
    draft = await parse_body(request, ConnectorDraft)
    return connector_out(await guarded(_service(request).add(user.id, draft)))


@connectors_router.patch("/connectors/{connector_id}", dependencies=[RequireOrigin])
async def change_connector(connector_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    patch = await parse_body(request, ConnectorPatch)
    return connector_out(await guarded(_service(request).update(user.id, connector_id, patch)))


@connectors_router.delete("/connectors/{connector_id}", status_code=204, dependencies=[RequireOrigin])
async def delete_connector(connector_id: str, request: Request, user: CurrentUser) -> Response:
    await guarded(_service(request).delete(user.id, connector_id))
    return Response(status_code=204)


# --- The Add a key card (request_connector) ---------------------------------------------------------------------
# - ``GET /api/connector-requests?state=open`` (My turn) and ``GET /api/connector-requests/{id}`` (the card).
# - ``POST /api/connector-requests/{id}/save`` ``{secret}``: makes the connector through ``ConnectorService.add``;
#   409 when already answered, 422 with a plain sentence (the card stays open).
# - ``POST /api/connector-requests/{id}/decline``: Not now.

connector_requests_router = APIRouter(prefix="/api", tags=["connectors"])


class KeyIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    secret: str = Field(repr=False)

    @field_validator("secret")
    @classmethod
    def _secret(cls, v: str) -> str:
        return check_secret(v)


def request_out(key_request: KeyRequest) -> dict[str, Any]:
    r = key_request
    return {
        "id": r.id, "bot_id": r.bot_id, "thread_id": r.thread_id, "service": r.service, "base_url": r.base_url,
        "host": r.host, "why": r.why, "auth_style": r.auth_style, "auth_name": r.auth_name, "tainted": r.tainted,
        "state": r.state, "connector_id": r.connector_id, "created_at": r.created_at,
    }


def _requests(request: Request) -> ConnectorRequestService:
    return request.app.state.connector_requests


async def _answered(pending) -> dict[str, Any]:
    try:
        return request_out(await guarded(pending))
    except NoSuchRequest:
        raise HTTPException(status_code=404, detail=texts.REQUEST_NOT_FOUND) from None
    except RequestClosed:
        raise HTTPException(status_code=409, detail=texts.REQUEST_CLOSED) from None


@connector_requests_router.get("/connector-requests")
async def list_requests(request: Request, user: CurrentUser,
                        state: Literal["open"] = "open") -> list[dict[str, Any]]:
    return [request_out(r) for r in await _requests(request).store.list_open(user.id)]


@connector_requests_router.get("/connector-requests/{request_id}")
async def get_request(request_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    return await _answered(_requests(request).get(user.id, request_id))


@connector_requests_router.post("/connector-requests/{request_id}/save", dependencies=[RequireOrigin])
async def save_request(request_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    body = await parse_body(request, KeyIn)
    return await _answered(_requests(request).save(user.id, request_id, body.secret))


@connector_requests_router.post("/connector-requests/{request_id}/decline", dependencies=[RequireOrigin])
async def decline_request(request_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    return await _answered(_requests(request).decline(user.id, request_id))
