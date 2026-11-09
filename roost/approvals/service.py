"""``ApprovalService``: the Ask card's buttons (approval plan Task 8; Design §4.2).

``TurnRunner`` opens cards, and this service closes them, the way ``StuckService`` does.

- ``yes`` / ``yes_session``: the card closes as ``approved`` FIRST (of two presses exactly one wins),
  then the one stored step runs through ``ApprovedCalls``. The outcome is posted as an
  ``approval_result`` message, your ``Yes: …`` line as a ``card_answer`` line, and a ``card_answer``
  item carries the task on. ``yes_session`` also starts a session OK for that folder (reads only).
- A Proposal (``kind="plan"``): ``accept`` runs every listed step in order (reason ``plan_accepted``), each
  through the same checks as a single Yes, and stops at the first one that fails; ``decline`` changes
  nothing and queues nothing; ``edit`` posts your words as a new message of your own.
- ``no``: nothing runs; ``No: …`` is your line and the item tells the bot to carry on without it. On a Send card
  (``send_card.py``) it is Don't send: "Not sent", and the bot waits for what to change.
- ``edit`` (a Send card's Change it…, owner 2026-11-03): the card closes as ``edited`` and your words are posted as your
  own message, as a Proposal's Edit does, so the bot retypes them and its Send asks again.

The frame is published and the bot's status settles whatever happens after the card closed."""

from __future__ import annotations

import logging
from uuid import uuid4

from roost.approvals.announce import post_result, post_user_line, publish_card
from roost.approvals.executor import ApprovedCalls
from roost.approvals.models import ApprovalCard, BadAnswer, CardClosed, CardState, StepOutcome
from roost.approvals.sessions import SessionOks
from roost.approvals.store import ApprovalStore
from roost.choices.decisions import DecisionBook
from roost.approvals.send_card import is_send_card
from roost.approvals.texts import (
    ACCEPT_LINE, APPROVED_FAILED_TEXT, BAD_ANSWER_TEXT, DECLINE_LINE, EDIT_NEEDS_TEXT, NO_LINE, SEND_NO_LINE,
    SESSION_NOT_OFFERED_TEXT, STEP_FAILED_LINE, YES_LINE, YES_SESSION_LINE,
)
from roost.choices.models import ChoiceView, choice_of
from roost.choices.texts import (
    CHOICE_OUT_OF_RANGE_TEXT, DISMISS_LINE, DISMISSED_ANSWER, OWN_LINE, OWN_NEEDS_TEXT, OWN_NOT_OFFERED_TEXT,
    PICK_LINE,
)
from roost.constants import APPROVAL_EDIT_TEXT_MAX, CHOICE_OWN_ANSWER_MAX_CHARS
from roost.memory.service import MemoryRefused
from roost.events.hub import EventHub
from roost.talk.runner import TurnRunner
from roost.talk.notices import post_notice
from roost.talk.store import TalkStore, message_out
from roost.talk.carry import joined, parked_site_entries
from roost.talk.new_site import approved_scope
from roost.work.models import ORIGIN_CARD, ORIGIN_YOU, WorkDraft, WorkKind

logger = logging.getLogger(__name__)

ASK_ANSWERS = frozenset({"yes", "yes_session", "no"})
SEND_ANSWERS = frozenset({"yes", "no", "edit"})        # a Send card: Send · Don't send · Change it…
PLAN_ANSWERS = frozenset({"accept", "decline", "edit"})


def _choice_words(view: ChoiceView, answer: str, text: str | None, choice: int | None) -> tuple[str, str]:
    """``(your line, the decision's answer)`` for an options card, or ``BadAnswer``. Only the STORED option text
    or your own bounded words ever become either."""
    if answer == "no":
        return DISMISS_LINE.format(question=view.question), DISMISSED_ANSWER
    if answer == "pick":
        if choice is None or not 0 <= choice < len(view.options):
            raise BadAnswer(CHOICE_OUT_OF_RANGE_TEXT)
        picked = view.options[choice]
        return PICK_LINE.format(answer=picked), picked
    if answer != "own":
        raise BadAnswer(BAD_ANSWER_TEXT)
    if not view.own:
        raise BadAnswer(OWN_NOT_OFFERED_TEXT)
    words = (text or "").strip()
    if not 1 <= len(words) <= CHOICE_OWN_ANSWER_MAX_CHARS:
        raise BadAnswer(OWN_NEEDS_TEXT)
    return OWN_LINE.format(answer=words), words


class ApprovalService:
    def __init__(self, store: ApprovalStore, talk: TalkStore, events: EventHub, turns: TurnRunner,
                 executor: ApprovedCalls, sessions: SessionOks, decisions: DecisionBook | None = None) -> None:
        self._decisions = decisions
        self._store = store
        self._talk = talk
        self._events = events
        self._turns = turns
        self._executor = executor
        self._sessions = sessions

    async def list_open(self, user_id: str) -> tuple[ApprovalCard, ...]:
        return await self._store.list_open(user_id)

    async def get(self, user_id: str, card_id: str) -> ApprovalCard | None:
        return await self._store.get(user_id, card_id)

    async def answer(self, user_id: str, card_id: str, answer: str, text: str | None = None,
                     choice: int | None = None) -> ApprovalCard | None:
        """``None`` when the card is not the user's; ``CardClosed`` when it was answered already;
        ``BadAnswer`` (a plain sentence) when the answer does not fit the card."""
        card = await self._store.get(user_id, card_id)
        if card is None:
            return None
        if card.state is not CardState.OPEN:
            raise CardClosed(card_id)
        view = choice_of(card)
        if view is not None:
            return await self._answer_choice(user_id, card, view, answer, text, choice)
        words = self._check(card, answer, text)
        if card.kind == "plan":
            return await self._answer_plan(user_id, card, answer, words)
        return await self._answer_ask(user_id, card, answer, words)

    @staticmethod
    def _check(card: ApprovalCard, answer: str, text: str | None) -> str | None:
        """Raise ``BadAnswer`` before the card closes if the answer does not fit it. Returns the Edit words."""
        allowed = PLAN_ANSWERS if card.kind != "ask" else SEND_ANSWERS if is_send_card(card) else ASK_ANSWERS
        if answer not in allowed:
            raise BadAnswer(BAD_ANSWER_TEXT)
        if answer == "yes_session" and not card.session_offer:
            raise BadAnswer(SESSION_NOT_OFFERED_TEXT)
        if answer != "edit":
            return None
        words = (text or "").strip()
        if not 1 <= len(words) <= APPROVAL_EDIT_TEXT_MAX:
            raise BadAnswer(EDIT_NEEDS_TEXT)
        return words

    async def _answer_choice(self, user_id: str, card: ApprovalCard, view: ChoiceView, answer: str,
                             text: str | None, choice: int | None) -> ApprovalCard:
        """An options card: ``pick`` (an index into the STORED options), ``own`` (your words, only when the card
        allows them) or ``no`` (Dismiss). The answer is checked before the card closes and built from stored
        text only; the decision is saved after the card closed, whichever press won."""
        line, decided = _choice_words(view, answer, text, choice)
        item_id = str(uuid4())
        state = CardState.DECLINED if answer == "no" else CardState.APPROVED
        closed = await self._store.close(user_id, card.id, state, answer_item_id=item_id)
        if closed is None:
            raise CardClosed(card.id)     # another press won
        try:
            posted = await post_user_line(self._talk, self._events, user_id, closed, line, tainted=closed.tainted)
            await self._record_decision(user_id, closed, view.question, decided)
            await self._turns.submit(user_id, WorkDraft(
                bot_id=closed.bot_id, thread_id=closed.thread_id, kind=WorkKind.CARD_ANSWER, origin=ORIGIN_CARD,
                body=posted.body, tainted=closed.tainted, message_id=posted.id,
                link_scope=await self._carried(user_id, closed)), item_id=item_id)
            return closed
        except Exception:
            logger.exception("Answering options card %s of bot %s failed after the card closed", card.id,
                             card.bot_id)
            raise
        finally:
            await self._announce_closed(user_id, closed.id)

    async def _record_decision(self, user_id: str, card: ApprovalCard, question: str, answer: str) -> None:
        if self._decisions is None:
            return
        try:
            await self._decisions.record(user_id, card.bot_id, question, answer, tainted=card.tainted)
        except MemoryRefused:
            logger.warning("A decision for bot %s was not saved: the memory service refused it", card.bot_id)

    async def _answer_plan(self, user_id: str, card: ApprovalCard, answer: str, words: str | None) -> ApprovalCard:
        """Accept runs the plan; Decline changes nothing; Edit posts your words as a new message."""
        item_id = str(uuid4())
        state = {"accept": CardState.APPROVED, "decline": CardState.DECLINED, "edit": CardState.EDITED}[answer]
        closed = await self._store.close(user_id, card.id, state, answer_item_id=item_id)
        if closed is None:
            raise CardClosed(card.id)     # another press won
        try:
            if answer == "accept":
                return await self._accept(user_id, closed, item_id)
            if answer == "edit":
                return await self._edit(user_id, closed, item_id, words or "")
            await post_user_line(self._talk, self._events, user_id, closed, DECLINE_LINE, tainted=False)
            return closed
        except Exception:
            logger.exception("Answering Proposal %s of bot %s failed after the card closed", card.id, card.bot_id)
            raise
        finally:
            await self._announce_closed(user_id, closed.id)

    async def _accept(self, user_id: str, card: ApprovalCard, item_id: str) -> ApprovalCard:
        """Every step in order, each through the same checks as a single Yes, stopping at the first failure."""
        texts: list[str] = []
        tainted = card.tainted
        for number, step in enumerate(card.steps, start=1):
            outcome = await self._executor.run(user_id, card, step, reason="plan_accepted")
            texts.append(outcome.text)
            tainted = tainted or outcome.tainted
            if not outcome.ok:
                texts.append(STEP_FAILED_LINE.format(n=number, reason=outcome.text))
                card = await self._store.mark_failed(user_id, card.id) or card
                await self._say_why(user_id, card, STEP_FAILED_LINE.format(n=number, reason=outcome.text))
                break
        await post_result(self._talk, user_id, card, "\n".join(texts), tainted=tainted)
        posted = await post_user_line(self._talk, self._events, user_id, card,
                                      ACCEPT_LINE.format(n=len(card.steps)), tainted=tainted)
        await self._turns.submit(user_id, WorkDraft(
            bot_id=card.bot_id, thread_id=card.thread_id, kind=WorkKind.CARD_ANSWER, origin=ORIGIN_CARD,
            body=posted.body, tainted=tainted, message_id=posted.id,
            link_scope=await self._carried(user_id, card)), item_id=item_id)
        return card

    async def _edit(self, user_id: str, card: ApprovalCard, item_id: str, words: str) -> ApprovalCard:
        message = await self._talk.add_message(user_id, card.thread_id, role="user", body=words)
        await self._events.publish(user_id, {"type": "message", "thread_id": card.thread_id,
                                             "message": message_out(message)})
        await self._turns.submit(user_id, WorkDraft(
            bot_id=card.bot_id, thread_id=card.thread_id, kind=WorkKind.MESSAGE, origin=ORIGIN_YOU,
            body=words, message_id=message.id), item_id=item_id)
        return card

    async def _answer_ask(self, user_id: str, card: ApprovalCard, answer: str, words: str | None) -> ApprovalCard:
        item_id = str(uuid4())
        state = {"no": CardState.DECLINED, "edit": CardState.EDITED}.get(answer, CardState.APPROVED)
        closed = await self._store.close(user_id, card.id, state, answer_item_id=item_id)
        if closed is None:
            raise CardClosed(card.id)     # another press won
        try:
            if answer == "edit":
                return await self._edit(user_id, closed, item_id, words or "")
            return await self._finish(user_id, closed, answer, item_id)
        except Exception:
            logger.exception("Answering Ask card %s of bot %s failed after the card closed", card.id, card.bot_id)
            raise
        finally:
            await self._announce_closed(user_id, closed.id)

    async def _finish(self, user_id: str, card: ApprovalCard, answer: str, item_id: str) -> ApprovalCard:
        title = card.steps[0].title if card.steps else ""
        outcome: StepOutcome | None = None
        if answer != "no" and card.steps:
            outcome = await self._executor.run(user_id, card, card.steps[0])
            if not outcome.ok:
                card = await self._store.mark_failed(user_id, card.id) or card
                await self._say_why(user_id, card, APPROVED_FAILED_TEXT.format(reason=outcome.text))
            elif answer == "yes_session":
                self._start_session(user_id, card)
            await post_result(self._talk, user_id, card, outcome.text, tainted=card.tainted or outcome.tainted)
        no_line = SEND_NO_LINE if is_send_card(card) else NO_LINE
        line = (no_line if answer == "no" else YES_SESSION_LINE if answer == "yes_session" else YES_LINE)
        tainted = card.tainted or (outcome is not None and outcome.tainted)
        posted = await post_user_line(self._talk, self._events, user_id, card, line.format(title=title),
                                      tainted=tainted)
        opened = outcome is not None and outcome.ok and card.steps
        await self._turns.submit(user_id, WorkDraft(
            bot_id=card.bot_id, thread_id=card.thread_id, kind=WorkKind.CARD_ANSWER, origin=ORIGIN_CARD,
            body=posted.body, tainted=tainted, message_id=posted.id,
            link_scope=joined(approved_scope(card.steps[0]) if opened else (), await self._carried(user_id, card))),
            item_id=item_id)
        return card

    async def _carried(self, user_id: str, card: ApprovalCard) -> tuple[str, ...]:
        """The sites the parked run opened itself, for the run that carries on (``roost/talk/carry.py``)."""
        return await parked_site_entries(self._turns.queue, user_id, card.work_item_id)

    async def _say_why(self, user_id: str, card: ApprovalCard, line: str) -> None:
        """B2: a Yes that didn't run says why under the card ("It didn't run: …"). The reason is the step's own
        sentence (a screen step's is always one of the runner's fixed sentences), never page or file text."""
        await post_notice(self._talk, self._events, user_id, card.thread_id, line)

    def _start_session(self, user_id: str, card: ApprovalCard) -> None:
        arguments = card.steps[0].arguments
        grant_id, label = arguments.get("grant_id"), arguments.get("folder")
        if isinstance(grant_id, str) and isinstance(label, str):
            self._sessions.grant(user_id, card.bot_id, grant_id, label)

    async def _announce_closed(self, user_id: str, card_id: str) -> None:
        """Tell the face, then settle the bot's status (Asking you ends). The settle runs even when the
        frame can't be published."""
        card = await self._store.get(user_id, card_id)
        try:
            if card is not None:
                await publish_card(self._events, user_id, card)
        finally:
            if card is not None:
                await self._turns.settle(user_id, card.bot_id)
