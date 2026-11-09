"""The Pay card and Vault: cards over HTTP (``docs/plans/2026-11-05-roost-pay-card.md``).

- ``GET /api/approvals/{id}/pay``: the card parts the page asks for, a Take-control reason, your saved cards.
- ``POST /api/approvals/{id}/pay``: your card goes into the page's boxes, then the card's Pay click runs (P4: a
  hand-validated body; a refusal never says what was sent).
- ``GET /api/payment-cards`` and ``DELETE /api/payment-cards/{id}``: Vault: cards, brand and last 4 only.

Another user's card id is a 404."""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.approvals.models import ApprovalCardOut, CardClosed, approval_card_out
from roost.approvals.texts import CARD_CLOSED_TEXT, CARD_NOT_FOUND_TEXT
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.payments.cards import CardNotFound, SavedCard
from roost.payments.checks import CardCheckError
from roost.payments.entry import NotPayCard, PayEntry, PayRequest
from roost.payments.fill import PayRefused

payments_router = APIRouter(tags=["payments"])

PAY_BODY_TEXT: Final = "Those card details don't fit. Check them and try again."
SAVED_CARD_GONE_TEXT: Final = "That card isn't in Vault: cards."
_ID_MAX, _NUMBER_MAX, _EXP_MAX, _NAME_MAX, _CVC_MAX = 64, 32, 10, 80, 4


class PayIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    card_id: str | None = Field(default=None, min_length=1, max_length=_ID_MAX)
    number: str = Field(default="", max_length=_NUMBER_MAX)
    exp: str = Field(default="", max_length=_EXP_MAX)
    name: str = Field(default="", max_length=_NAME_MAX)
    cvc: str = Field(default="", max_length=_CVC_MAX)
    save: bool = False


class SavedCardOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    brand: str
    last4: str
    last_used_at: str | None


class PayFieldsOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    parts: list[str]
    refusal: str
    cards: list[SavedCardOut]


def _entry(request: Request) -> PayEntry:
    return request.app.state.pay_entry


def _card_out(card: SavedCard) -> SavedCardOut:
    return SavedCardOut(id=card.id, brand=card.brand, last4=card.last4, last_used_at=card.last_used_at)


async def _pay_request(request: Request) -> PayRequest:
    """The body, or a 422 that never says what was sent (FastAPI's own 422 would echo it)."""
    try:
        body = PayIn.model_validate(await request.json())
    except (ValueError, ValidationError):
        raise HTTPException(status_code=422, detail=PAY_BODY_TEXT) from None
    return PayRequest(card_id=body.card_id, number=body.number, exp=body.exp, name=body.name, cvc=body.cvc,
                      save=body.save)


@payments_router.get("/api/approvals/{card_id}/pay")
async def pay_fields(card_id: str, request: Request, user: CurrentUser) -> PayFieldsOut:
    try:
        fields = await _entry(request).fields(user.id, card_id)
    except CardClosed:
        raise HTTPException(status_code=409, detail=CARD_CLOSED_TEXT) from None
    except NotPayCard as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from None
    if fields is None:
        raise HTTPException(status_code=404, detail=CARD_NOT_FOUND_TEXT)
    return PayFieldsOut(parts=list(fields.parts), refusal=fields.refusal, cards=[_card_out(c) for c in fields.cards])


@payments_router.post("/api/approvals/{card_id}/pay", dependencies=[RequireOrigin])
async def pay(card_id: str, request: Request, user: CurrentUser) -> ApprovalCardOut:
    """Your card into the page's card boxes, then the card's Pay click (only the same button)."""
    body = await _pay_request(request)
    try:
        card = await _entry(request).pay(user.id, card_id, body)
    except CardClosed:
        raise HTTPException(status_code=409, detail=CARD_CLOSED_TEXT) from None
    except NotPayCard as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from None
    except CardCheckError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except PayRefused as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from None
    if card is None:
        raise HTTPException(status_code=404, detail=CARD_NOT_FOUND_TEXT)
    return approval_card_out(card)


@payments_router.get("/api/payment-cards")
async def list_cards(request: Request, user: CurrentUser) -> list[SavedCardOut]:
    return [_card_out(c) for c in await request.app.state.payment_cards.list(user.id)]


@payments_router.delete("/api/payment-cards/{saved_id}", dependencies=[RequireOrigin], status_code=204)
async def delete_card(saved_id: str, request: Request, user: CurrentUser) -> None:
    try:
        await request.app.state.payment_cards.delete(user.id, saved_id)
    except CardNotFound:
        raise HTTPException(status_code=404, detail=SAVED_CARD_GONE_TEXT) from None
