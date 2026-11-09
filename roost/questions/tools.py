"""``QuestionTools``: ``note_question(question, default_choice, why?)``.

Arguments are validated (``ToolText``, capped at ``QUESTION_MAX_CHARS``). At most ``QUESTIONS_PER_RUN_MAX`` per run
and ``QUESTIONS_OPEN_PER_BOT_MAX`` open per bot. The row remembers the routine (when the run is a routine's) and the
run's taint. A risky question is refused: the book never stands in for an Ask card."""

from __future__ import annotations

import html
from collections import OrderedDict
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import QUESTION_MAX_CHARS, QUESTIONS_PER_RUN_MAX
from roost.questions.service import QuestionRefused, QuestionService
from roost.questions.texts import BAD_QUESTION_ARGS_TEXT, NOTED_TEXT, RUN_CAP_TEXT
from roost.records.tool_text import ToolText
from roost.routines.store import RoutineStore
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome

_RUNS_REMEMBERED = 256


class NoteQuestionArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question: ToolText = Field(min_length=1, max_length=QUESTION_MAX_CHARS)
    default_choice: ToolText = Field(min_length=1, max_length=QUESTION_MAX_CHARS)
    why: ToolText | None = Field(default=None, max_length=QUESTION_MAX_CHARS)


class QuestionTools:
    names = frozenset({"note_question"})

    def __init__(self, service: QuestionService, routines: RoutineStore) -> None:
        self._service = service
        self._routines = routines
        self._per_run: OrderedDict[tuple[str, str], int] = OrderedDict()

    def activity(self, name: str) -> str:
        return "noting a question"

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        try:
            args = NoteQuestionArgs.model_validate(arguments)
        except ValidationError:
            return ToolOutcome(BAD_QUESTION_ARGS_TEXT)
        thread_id = ctx.thread_id
        if thread_id is None:
            return ToolOutcome("Refused: there is no chat to note this in.")
        key = (ctx.bot_id, ctx.run_id or thread_id)
        if self._per_run.get(key, 0) >= QUESTIONS_PER_RUN_MAX:
            return ToolOutcome(RUN_CAP_TEXT)
        routine = await self._routines.for_thread(ctx.user_id, thread_id) if ctx.from_routine else None
        try:
            await self._service.note(
                ctx.user_id, ctx.bot_id, thread_id, args.question.strip(), args.default_choice.strip(),
                args.why.strip() if args.why else None, routine_id=routine.id if routine else None,
                tainted=ctx.tainted)
        except QuestionRefused as refused:
            return ToolOutcome(html.escape(refused.text, quote=True))
        self._count(key)
        return ToolOutcome(NOTED_TEXT.format(default_choice=html.escape(args.default_choice.strip(), quote=True)),
                           created=True)

    def _count(self, key: tuple[str, str]) -> None:
        self._per_run[key] = self._per_run.get(key, 0) + 1
        self._per_run.move_to_end(key)
        while len(self._per_run) > _RUNS_REMEMBERED:
            self._per_run.popitem(last=False)
