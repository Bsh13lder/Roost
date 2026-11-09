"""The Stuck card's buttons over HTTP (stuck flow, Task 7; design §2 "The card's buttons", R8–R10).

- ``GET /api/stuck``: your open cards, newest first (Home's My turn, the chat's card).
- ``GET /api/stuck/{card_id}``: one of your cards, open or closed, in the list's shape (a closed card's final state).
- ``POST /api/stuck/{card_id}/clear``: Give it back, Try again and Done, carry on. An optional body
  ``{"how": "try_again" | "gave_back"}`` says which (default ``gave_back``); Try again has its own words.
- ``POST /api/stuck/{card_id}/give-up``: Give up.
- ``POST /api/stuck/{card_id}/open-in-main-browser``: Use my main Brave.
- ``POST /api/stuck/{card_id}/open-sign-in``: a Sign-in card's Open sign-in (its page, then you take control).
- ``POST /api/stuck/{card_id}/later``: a Sign-in card's Later.
- ``POST /api/stuck/{card_id}/secret``: a field card's masked field (B3): ``{"value"}`` is typed into the box on the
  bot's computer and never kept. Its body is read by hand, so a refusal never echoes the value back.

Every route has ``CurrentUser``, and every button has ``RequireOrigin``.
``StuckService`` does the work, and this module only turns its answers into
status codes. Another user's card id is a 404, never the card. The service
checks the address before the keeper is asked (R8), because ``KeeperClient``
turns a keeper refusal it did not expect into a 503.
"""

from __future__ import annotations

from typing import Awaitable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import COMPUTERS_BUSY_TEXT, SECRET_VALUE_MAX_CHARS
from roost.desk import DeskBusy, DeskUnavailable
from roost.desk.url_policy import UrlBlocked
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.stuck.models import (
    DEFAULT_CLEAR_HOW, CardClosed, ClearHow, KeepAnswerNeeded, NoAddress, NotSignInCard, StuckCard, StuckCardOut,
    stuck_card_out,
)
from roost.signin.check import NotSignedInYet
from roost.signin.secret_entry import FieldRefused, NotFieldCard
from roost.signin.secret_texts import BAD_VALUE_DETAIL, NOT_FIELD_CARD_DETAIL
from roost.signin.texts import KEEP_ANSWER_NEEDED_DETAIL, NOT_SIGN_IN_DETAIL, not_signed_in_text
from roost.stuck.service import StuckService
from roost.vault.models import NO_SITE_TEXT, AccountLabel, NoSite

stuck_router = APIRouter(prefix="/api/stuck", tags=["stuck"])

CARD_NOT_FOUND_DETAIL = "Card not found"
CARD_CLOSED_DETAIL = "This card is already closed."
NO_ADDRESS_DETAIL = "This card has no web address."
ADDRESS_REFUSED_DETAIL = "That address can't be opened."
DESK_UNAVAILABLE_DETAIL = "desk unavailable"

# What each refusal from StuckService answers. No two of these types overlap.
_REFUSALS: tuple[tuple[type[Exception], int, str], ...] = (
    (CardClosed, 409, CARD_CLOSED_DETAIL),
    (NoAddress, 400, NO_ADDRESS_DETAIL),
    (NoSite, 400, NO_SITE_TEXT),
    (UrlBlocked, 400, ADDRESS_REFUSED_DETAIL),
    (DeskUnavailable, 503, DESK_UNAVAILABLE_DETAIL),
    (NotSignInCard, 400, NOT_SIGN_IN_DETAIL),
    (KeepAnswerNeeded, 400, KEEP_ANSWER_NEEDED_DETAIL),
    (DeskBusy, 409, COMPUTERS_BUSY_TEXT),
)
_REFUSED: tuple[type[Exception], ...] = tuple(kind for kind, _status, _detail in _REFUSALS)


class ClearIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    how: ClearHow = DEFAULT_CLEAR_HOW
    account: AccountLabel | None = None     # which account you signed in with; saved and put in the continue line
    keep: bool | None = None                # a Sign-in card's "Keep me signed in on this computer?" (None: not asked)


def _service(request: Request) -> StuckService:
    return request.app.state.stuck_service


def _refusal(exc: Exception) -> HTTPException:
    status, detail = next((status, detail) for kind, status, detail in _REFUSALS if isinstance(exc, kind))
    return HTTPException(status_code=status, detail=detail)


async def _answer(pending: Awaitable[StuckCard | None]) -> StuckCardOut:
    try:
        card = await pending
    except NotSignedInYet as exc:
        raise HTTPException(status_code=409, detail=not_signed_in_text(exc.host)) from exc
    except _REFUSED as exc:
        raise _refusal(exc) from exc
    if card is None:
        raise HTTPException(status_code=404, detail=CARD_NOT_FOUND_DETAIL)
    return stuck_card_out(card)


async def _ended_teaching(request: Request, user_id: str, card: StuckCardOut) -> StuckCardOut:
    """The card gave the computer back: a teach recording on it ends with that hold."""
    await request.app.state.teach.end(user_id, card.bot_id)
    return card


@stuck_router.get("")
async def list_stuck(request: Request, user: CurrentUser) -> list[StuckCardOut]:
    return [stuck_card_out(card) for card in await _service(request).list_open(user.id)]


@stuck_router.get("/{card_id}")
async def get_stuck(card_id: str, request: Request, user: CurrentUser) -> StuckCardOut:
    return await _answer(_service(request).get(user.id, card_id))


@stuck_router.post("/{card_id}/clear", dependencies=[RequireOrigin])
async def clear_card(card_id: str, request: Request, user: CurrentUser, body: ClearIn | None = None) -> StuckCardOut:
    """Give it back, Try again, and Done, carry on (R10): the bot carries on with the task. No body
    means ``gave_back``."""
    if body is None:
        cleared = _service(request).clear(user.id, card_id, DEFAULT_CLEAR_HOW)
    else:
        cleared = _service(request).clear(user.id, card_id, body.how, body.account, body.keep)
    return await _ended_teaching(request, user.id, await _answer(cleared))


@stuck_router.post("/{card_id}/give-up", dependencies=[RequireOrigin])
async def give_up_card(card_id: str, request: Request, user: CurrentUser) -> StuckCardOut:
    return await _ended_teaching(request, user.id, await _answer(_service(request).give_up(user.id, card_id)))


@stuck_router.post("/{card_id}/open-in-main-browser", dependencies=[RequireOrigin])
async def open_card_in_main_browser(card_id: str, request: Request, user: CurrentUser) -> StuckCardOut:
    """Use my main Brave: opens the card's address there, with no automation (D-A3)."""
    return await _answer(_service(request).open_in_main_browser(user.id, card_id))


@stuck_router.post("/{card_id}/open-sign-in", dependencies=[RequireOrigin])
async def open_sign_in(card_id: str, request: Request, user: CurrentUser) -> StuckCardOut:
    """Open sign-in: the bot's own Linux computer shows the card's page, and you take control to sign in."""
    return await _answer(request.app.state.signin.open_sign_in(user.id, card_id))


class SecretIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    value: str = Field(min_length=1, max_length=SECRET_VALUE_MAX_CHARS)
    save: bool = False          # Save in Vault (owner, 2026-11-08): a password is kept sealed for this site


async def _secret_value(request: Request) -> SecretIn:
    """The body, or a 422 that never says what was sent (FastAPI's own 422 would echo it)."""
    try:
        return SecretIn.model_validate(await request.json())
    except (ValueError, ValidationError):
        raise HTTPException(status_code=422, detail=BAD_VALUE_DETAIL.format(limit=SECRET_VALUE_MAX_CHARS)) from None


@stuck_router.post("/{card_id}/secret", dependencies=[RequireOrigin])
async def type_secret(card_id: str, request: Request, user: CurrentUser) -> StuckCardOut:
    """B3: your password or code goes straight into the box on the bot's computer; the card closes as cleared."""
    body = await _secret_value(request)
    try:
        card = await request.app.state.secret_entry.type_secret(user.id, card_id, body.value, save=body.save)
    except FieldRefused as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from None
    except NotFieldCard:
        raise HTTPException(status_code=400, detail=NOT_FIELD_CARD_DETAIL) from None
    except CardClosed:
        raise HTTPException(status_code=409, detail=CARD_CLOSED_DETAIL) from None
    if card is None:
        raise HTTPException(status_code=404, detail=CARD_NOT_FOUND_DETAIL)
    return stuck_card_out(card)


@stuck_router.post("/{card_id}/later", dependencies=[RequireOrigin])
async def later_card(card_id: str, request: Request, user: CurrentUser) -> StuckCardOut:
    """Later: the bot leaves the site for now and stops that task."""
    return await _answer(_service(request).later(user.id, card_id))
