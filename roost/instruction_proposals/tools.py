"""``propose_instructions_update``: every bot may offer new instructions for ITSELF on a card. The tool takes no bot
name (the run's own bot is the only one it can name) and writes nothing: the user's Accept does.

Like the skill and routine proposals it only stores a proposal, so the gate's tainted-write rule does not stop it
and approval modes ask no second card; a run that read web content gets its card marked instead."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import INSTRUCTION_WHY_MAX, MAX_BOT_INSTRUCTIONS_LENGTH
from roost.instruction_proposals.models import ProposalRequest
from roost.instruction_proposals.service import InstructionProposalRefused, InstructionProposalService
from roost.instruction_proposals.texts import ACTIVITY, ASKED, BAD_ARGS, NO_CHAT
from roost.instruction_proposals.tool_specs import TOOL_NAME
from roost.records.tool_text import ToolText
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome


class ProposeArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    new_text: ToolText = Field(min_length=1, max_length=MAX_BOT_INSTRUCTIONS_LENGTH)
    why: ToolText = Field(min_length=1, max_length=INSTRUCTION_WHY_MAX)


class InstructionTools:
    names = frozenset({TOOL_NAME})

    def __init__(self, service: InstructionProposalService) -> None:
        self._service = service

    def activity(self, name: str) -> str:
        return ACTIVITY

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        try:
            args = ProposeArgs.model_validate(arguments)
        except ValidationError:
            return ToolOutcome(BAD_ARGS)
        if ctx.thread_id is None:
            return ToolOutcome(f"Refused: {NO_CHAT}")
        try:
            await self._service.propose(ProposalRequest(
                user_id=ctx.user_id, bot_id=ctx.bot_id, new_text=args.new_text, why=args.why.strip(),
                thread_id=ctx.thread_id, tainted=ctx.tainted, from_routine=ctx.from_routine))
        except InstructionProposalRefused as refused:
            return ToolOutcome(f"Refused: {refused.text}")
        return ToolOutcome(ASKED)
