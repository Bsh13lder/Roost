"""The approved re-run (C3): a card's Yes runs the one act it showed, and only on the same control.

``ComputerUse`` (``roost/computer_use/runner.py``) mixes this in: the page is resolved again, ``same_target`` must
hold, a Send's message must still be the one the card showed, the browser is brought up first when something else is in front, and a ``not_chromium`` refusal gets exactly
one more try.

A browser that stops answering (2026-10-27: a superseded CDP connection) before any input went out gets one more try,
resolved again under the same guards. Once a click, typing or key went out, nothing is sent again: the outcome says
it was sent and counts as run, never "I didn't touch anything"."""

from __future__ import annotations

import logging

from pydantic import BaseModel

from roost.payments.fill import clear_card
from roost.approvals.models import PendingCall, StepOutcome
from roost.computer_use.inputs import TOOL_INPUTS
from roost.computer_use.models import ActResolution, resolution_from_json, same_target
from roost.computer_use.runner_typing import DRAFT_CHANGED_TEXT
from roost.computer_use.screen_grab import ScreenGrabError
from roost.computer_use.vault_login import VAULT_TOOL
from roost.computer_use.texts import (
    _INPUT_WORDS, ASLEEP_TEXT, BROWSER_SILENT_TEXT, CHANGED_TEXT, FOCUS_MOVED_TEXT, HELD_TEXT, MOVED_TEXT,
    NO_SCREEN_TEXT, SENT_THEN_SILENT_TEXT, SENT_WHAT,
)
from roost.constants import CU_RERUN_SETTLE_S
from roost.desk import DeskAsleep, DeskUnavailable, InputRefusedByComputer
from roost.desk.cdp import CdpClientError, CdpReplyError
from roost.llm.types import ToolCallRequested

_SPEND = "spend"
logger = logging.getLogger(__name__)


class ApprovedRerun:
    """Mixed into ``ComputerUse``: every attribute it reads is the runner's."""

    async def rerun(self, step: PendingCall) -> StepOutcome:
        """Run the one act a card approved: resolve the page again, and act only on the same control."""
        try:
            stored = resolution_from_json(step.act or {})
            args = TOOL_INPUTS[step.tool].model_validate(step.arguments)
        except (ValueError, KeyError):
            return StepOutcome(False, NO_SCREEN_TEXT)
        self._audited, self._resolved = False, None
        call = ToolCallRequested(id=f"card-{self._run.run_id}", name=step.tool, arguments=dict(step.arguments))
        text = ""
        try:
            outcome = await self._guarded_rerun(step, stored, args)
            text = outcome.text
            return outcome
        finally:
            await self._audit_refusal(call, True, text)

    async def _guarded_rerun(self, step: PendingCall, stored: ActResolution, args: BaseModel) -> StepOutcome:
        if self._held():
            return StepOutcome(False, HELD_TEXT)
        self._act_epoch = self._epoch()
        refusal = await self._take() or await self._arm()
        if refusal is not None:
            return StepOutcome(False, refusal)
        try:
            outcome = await self._rerun_retrying(step, stored, args)
            if not outcome.ok and stored.commit == _SPEND:
                await self._empty_card_boxes(stored.host)
            return outcome
        except DeskAsleep:
            return StepOutcome(False, ASLEEP_TEXT)
        except DeskUnavailable:
            return self._sent_outcome(step) or StepOutcome(False, NO_SCREEN_TEXT)
        except InputRefusedByComputer as exc:
            return StepOutcome(False, _INPUT_WORDS.get(exc.word, NO_SCREEN_TEXT))
        except (CdpClientError, ScreenGrabError) as exc:
            logger.warning("An approved %s of bot %s met a silent browser: %s", step.tool, self._run.bot_id,
                           type(exc).__name__)
            return self._sent_outcome(step) or StepOutcome(False, BROWSER_SILENT_TEXT)
        finally:
            await self.close()

    async def _rerun_retrying(self, step: PendingCall, stored: ActResolution, args: BaseModel) -> StepOutcome:
        """A dead connection (never one failed command) before any input went out: the whole re-run once more."""
        self._input_sent = False
        try:
            return await self._rerun(step, stored, args)
        except CdpReplyError:
            raise
        except CdpClientError as exc:
            if self._input_sent:
                raise
            logger.warning("An approved %s of bot %s met a dead connection before any input; trying once more: %s",
                           step.tool, self._run.bot_id, type(exc).__name__)
        self._input_sent = False
        return await self._rerun(step, stored, args)

    async def _empty_card_boxes(self, host: str) -> None:
        """A Pay that didn't click (the Pay card, review 2026-11-06): the card Roost typed leaves the page before the
        bot looks again, so it can neither see nor send it. A failure is logged by type only."""
        try:
            emptied = await clear_card(self._desk.page(), self._desk, host)
        except Exception as exc:  # noqa: BLE001 - the Pay outcome stands; only the clean-up failed
            logger.warning("Card boxes of bot %s were not emptied after a Pay that didn't click: %s",
                           self._run.bot_id, type(exc).__name__)
            return
        if emptied:
            logger.info("Emptied %d card boxes of bot %s after a Pay that didn't click", emptied, self._run.bot_id)

    def _sent_outcome(self, step: PendingCall) -> StepOutcome | None:
        """The input went out before the browser went silent: it ran (the card is not failed), and the bot looks."""
        if not self._input_sent:
            return None
        return StepOutcome(True, SENT_THEN_SILENT_TEXT.format(what=SENT_WHAT.get(step.tool, "input")), tainted=True)

    async def _rerun(self, step: PendingCall, stored: ActResolution, args: BaseModel) -> StepOutcome:
        """Brave is brought up first (a fresh computer may have nothing in front), and a ``not_chromium``
        refusal gets exactly one more try: Brave up again, the page resolved again, the same control."""
        await self._ready()
        self._require_hands()
        await self._browser_up(force=False)
        try:
            return await self._rerun_once(step, stored, args)
        except InputRefusedByComputer as exc:
            if exc.word != "not_chromium" or self._input_sent:     # never a second try after an input went out
                raise
            await self._browser_up(force=True)
            return await self._rerun_once(step, stored, args)

    async def _browser_up(self, *, force: bool) -> None:
        if not force and (await self._desk.front_window()).kind == "brave":
            return
        await self._desk.open_app("browser", held=self._held())
        await self._sleep(CU_RERUN_SETTLE_S)
        self._require_hands()

    async def _rerun_once(self, step: PendingCall, stored: ActResolution, args: BaseModel) -> StepOutcome:
        if step.tool == VAULT_TOOL:                      # Vault: passwords: Roost types the login, nothing else
            return await self.vault_rerun(step, stored)
        fresh = await self.resolve(step.tool, args, pinned=stored.target)   # an index names the stored control
        self._resolved = fresh
        if not same_target(stored, fresh) or fresh.refusal:
            return StepOutcome(False, CHANGED_TEXT, tainted=True)
        changed = await self._drafts_still(step.drafts)
        if changed:
            return StepOutcome(False, DRAFT_CHANGED_TEXT.format(label=changed), tainted=True)
        call = ToolCallRequested(id=f"card-{self._run.run_id}", name=step.tool, arguments=dict(step.arguments))
        if not self._audited:
            await self._gate.record_approved(self._run.user_id, self._run.bot_id, step.tool,
                                             dict(step.arguments), reason="approved", tainted=True, act=fresh)
            self._audited = True
        text = await self.act(fresh, call, with_glance=False)
        return StepOutcome(text not in (MOVED_TEXT, FOCUS_MOVED_TEXT, *_INPUT_WORDS.values()), text, tainted=True)
