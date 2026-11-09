"""``QuestionService``: note, list, answer, dismiss, and a routine's last answers.

Noting is for NON-urgent questions the bot answers itself with a safe default and carries on (it saves nothing the
user hasn't seen: the default is shown in the book). Answering turns the user's words into their OWN message in the
bot's main chat (untainted, because they typed it), saves it as a decision memory, and queues a normal run so the bot
adapts at once. A question about something risky is refused here: those go through the gate's Ask cards."""

from __future__ import annotations

import json
import logging

from roost.choices.decisions import DecisionBook, is_dangerous
from roost.constants import QUESTION_ANSWER_MAX_CHARS, QUESTION_ANSWERS_IN_PROMPT, QUESTIONS_OPEN_PER_BOT_MAX
from roost.events.hub import EventHub
from roost.memory.service import MemoryRefused
from roost.questions.store import Question, QuestionStore
from roost.questions.texts import (
    ANSWER_MESSAGE, ANSWER_NEEDS_TEXT, FROM_WEB_MARK, NOT_OPEN_TEXT, OPEN_CAP_TEXT, PICKED_LINE, QUESTION_CONTEXT,
    RISKY_TEXT,
)
from roost.routines.models import AnswerLine
from roost.timezones import local_tz
from roost.talk.store import TalkStore, message_out
from roost.work.models import ORIGIN_YOU, WorkDraft, WorkKind

logger = logging.getLogger(__name__)


class NoSuchQuestion(LookupError):
    """The question is not there, or not the user's."""


class QuestionRefused(ValueError):
    """A question or answer that can't be taken; ``text`` is a plain sentence."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


class QuestionClosed(RuntimeError):
    """Another press answered or dismissed it first (409)."""


class QuestionService:
    def __init__(
        self, store: QuestionStore, talk: TalkStore, events: EventHub, turns=None, decisions: DecisionBook | None = None,
    ) -> None:
        self._store = store
        self._talk = talk
        self._events = events
        self._turns = turns
        self._decisions = decisions

    def attach(self, turns) -> None:
        """Late wiring: the runner is built after the book (its routine hooks read the book's answers)."""
        self._turns = turns

    async def note(
        self, user_id: str, bot_id: str, thread_id: str, question: str, default_choice: str, why: str | None,
        *, routine_id: str | None, tainted: bool,
    ) -> Question:
        """Keep a question with the default the bot carries on with. ``QuestionRefused`` for a risky one or a full book."""
        if is_dangerous(question) or is_dangerous(default_choice):
            raise QuestionRefused(RISKY_TEXT)
        if await self._store.count_open(user_id, bot_id) >= QUESTIONS_OPEN_PER_BOT_MAX:
            raise QuestionRefused(OPEN_CAP_TEXT)
        noted = await self._store.note(user_id, bot_id, thread_id, question, default_choice, why,
                                       routine_id=routine_id, tainted=tainted)
        body = json.dumps({"question_id": noted.id, "default_choice": default_choice,
                           "text": PICKED_LINE.format(default_choice=default_choice)})
        message = await self._talk.add_message(user_id, thread_id, "activity", body, tainted=tainted,
                                               kind="question_note", author_bot_id=bot_id)
        await self._events.publish(user_id, {"type": "message", "thread_id": thread_id,
                                             "message": message_out(message)})
        await self._events.publish(user_id, {"type": "questions_changed", "bot_id": bot_id})
        return noted

    async def list(self, user_id: str, *, state: str = "open", bot_id: str | None = None) -> tuple[Question, ...]:
        return await self._store.list(user_id, state=state, bot_id=bot_id)

    async def answer(self, user_id: str, question_id: str, text: str) -> Question:
        """Your answer: sealed, posted as YOUR message in the bot's main chat, saved as a decision, and a run queued."""
        words = text.strip()
        if not 1 <= len(words) <= QUESTION_ANSWER_MAX_CHARS:
            raise QuestionRefused(ANSWER_NEEDS_TEXT if not words else
                                  f"Keep your answer to {QUESTION_ANSWER_MAX_CHARS} characters.")
        current = await self._require(user_id, question_id)
        closed = await self._store.answer(user_id, question_id, words)
        if closed is None:
            raise QuestionClosed(NOT_OPEN_TEXT)
        await self._events.publish(user_id, {"type": "questions_changed", "bot_id": closed.bot_id})
        await self._decide(user_id, current, words)
        await self._send(user_id, current, words)
        return closed

    async def dismiss(self, user_id: str, question_id: str) -> Question:
        await self._require(user_id, question_id)
        closed = await self._store.dismiss(user_id, question_id)
        if closed is None:
            raise QuestionClosed(NOT_OPEN_TEXT)
        await self._events.publish(user_id, {"type": "questions_changed", "bot_id": closed.bot_id})
        return closed

    async def answers_for_routine(self, user_id: str, routine_id: str) -> tuple[AnswerLine, ...]:
        """The routine's last answered questions, for its next run's instructions (quoted there as data)."""
        found = await self._store.answered_for_routine(user_id, routine_id, QUESTION_ANSWERS_IN_PROMPT)
        return tuple(AnswerLine(
            f"{q.question} → {q.answer}" + (f" ({FROM_WEB_MARK})" if q.tainted else ""), q.tainted) for q in found)

    async def _require(self, user_id: str, question_id: str) -> Question:
        found = await self._store.get(user_id, question_id)
        if found is None:
            raise NoSuchQuestion(question_id)
        return found

    async def _decide(self, user_id: str, question: Question, answer: str) -> None:
        """Remember the answer as the user's decision. A risky question is still asked every time (``reusable``)."""
        if self._decisions is None:
            return
        try:
            await self._decisions.record(user_id, question.bot_id, question.question, answer, tainted=question.tainted)
        except MemoryRefused:
            logger.warning("A decision for bot %s was not saved: the memory service refused it", question.bot_id)

    async def _send(self, user_id: str, question: Question, answer: str) -> None:
        if self._turns is None:
            return
        thread, _ = await self._talk.ensure_main_thread(user_id, question.bot_id)
        # The bot wrote the question, so its text never goes inside your message: it is a separate, bot-authored
        # line (tainted when the question was) and the run starts tainted too.
        context = await self._talk.add_message(
            user_id, thread.id, "bot", QUESTION_CONTEXT.format(question=question.question),
            tainted=question.tainted, author_bot_id=question.bot_id)
        await self._events.publish(user_id, {"type": "message", "thread_id": thread.id,
                                             "message": message_out(context)})
        when = question.created_at.astimezone(local_tz()).strftime("%d %b %H:%M")
        body = ANSWER_MESSAGE.format(when=when, answer=answer)
        message = await self._talk.add_message(user_id, thread.id, "user", body)
        await self._events.publish(user_id, {"type": "message", "thread_id": thread.id,
                                             "message": message_out(message)})
        await self._turns.submit(user_id, WorkDraft(
            bot_id=question.bot_id, thread_id=thread.id, kind=WorkKind.MESSAGE, origin=ORIGIN_YOU, body=body,
            tainted=question.tainted, message_id=message.id))
