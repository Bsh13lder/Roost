"""Stuck cards (stuck flow §2, R6–R9): frozen dataclasses for the store and the
run, plus the one pydantic wire shape the face gets (no ``user_id``, no
``request``)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from roost.desk.stuck import Block, BlockReason, host_of_url


# How a card was cleared (stuck flow R10, final review M7): "gave_back" is Give it back and Done, carry on,
# after the user took control or used their main Brave; "try_again" is Try again, which the user pressed
# without taking control. The two post different lines, and "gave_back" is the default.
ClearHow = Literal["try_again", "gave_back"]
DEFAULT_CLEAR_HOW: ClearHow = "gave_back"


class CardState(str, Enum):
    OPEN = "open"
    CLEARED = "cleared"
    GIVEN_UP = "given_up"
    BLOCKED = "blocked"
    REPLIED = "replied"     # you answered it in the chat (roost/stuck/typed_reply.py); stored as v38's ``replied``


@dataclass(frozen=True)
class CardDraft:
    """What a stopped run hands the store: the block, and the request to carry on with."""

    bot_id: str
    thread_id: str
    work_item_id: str | None
    block: Block
    request: str
    tainted: bool
    sign_in: bool = False       # a Sign-in card: a sign-in page on the bot's Linux computer


@dataclass(frozen=True)
class StuckCard:
    id: str
    user_id: str
    bot_id: str
    thread_id: str
    work_item_id: str | None
    reason: BlockReason
    url: str
    note: str
    request: str
    suggest_main_browser: bool
    tainted: bool
    main_opened: bool
    state: CardState
    answer_item_id: str | None
    created_at: str
    closed_at: str | None
    sign_in: bool = False       # a Sign-in card (Open sign-in · Check again · Later)
    secret_field: str | None = None   # B3: "password" | "code": the card shows a masked field

    @property
    def host(self) -> str:
        return host_of_url(self.url)

    def is_met_again_by(self, block: Block) -> bool:
        """Rung 4 (R12, R13): ``block`` is this card's own block, met again by the run that continued it.

        It needs the same site and the same reason, and the bot asking for help is never "the same":
        the user cleared a check and the site now wants a sign-in, or the bot asks for something new,
        and both are progress. A card finished in the user's main Brave never is: the bot is told not
        to read that page again, so a block it meets there is a new problem to show."""
        return (
            bool(block.host) and block.host == self.host and block.reason == self.reason
            and block.reason != "asked" and not self.main_opened
            and not block.field and not self.secret_field     # B3: a password then a code is progress
        )


class StuckCardOut(BaseModel):
    """The card's wire shape: ``GET /api/stuck`` and the ``stuck_card`` frame."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    bot_id: str
    thread_id: str
    reason: BlockReason
    host: str
    url: str
    note: str
    suggest_main_browser: bool
    tainted: bool
    main_opened: bool
    state: CardState
    created_at: str
    closed_at: str | None
    sign_in: bool = False
    secret_field: str | None = None


def stuck_card_out(card: StuckCard) -> StuckCardOut:
    return StuckCardOut(
        id=card.id, bot_id=card.bot_id, thread_id=card.thread_id, reason=card.reason, host=card.host,
        url=card.url, note=card.note, suggest_main_browser=card.suggest_main_browser, tainted=card.tainted,
        main_opened=card.main_opened, state=card.state, created_at=card.created_at, closed_at=card.closed_at,
        sign_in=card.sign_in, secret_field=card.secret_field,
    )


class CardClosed(Exception):
    """The card is no longer open (cleared, given up or blocked): the route answers 409."""


class NoAddress(Exception):
    """The card has no web address to open: the route answers 400."""


class NotSignInCard(Exception):
    """Open sign-in on a card that is not a Sign-in card: the route answers 400."""


class KeepAnswerNeeded(Exception):
    """Give it back on a Sign-in card with no answer to "Keep me signed in on this computer?" (the route answers 400,
    the card stays open): otherwise the login would stay in the bot's browser with no Vault row to sign out of."""
