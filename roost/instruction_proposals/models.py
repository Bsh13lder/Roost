"""The instructions card's shapes: the sealed payload, a stored proposal, a run's request and the card's view."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from roost.constants import INSTRUCTION_WHY_MAX, MAX_BOT_INSTRUCTIONS_LENGTH

ProposalState = Literal["open", "accepted", "declined"]


class InstructionPayload(BaseModel):
    """What ``instruction_proposals.payload`` seals: the instructions the card was made from, the new ones and why."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    before: str = Field(max_length=MAX_BOT_INSTRUCTIONS_LENGTH)
    after: str = Field(min_length=1, max_length=MAX_BOT_INSTRUCTIONS_LENGTH)
    why: str = Field(default="", max_length=INSTRUCTION_WHY_MAX)


@dataclass(frozen=True)
class InstructionProposal:
    id: str
    user_id: str
    bot_id: str
    payload: InstructionPayload
    tainted: bool
    from_routine: bool
    state: ProposalState
    thread_id: str
    message_id: str | None
    created_at: str
    decided_at: str | None


@dataclass(frozen=True)
class ProposalRequest:
    """One proposal from a run: the bot's own new text and why, the chat it is in, and the run's marks."""
    user_id: str
    bot_id: str
    new_text: str
    why: str
    thread_id: str
    tainted: bool
    from_routine: bool


@dataclass(frozen=True)
class ProposalView:
    proposal: InstructionProposal
    diff: tuple[dict, ...]       # line_diff(before, after)
    stale: bool                  # the bot's instructions are no longer the ones the card was made from
