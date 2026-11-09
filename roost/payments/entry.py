"""``PayEntry``: the Pay card's Pay (P2–P5). Your card goes into the page's card boxes, then the stored Pay click runs.

``fields`` reads the live page for the parts it asks (and your saved cards' brand and last 4). ``pay`` checks the
card (yours, open, a Pay card, in your own chat, a Linux bot you are not holding), checks the values by hand, takes
the computer's lease ``pay:<card>``, checks the page is still on the card's host, types each part (``fill.py``),
keeps the card in Vault: cards when you asked (never the security code), writes an audit row of the parts and the
last 4, and then answers the card Yes, which re-resolves the page and clicks only the same Pay button.

Values live only in this call: never logged, stored (but the asked-for Vault card), published or put in a message.
Errors are logged by type name only."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from roost.approvals.models import ApprovalCard, CardClosed, CardState
from roost.desk.stuck import host_of_url
from roost.payments.cards import CardNotFound, CardStore, CardsFull, NewCard, SavedCard
from roost.payments.checks import CardCheckError, brand_of, check_cvc, check_exp, check_name, check_number
from roost.payments.fill import CardValues, PayRefused, card_boxes, clear_card, fill_card, needs_card
from roost.payments.pay_card import is_pay_card, pay_host
from roost.payments.texts import (
    BUSY_TEXT, CARD_GONE_TEXT, CARDS_FULL_TEXT, HELD_TEXT, MISSING_TEXT, NO_BOXES_TEXT, NOT_A_PAY_CARD_TEXT,
    NOT_TYPED_TEXT,
    NOT_YOUR_CHAT_TEXT, PART_WORDS, WRONG_PAGE_TEXT,
)

logger = logging.getLogger(__name__)

PAY_AUDIT_ACTION = "card_typed"
_LINUX = "linux"
_OWN_CHAT_KIND = "chat"


@dataclass(frozen=True)
class PayRequest:
    """The hand-validated body of ``POST /api/approvals/{id}/pay``. ``repr`` never shows a value."""

    card_id: str | None
    number: str
    exp: str
    name: str
    cvc: str
    save: bool

    def __repr__(self) -> str:
        return f"PayRequest(card_id={self.card_id!r}, save={self.save})"


@dataclass(frozen=True)
class PayFields:
    parts: tuple[str, ...]        # number · exp · name · cvc, only those the page asks for
    refusal: str                  # a framed card box or a list: Take control instead ("" when Roost can fill it)
    cards: tuple[SavedCard, ...]  # your Vault: cards (brand and last 4)


class NotPayCard(Exception):
    """Not a Pay card, or not in your own chat: the route answers 400 with ``detail``."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class PayEntry:
    def __init__(self, approvals: Any, talk: Any, bots: Any, desks: Any, control: Any, leases: Any, gate: Any,
                 cards: CardStore, *, today: Any = date.today) -> None:
        self._approvals, self._talk, self._bots, self._desks = approvals, talk, bots, desks
        self._control, self._leases, self._gate, self._cards, self._today = control, leases, gate, cards, today

    async def fields(self, user_id: str, card_id: str) -> PayFields | None:
        card = await self._open_card(user_id, card_id)
        if card is None:
            return None
        page = self._desks.for_bot(card.bot_id, _LINUX).page()
        targets = await page.targets() if page is not None else ()
        try:
            card_boxes(targets)
            refusal = ""
        except PayRefused as exc:
            refusal = exc.detail
        return PayFields(parts=needs_card(targets), refusal=refusal, cards=await self._cards.list(user_id))

    async def pay(self, user_id: str, card_id: str, request: PayRequest) -> ApprovalCard | None:
        """``None``: not your card. ``CardClosed``, ``NotPayCard``, ``CardCheckError`` or ``PayRefused`` otherwise.

        Card values sent while the page has no box Roost can fill (a framed box, an expiry list) are refused, never
        dropped: Pay would click on empty boxes. With no values (you typed the card yourself) Pay just clicks."""
        card = await self._open_card(user_id, card_id)
        if card is None:
            return None
        if self._control.held(card.bot_id) is not None:
            raise PayRefused(HELD_TEXT)
        desk = self._desks.for_bot(card.bot_id, _LINUX)
        page = desk.page()
        targets = await page.targets() if page is not None else ()
        parts = needs_card(targets)
        if not parts:
            if _sends_card(request):
                raise PayRefused(_why_not(targets))
            return await self._approvals.answer(user_id, card_id, "yes")
        values, new = await self._values(user_id, request, parts)
        typed = await self._fill_with_lease(card, desk, values)
        await self._after_fill(user_id, card, typed, values.number[-4:] if values.number else "")
        closed = await self._approvals.answer(user_id, card_id, "yes")
        await self._remember(user_id, request, new)
        return closed

    async def _after_fill(self, user_id: str, card: ApprovalCard, typed: tuple[str, ...], last4: str) -> None:
        try:
            await self._gate.record_approved(user_id, card.bot_id, PAY_AUDIT_ACTION,
                                             {"parts": list(typed), "last4": last4}, reason="approved",
                                             tainted=card.tainted)
        except Exception as exc:  # noqa: BLE001 - the audit must not leave a filled card unpaid
            logger.warning("The audit row for Pay card %s was not written: %s", card.id, type(exc).__name__)

    async def _open_card(self, user_id: str, card_id: str) -> ApprovalCard | None:
        card = await self._approvals.get(user_id, card_id)
        if card is None:
            return None
        if card.state is not CardState.OPEN:
            raise CardClosed(card_id)
        if not is_pay_card(card):
            raise NotPayCard(NOT_A_PAY_CARD_TEXT)
        thread = await self._talk.get_thread(user_id, card.thread_id)
        bot = await self._bots.get(user_id, card.bot_id)
        if thread is None or thread.kind != _OWN_CHAT_KIND or thread.peer_bot_id or bot is None \
                or bot.computer != _LINUX:
            raise NotPayCard(NOT_YOUR_CHAT_TEXT)
        return card

    async def _values(self, user_id: str, request: PayRequest, parts: tuple[str, ...]) -> tuple[CardValues, NewCard | None]:
        """The checked values for the parts the page asks; a saved card gives all but the security code."""
        if request.card_id:
            try:
                saved = await self._cards.secret(user_id, request.card_id)
            except CardNotFound:
                raise CardCheckError(CARD_GONE_TEXT) from None
            number, exp, name, new = saved.number, check_exp(saved.exp, self._today()), saved.name, None
        else:
            number = check_number(request.number) if "number" in parts or request.save else ""
            exp = check_exp(request.exp, self._today()) if "exp" in parts or request.save else ""
            name = check_name(request.name) if "name" in parts or (request.save and request.name) else ""
            new = NewCard(number=number, exp=exp, name=name) if request.save and number and exp else None
        cvc = check_cvc(request.cvc, brand_of(number) if number else "card") if "cvc" in parts else ""
        for part, value in (("number", number), ("exp", exp), ("name", name)):
            if part in parts and not value:
                raise CardCheckError(MISSING_TEXT.format(part=PART_WORDS[part]))
        return CardValues(number=number, exp=exp, name=name, cvc=cvc), new

    async def _fill_with_lease(self, card: ApprovalCard, desk: Any, values: CardValues) -> tuple[str, ...]:
        lease, host = f"pay:{card.id}", pay_host(card)
        if not self._leases.acquire(card.bot_id, lease):
            raise PayRefused(BUSY_TEXT)
        try:
            page = desk.page()
            if page is None or host_of_url(await page.url()).lower() != host.lower():
                raise PayRefused(WRONG_PAGE_TEXT.format(host=host))
            try:
                return await fill_card(page, desk, values, host)
            except PayRefused:
                await self._empty(card, desk, host)
                raise
            except Exception as exc:  # noqa: BLE001 - any failure: the card leaves the page, the words are fixed
                logger.warning("A card for Pay card %s of bot %s was not typed: %s", card.id, card.bot_id,
                               type(exc).__name__)
                await self._empty(card, desk, host)
                raise PayRefused(NOT_TYPED_TEXT) from None
        finally:
            self._leases.release(card.bot_id, lease)

    @staticmethod
    async def _empty(card: ApprovalCard, desk: Any, host: str) -> None:
        try:
            await clear_card(desk.page(), desk, host)
        except Exception as exc:  # noqa: BLE001 - logged by type only
            logger.warning("Card boxes for Pay card %s were not emptied: %s", card.id, type(exc).__name__)

    async def _remember(self, user_id: str, request: PayRequest, new: NewCard | None) -> None:
        """Keep the card (or mark a saved one used) after Pay; a failure here never undoes the payment."""
        try:
            if new is not None:
                await self._cards.save(user_id, new)
            elif request.card_id:
                await self._cards.mark_used(user_id, request.card_id)
        except CardsFull:
            logger.warning("A card was not saved for user %s: %s", user_id, CARDS_FULL_TEXT)
        except Exception as exc:  # noqa: BLE001 - logged by type only, never the card
            logger.warning("A card was not saved for user %s: %s", user_id, type(exc).__name__)


def _sends_card(request: PayRequest) -> bool:
    return bool(request.card_id or request.number or request.exp or request.name or request.cvc)


def _why_not(targets: tuple[Any, ...]) -> str:
    try:
        card_boxes(targets)
    except PayRefused as exc:
        return exc.detail
    return NO_BOXES_TEXT
