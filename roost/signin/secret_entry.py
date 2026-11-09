"""``SecretEntry``: your password or code, typed into the box on the bot's own computer (B3, owner decision
2026-10-23; ``docs/plans/2026-10-23-roost-tabs-signin-flow.md``).

``type_secret`` checks the card (yours, open, a field card, a Linux bot, you not holding the computer), takes the
computer's screen lease, reads the page again (the card's host; the focused secret box, or else the one visible
secret box, clicked first), sends the value as one ``type`` through the keeper's input route (text on stdin only),
and presses nothing else. Then the audit gets the kind and the length, and the card closes as cleared with your
line "I typed your <kind> into the box. Carry on." (the bot clicks Next or Sign in itself). No Vault row is saved
here: the sign-in is not finished yet, and a login is saved only once the computer looks signed in (A1). With Save in
Vault (owner, 2026-11-08) a password (never a code) is also kept sealed in Vault: passwords for the card's site, with
the user name the page's own sign-in box holds (empty when there is none).

The value lives only in this call's arguments: it is never logged, stored, published, put in a message, an audit
row or a prompt. Errors are logged by type name only."""

from __future__ import annotations

import logging
from typing import Any

from roost.computer_use.models import PageTarget
from roost.computer_use.session import ComputerUseLease
from roost.desk import DeskAsleep, DeskUnavailable, InputRefusedByComputer, ScreenInput
from roost.desk.cdp import CdpClientError
from roost.desk.control import ControlLock
from roost.desk.page_geometry import viewport_to_screen
from roost.desk.stuck import host_of_url
from roost.signin.secret_texts import (
    BUSY_DETAIL, HELD_DETAIL, MANY_BOXES_DETAIL, NO_BOX_DETAIL, NOT_TYPED_DETAIL, WRONG_PAGE_DETAIL, typed_line,
)
from roost.stuck.models import CardClosed, CardState, StuckCard
from roost.stuck.service import StuckService
from roost.stuck.store import StuckStore
from roost.constants import VAULT_USERNAME_MAX_CHARS
from roost.vault.models import normalise_host
from roost.vault.passwords import NewLogin, PasswordsFull, VaultPasswordStore

logger = logging.getLogger(__name__)

SECRET_AUDIT_ACTION = "secret_typed"
_PASSWORD = "password"
NOT_SAVED_LINE = "It wasn't saved in Vault: passwords (it is full); delete an old login in Settings."
_LINUX = "linux"
_NOT_TYPED = (DeskAsleep, DeskUnavailable, InputRefusedByComputer, CdpClientError, ValueError)


def _sign_in_secret(target: PageTarget) -> bool:
    """A password or code box; never a card box (those only the Pay card fills)."""
    return target.secret_field and not target.card_field


async def _sign_in_name(page: Any) -> str:
    """What the page's one email or user name box holds; empty when there is none, or more than one."""
    boxes = [target for target in await page.targets() if target.sign_in_box and not target.secret_field]
    if len(boxes) != 1:
        return ""
    return ((await page.box_text(boxes[0].node_id)) or "").strip()[:VAULT_USERNAME_MAX_CHARS]


class NotFieldCard(Exception):
    """The card shows no masked field (or its bot is not on Linux): the route answers 400."""


class FieldRefused(Exception):
    """Nothing was typed, and ``detail`` says why in plain words: the route answers 409 and the card stays open."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class SecretEntry:
    def __init__(self, stuck: StuckStore, service: StuckService, bots: Any, desks: Any, control: ControlLock,
                 leases: ComputerUseLease, gate: Any, *, vault: VaultPasswordStore | None = None) -> None:
        self._stuck = stuck
        self._service = service
        self._bots = bots
        self._desks = desks
        self._control = control
        self._leases = leases
        self._gate = gate
        self._vault = vault

    async def type_secret(self, user_id: str, card_id: str, value: str, *, save: bool = False) -> StuckCard | None:
        """``None``: not your card. ``CardClosed``, ``NotFieldCard`` or ``FieldRefused`` otherwise."""
        card = await self._stuck.get(user_id, card_id)
        if card is None:
            return None
        if card.state is not CardState.OPEN:
            raise CardClosed(card_id)
        bot = await self._bots.get(user_id, card.bot_id)
        if not card.secret_field or bot is None or bot.computer != _LINUX:
            raise NotFieldCard(card_id)
        if self._control.held(bot.id) is not None:
            raise FieldRefused(HELD_DETAIL)
        username = await self._type_with_lease(card, value)
        saved = await self._save(user_id, card, username, value) if save else True
        await self._gate.record_approved(user_id, bot.id, SECRET_AUDIT_ACTION,
                                         {"kind": card.secret_field, "length": len(value)},
                                         reason="approved", tainted=card.tainted)
        line = typed_line(card.secret_field) if saved else f"{typed_line(card.secret_field)} {NOT_SAVED_LINE}"
        return await self._service.clear(user_id, card_id, "try_again", keep=None, line=line)

    async def _save(self, user_id: str, card: StuckCard, username: str, value: str) -> bool:
        """Save in Vault, after the typing: a password only (never a code). A save that fails never undoes the
        typing or leaves the card open (security review L4); it is logged by type name only."""
        if card.secret_field != _PASSWORD or self._vault is None:
            return True
        try:
            await self._vault.save(user_id, NewLogin(host=normalise_host(card.host), username=username,
                                                     password=value))
        except (PasswordsFull, ValueError) as exc:
            logger.warning("A password for card %s was typed but not saved: %s", card.id, type(exc).__name__)
            return False
        return True

    async def _type_with_lease(self, card: StuckCard, value: str) -> str:
        """Types the value; returns what the page's sign-in box holds (the user name to save with it)."""
        lease = f"secret:{card.id}"
        if not self._leases.acquire(card.bot_id, lease):
            raise FieldRefused(BUSY_DETAIL)
        try:
            return await self._type(card, self._desks.for_bot(card.bot_id, _LINUX), value)
        except _NOT_TYPED as exc:
            logger.warning("A secret for card %s of bot %s was not typed: %s", card.id, card.bot_id,
                           type(exc).__name__)
            raise FieldRefused(NOT_TYPED_DETAIL) from None
        finally:
            self._leases.release(card.bot_id, lease)

    async def _type(self, card: StuckCard, desk: Any, value: str) -> str:
        page = desk.page()
        if page is None:
            raise FieldRefused(NOT_TYPED_DETAIL)
        username = await _sign_in_name(page)
        geo = await page.geometry()                   # the bot's tab in front, its window up
        box, focused = await self._box(page, card)
        if not focused:
            x, y = viewport_to_screen(box.box.center(), geo)
            await desk.send_input(ScreenInput("move", x, y, window=geo.window_rect))
            await desk.send_input(ScreenInput("click", x, y, window=geo.window_rect))
            now = await page.focused()
            if now is None or now.node_id != box.node_id or not _sign_in_secret(now):
                raise FieldRefused(NOT_TYPED_DETAIL)
        await desk.send_input(ScreenInput("type", text=value, window=geo.window_rect))
        return username

    @staticmethod
    async def _box(page: Any, card: StuckCard) -> tuple[PageTarget, bool]:
        """The secret box to type into and whether it already has focus, or ``FieldRefused``."""
        if host_of_url(await page.url()).lower() != card.host.lower():
            raise FieldRefused(WRONG_PAGE_DETAIL.format(host=card.host))
        focused = await page.focused()
        if focused is not None and _sign_in_secret(focused) and not focused.cross_origin_frame:   # review L5
            return focused, True
        boxes = [target for target in await page.targets() if _sign_in_secret(target)]
        if not boxes:
            raise FieldRefused(NO_BOX_DETAIL)
        if len(boxes) > 1:
            raise FieldRefused(MANY_BOXES_DETAIL)
        return boxes[0], False
