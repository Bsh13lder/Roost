"""``StuckService``: the Stuck card's buttons (stuck flow, Task 7; design §2, R6, R8–R10).

``TurnRunner`` opens cards (Task 5), and this service closes them. It is built
after ``turns`` on ``app.state.stuck_service``, the way ``RoomService`` is, so
the runner never needs the service and the two never import each other in a
circle.

- ``clear`` is behind Give it back, Try again and Done, carry on. The card
  becomes ``cleared``, any control hold is released, your ``card_answer`` line
  is posted, and a ``card_answer`` item continues the task in the same thread.
  The line is posted because the model reads the chat, never an item's body
  (R6). The item carries the card's taint and its address as link scope.
  Then the status settles (R9): once the continue run ends, or, when that run
  can't start (the daily run cap), as soon as the drain task gives up.
- ``give_up``: the card becomes ``given_up``, the bot says ``GIVE_UP_LINE``,
  and its status settles (Resting, or Off duty; while a run is going, once it ends).
- ``open_in_main_browser``: the address is checked here first (R8), then opened
  in your own Brave through ``MainBrowser``. The card remembers ``main_opened``.

Every state change publishes a ``stuck_card`` frame. ``CardClosed`` covers a
card that was already closed, and one that another press closed between this
press's read and its write (a double click, or two tabs). ``StuckStore.close``
only moves a card out of ``open``, so exactly one press wins.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import uuid4

from roost.desk import DeskUnavailable
from roost.desk.control import ControlLock
from roost.desk.main_browser import MainBrowser
from roost.desk.url_policy import check_url
from roost.events.hub import EventHub
from roost.stuck.announce import post_bot_line, publish_card
from roost.talk.carry import card_site_entries, joined, parked_site_entries
from roost.signin.check import SignInCheck
from roost.signin.texts import LATER_LINE, kept_sentence
from roost.stuck.models import (
    DEFAULT_CLEAR_HOW, CardClosed, CardState, ClearHow, KeepAnswerNeeded, NoAddress, NotSignInCard, StuckCard,
)
from roost.stuck.store import StuckStore
from roost.stuck.texts import GIVE_UP_LINE, continue_text
from roost.talk.runner import TurnRunner
from roost.talk.store import Message, TalkStore, message_out
from roost.vault.models import NoSite, clean_label, signed_in_line
from roost.vault.service import VaultService
from roost.work.models import ORIGIN_CARD, WorkDraft, WorkKind

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AccountAnswer:
    """What I'm done said: the account name (optional), Keep me signed in (Sign-in cards only) and the continue
    item a "No, this time" clear waits for."""

    account: str | None
    keep: bool | None
    item_id: str


class StuckService:
    def __init__(self, store: StuckStore, talk: TalkStore, events: EventHub, turns: TurnRunner,
                 control: ControlLock, main_browser: MainBrowser, vault: VaultService | None = None,
                 signed_in: SignInCheck | None = None) -> None:
        self._vault = vault
        self._signed_in = signed_in
        self._store = store
        self._talk = talk
        self._events = events
        self._turns = turns
        self._control = control
        self._main_browser = main_browser

    async def list_open(self, user_id: str) -> tuple[StuckCard, ...]:
        return await self._store.list_open(user_id)

    async def get(self, user_id: str, card_id: str) -> StuckCard | None:
        """One of the user's cards, open or closed; ``None`` for another user's or an unknown id."""
        return await self._store.get(user_id, card_id)

    async def clear(self, user_id: str, card_id: str, how: ClearHow = DEFAULT_CLEAR_HOW,
                    account: str | None = None, keep: bool | None = None,
                    line: str | None = None) -> StuckCard | None:
        """Give it back (or Try again, ``how="try_again"``, which has its own line): the bot carries on
        with the task. ``None`` when the card
        is not the user's; ``CardClosed`` when it is no longer open. The last
        step settles the status (R9), so a bot whose continue run can't start
        never keeps showing Stuck with no open card. That holds on failure too: if
        posting the line or queuing the item raises after the card closed, the frame
        and the settle still happen, and the error is logged and raised."""
        opened = await self._open_card(user_id, card_id)
        if opened is None:
            return None
        if opened.sign_in and how == "gave_back" and keep is None:
            raise KeepAnswerNeeded(card_id)
        item_id = str(uuid4())
        said = await self._save_account(user_id, opened, AccountAnswer(account, keep, item_id))   # NoSite: stays open
        card = await self._close(user_id, card_id, CardState.CLEARED, answer_item_id=item_id)
        self._control.give_back(card.bot_id)
        text = (line if line is not None else continue_text(card, how)) + said   # B3: the secret field's own line
        try:
            line = await self._post_continue_line(user_id, card, text)
            await self._turns.submit(user_id, WorkDraft(
                bot_id=card.bot_id, thread_id=card.thread_id, kind=WorkKind.CARD_ANSWER, origin=ORIGIN_CARD,
                body=text, tainted=card.tainted, message_id=line.id,
                link_scope=await self._carried(user_id, card),
            ), item_id=item_id)
        except Exception:
            # The card is already closed: the face still hears of it and the status still settles
            # (below), or the bot would keep showing Stuck with no open card. Ids only, never the address.
            logger.exception("Giving back Stuck card %s of bot %s failed after the card was closed",
                             card.id, card.bot_id)
            raise
        finally:
            await self._announce_closed(user_id, card)
        return card

    async def _carried(self, user_id: str, card: StuckCard) -> tuple[str, ...]:
        """The continue item's link scope: the card's address and its site, and the sites the parked run opened
        itself (``roost/talk/carry.py``), so carrying on there needs no Open card. Never a page's link."""
        parked = await parked_site_entries(self._turns.queue, user_id, card.work_item_id)
        return joined(card_site_entries(card.url), parked)

    async def _save_account(self, user_id: str, card: StuckCard, answer: AccountAnswer) -> str:
        """Remember the account for the card's own site and return the sentence for the continue line. On a
        Sign-in card, "Keep me signed in on this computer?" is saved too: No clears the site after this task."""
        label = clean_label(answer.account or "")
        keeping = card.sign_in and answer.keep is not None
        if (not label and not keeping) or self._vault is None:
            return ""
        if not card.host:
            raise NoSite(card.id)
        if card.sign_in and self._signed_in is not None:
            await self._signed_in.require(user_id, card.bot_id, card.host)   # NotSignedInYet: saves nothing
        kept = bool(answer.keep) if keeping else True
        login = await self._vault.sign_in(
            user_id, card.bot_id, card.host, label or None, kept=kept,
            clear_after_item_id=None if kept else answer.item_id)
        said = [signed_in_line(login.host, login.label)] if label else []
        if keeping:
            said.append(kept_sentence(login.host, kept))
        return " " + " ".join(said)

    async def give_up(self, user_id: str, card_id: str) -> StuckCard | None:
        """Give up: the task ends, and the bot says so. ``None`` / ``CardClosed`` as for ``clear``."""
        if await self._open_card(user_id, card_id) is None:
            return None
        return await self._end(user_id, card_id, GIVE_UP_LINE)

    async def later(self, user_id: str, card_id: str) -> StuckCard | None:
        """Later, on a Sign-in card: the task ends for now and the bot says it left the site for later.
        ``NotSignInCard`` on any other card; ``None`` / ``CardClosed`` as for ``clear``."""
        opened = await self._open_card(user_id, card_id)
        if opened is None:
            return None
        if not opened.sign_in:
            raise NotSignInCard(card_id)
        return await self._end(user_id, card_id, LATER_LINE.format(host=opened.host))

    async def _end(self, user_id: str, card_id: str, line: str) -> StuckCard:
        card = await self._close(user_id, card_id, CardState.GIVEN_UP)
        self._control.give_back(card.bot_id)
        await post_bot_line(self._talk, self._events, user_id, card, line, kind="text")
        await publish_card(self._events, user_id, card)
        await self._turns.settle(user_id, card.bot_id)
        return card

    async def open_in_main_browser(self, user_id: str, card_id: str) -> StuckCard | None:
        """Use my main Brave: open the card's address there (piece A: open only, D-A3).

        ``None`` when the card is not the user's. ``CardClosed`` when it is no
        longer open, ``NoAddress`` when it has no address, and ``UrlBlocked`` when
        the address check refuses it. ``DeskUnavailable`` when the keeper can't
        open it."""
        card = await self._open_card(user_id, card_id)
        if card is None:
            return None
        if not card.url:
            raise NoAddress(card_id)
        checked = check_url(card.url)
        try:
            await self._main_browser.open(card.bot_id, checked)
        except DeskUnavailable:
            logger.warning("The main browser could not open Stuck card %s of bot %s", card_id, card.bot_id,
                           exc_info=True)
            raise
        marked = await self._store.mark_main_opened(user_id, card_id)
        if marked is None:
            raise CardClosed(card_id)
        await publish_card(self._events, user_id, marked)
        return marked

    async def _announce_closed(self, user_id: str, card: StuckCard) -> None:
        """Tell the face the card is closed, then settle the status (R9). The settle runs even when
        the frame can't be published."""
        try:
            await publish_card(self._events, user_id, card)
        finally:
            await self._turns.settle(user_id, card.bot_id)

    async def _open_card(self, user_id: str, card_id: str) -> StuckCard | None:
        """The user's card, while it is open. ``None`` when it is not theirs."""
        card = await self._store.get(user_id, card_id)
        if card is not None and card.state is not CardState.OPEN:
            raise CardClosed(card_id)
        return card

    async def _close(self, user_id: str, card_id: str, state: CardState, *,
                     answer_item_id: str | None = None) -> StuckCard:
        """Only one press wins. ``None`` here means another press closed the card first."""
        card = await self._store.close(user_id, card_id, state, answer_item_id=answer_item_id)
        if card is None:
            raise CardClosed(card_id)
        return card

    async def _post_continue_line(self, user_id: str, card: StuckCard, text: str) -> Message:
        """R6: the continue text is your own line, carrying the card's taint."""
        line = await self._talk.add_message(user_id, card.thread_id, role="user", body=text,
                                            tainted=card.tainted, kind="card_answer")
        await self._events.publish(user_id, {
            "type": "message", "thread_id": card.thread_id, "message": message_out(line),
        })
        return line
