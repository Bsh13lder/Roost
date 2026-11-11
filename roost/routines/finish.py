"""``finish_routine``: a routine ends when its job is done (owner, 2026-11-11,
docs/plans/2026-11-11-roost-routine-finish.md).

In a routine's own run (a page-watch change run included, tainted as it is) the bot calls ``finish_routine`` with a
short reason. It names no routine: the one that started this run is the only one it may finish, read from the run's
own thread (``RoutineStore.for_thread``). Finishing only reduces what runs, so the gate allows it when tainted and
puts no Ask card in front of it (``tool_specs.py``). The routine is paused and marked finished (schema v48), one
``routine_finished`` line in the bot's chat offers Resume and Delete now (``finished.py``), and the scheduler
deletes it ``ROUTINE_FINISHED_KEEP_DAYS`` later unless the user resumed it. Outside a routine run the tool refuses
and points at the direct tools."""

from __future__ import annotations

import html
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import ROUTINE_FINISHED_KEEP_DAYS, ROUTINE_FINISHED_REASON_MAX
from roost.records.tool_text import ToolText
from roost.routines.finished import FINISHED_KIND
from roost.routines.models import Routine
from roost.routines.service import NoSuchRoutine, Refused, RoutineService
from roost.routines.store import RoutineStore
from roost.routines.tool_specs import FINISH_ROUTINE
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome

__all__ = ["FINISHED_KIND", "FINISH_ROUTINE", "NOT_ROUTINE_RUN_TEXT", "RoutineFinish"]

NOT_ROUTINE_RUN_TEXT: Final = (
    "Refused: finish_routine works only inside a routine's own run, for the routine that started it. In the user's "
    "own chat, pause_routine or delete_routine does what they ask."
)
BAD_ARGS_TEXT: Final = "Refused: finish_routine needs a short reason (one line)."
FINISHED_TEXT: Final = (
    "Finished routine “{name}”: it is paused and will be deleted in {days} days unless the user resumes it. Say so in "
    "one line of your reply."
)
ACTIVITY_TEXT: Final = "finishing this routine"


class FinishArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: ToolText = Field(min_length=1, max_length=ROUTINE_FINISHED_REASON_MAX)


class RoutineFinish:
    """The ``finish_routine`` handler: one tool, for the routine whose run this is."""

    names: frozenset[str] = frozenset({FINISH_ROUTINE})

    def __init__(self, routines: RoutineStore, service: RoutineService) -> None:
        self._routines = routines
        self._service = service

    def activity(self, name: str) -> str:
        return ACTIVITY_TEXT

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        try:
            args = FinishArgs.model_validate(arguments)
        except ValidationError:
            return ToolOutcome(BAD_ARGS_TEXT, failed=True)
        routine = await self._own_run_routine(ctx)
        if routine is None:
            return ToolOutcome(NOT_ROUTINE_RUN_TEXT, failed=True)
        try:
            finished = await self._service.finish(ctx.user_id, routine.id, args.reason, tainted=ctx.tainted)
        except Refused as refused:
            return ToolOutcome(f"Refused: {html.escape(refused.text, quote=True)}", failed=True)
        except NoSuchRoutine:
            return ToolOutcome(NOT_ROUTINE_RUN_TEXT, failed=True)
        return ToolOutcome(FINISHED_TEXT.format(name=html.escape(finished.name, quote=True),
                                                days=ROUTINE_FINISHED_KEEP_DAYS))

    async def _own_run_routine(self, ctx: RecordContext) -> Routine | None:
        """The routine that started this run: a routine run, in that routine's own run-log thread, of this bot."""
        if not ctx.from_routine or ctx.thread_id is None:
            return None
        routine = await self._routines.for_thread(ctx.user_id, ctx.thread_id)
        if routine is None or routine.bot_id != ctx.bot_id:
            return None
        return routine
