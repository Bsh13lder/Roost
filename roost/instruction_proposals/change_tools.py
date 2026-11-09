"""``update_my_instructions``: a bot changes one section of its own instructions directly (owner, 2026-10-23, A2).

Only in a 1:1 run your own message started (``RecordContext.user_started``, not a routine, in a chat). Anywhere else
it is refused, and the bot offers the change with propose_instructions_update instead. A run that read web content is
refused by the gate outside your own chat; in your own chat the runner hands this a clean context
(``roost/talk/owner_chat.py``), so this check stays the second lock."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import INSTRUCTION_WHY_MAX, MAX_BOT_INSTRUCTIONS_LENGTH
from roost.instruction_proposals.changes import ChangeRefused, ChangeRequest, InstructionChanges
from roost.instruction_proposals.texts import CHANGE_ACTIVITY, CHANGE_BAD_ARGS, CHANGE_TAINTED, change_done
from roost.instruction_proposals.tool_specs import UPDATE_TOOL_NAME
from roost.records.tool_text import ToolText
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome

_SECTION_MAX = 60


class UpdateArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    section: ToolText = Field(min_length=1, max_length=_SECTION_MAX)
    new_text: ToolText = Field(min_length=1, max_length=MAX_BOT_INSTRUCTIONS_LENGTH)
    why: ToolText = Field(min_length=1, max_length=INSTRUCTION_WHY_MAX)


def _may_change(ctx: RecordContext) -> bool:
    return not ctx.tainted and not ctx.from_routine and ctx.user_started and ctx.thread_id is not None


class InstructionChangeTools:
    names = frozenset({UPDATE_TOOL_NAME})

    def __init__(self, changes: InstructionChanges) -> None:
        self._changes = changes

    def activity(self, name: str) -> str:
        return CHANGE_ACTIVITY

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        if not _may_change(ctx) or ctx.thread_id is None:
            return ToolOutcome(CHANGE_TAINTED, failed=True)
        try:
            args = UpdateArgs.model_validate(arguments)
        except ValidationError:
            return ToolOutcome(CHANGE_BAD_ARGS, failed=True)
        try:
            title, _line = await self._changes.change(ChangeRequest(
                user_id=ctx.user_id, bot_id=ctx.bot_id, thread_id=ctx.thread_id, section=args.section.strip(),
                new_text=args.new_text, why=args.why.strip()))
        except ChangeRefused as refused:
            return ToolOutcome(f"Refused: {refused}", failed=True)
        return ToolOutcome(change_done(title))
