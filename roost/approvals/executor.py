"""``ApprovedCalls``: runs the one stored step of a card after the user's Yes.

It runs EXACTLY what the card stored (never anything the bot says afterwards), audits it (decision
``do``, reason ``approved`` or ``plan_accepted``) before it runs, and returns the outcome. A Mac step re-checks its file
hash, its grant and its bot inside the Mac handler's ``execute``."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from roost.approvals import topics
from roost.approvals.models import ApprovalCard, PendingCall, StepOutcome
from roost.choices.models import CHOICE_TOOL
from roost.constants import CU_ACT_TOOLS
from roost.events.hub import EventHub
from roost.talk.domain_tools import DomainTools, RecordContext
from roost.talk.gate import TAINTED_CHANGE_TEXT, Gate
from roost.talk.new_site import open_card_host
from roost.talk.owner_chat import OWNER_CHAT_OWN_TOOLS, OWNER_CHAT_TOOLS
from roost.talk.store import TalkStore
from roost.talk.tool_catalog import CATALOG

if TYPE_CHECKING:
    from roost.computer_use.reruns import ScreenReruns
    from roost.talk.new_site import PageOpens

logger = logging.getLogger(__name__)

_DIDNT_RUN = "It didn't run. Nothing changed."
FLOOR_IN_PLAN_TEXT = "This step needs its own question, so a plan can't run it."


class ApprovedCalls:
    def __init__(self, domain: DomainTools, gate: Gate, talk: TalkStore, events: EventHub,
                 *, screen: "ScreenReruns | None" = None, pages: "PageOpens | None" = None) -> None:
        self._screen = screen     # C3: approved clicks and keys; None: such a step never runs
        self._pages = pages       # Open cards: an approved new site; None: such a step never runs
        self._domain = domain
        self._gate = gate
        self._talk = talk
        self._events = events

    async def run(self, user_id: str, card: ApprovalCard, step: PendingCall, *,
                  reason: Literal["approved", "plan_accepted"] = "approved") -> StepOutcome:
        """Run one stored step. The rules the gate applies to a run still hold: a card from a tainted run
        never changes anything but the one relaxed Mac edit, and a step that hits the hard floor needs a card
        of its own, never a plan. A card from a tainted run changes nothing but the relaxed Mac edit, the asking
        tools and what your own chat may change (``OWNER_CHAT_TOOLS``: only your own chat parks one)."""
        if step.tool == CHOICE_TOOL:
            return StepOutcome(False, _DIDNT_RUN)   # an options card is answered, never run
        if step.tool in CU_ACT_TOOLS or step.act is not None:
            return await self._screen_step(user_id, card, step, reason)
        if open_card_host(step) is not None:
            return await self._open_step(user_id, card, step, reason)
        if not self._domain.handles(step.tool) or step.tool not in CATALOG:
            return StepOutcome(False, _DIDNT_RUN)
        # Your own chat (owner, 2026-11-03): the gate parks such a tainted change only there, so your Yes runs it.
        relaxed = topics.RELAX_TAINTED_TOOLS | topics.ASK_WHEN_TAINTED_TOOLS | OWNER_CHAT_TOOLS
        if card.tainted and CATALOG[step.tool].kind_for(step.arguments) == "write_change" and step.tool not in relaxed:
            return StepOutcome(False, TAINTED_CHANGE_TEXT)
        if reason == "plan_accepted" and step.floor is not None:
            return StepOutcome(False, FLOOR_IN_PLAN_TEXT)
        await self._gate.record_approved(
            user_id, card.bot_id, step.tool, dict(step.arguments), reason=reason, tainted=card.tainted)
        clean = step.tool in OWNER_CHAT_OWN_TOOLS     # the bot's own things run clean after your Yes, as in your chat
        ctx = RecordContext(user_id=user_id, bot_id=card.bot_id, tainted=card.tainted and not clean,
                            thread_id=card.thread_id)
        try:
            outcome = await self._domain.execute(step.tool, dict(step.arguments), ctx)
        except Exception as exc:
            # The type name only: an error from a file step must never put a path or text in a log.
            logger.warning("An approved %s step of bot %s failed: %s", step.tool, card.bot_id, type(exc).__name__)
            return StepOutcome(False, _DIDNT_RUN)
        return StepOutcome(not outcome.failed, outcome.text, outcome.tainted)

    async def _open_step(self, user_id: str, card: ApprovalCard, step: PendingCall, reason: str) -> StepOutcome:
        """An Open card: the bot's browser opens exactly the stored address. A plan never carries one."""
        if reason == "plan_accepted":
            return StepOutcome(False, FLOOR_IN_PLAN_TEXT)
        if self._pages is None:
            return StepOutcome(False, _DIDNT_RUN)
        await self._gate.record_approved(
            user_id, card.bot_id, step.tool, dict(step.arguments), reason="approved", tainted=card.tainted)
        return await self._pages.open(user_id, card, step)

    async def _screen_step(self, user_id: str, card: ApprovalCard, step: PendingCall, reason: str) -> StepOutcome:
        """C3: a click, typing or key press resolves the page again and acts only on the same control
        (``ComputerUse.rerun``, which writes the audit row). A plan never carries one: it asks on its own."""
        if reason == "plan_accepted":
            return StepOutcome(False, FLOOR_IN_PLAN_TEXT)
        if self._screen is None or step.tool not in CU_ACT_TOOLS or step.act is None:
            return StepOutcome(False, _DIDNT_RUN)
        try:
            return await self._screen.rerun(user_id, card, step)
        except Exception as exc:
            logger.warning("An approved %s step of bot %s failed: %s", step.tool, card.bot_id, type(exc).__name__)
            return StepOutcome(False, _DIDNT_RUN)
