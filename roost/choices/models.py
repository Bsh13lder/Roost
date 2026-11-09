"""The options card's stored shape: ``ask_choice``'s arguments, its one card step, and the view of it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from roost.approvals.models import ApprovalCard, ArgRow, PendingCall
from roost.constants import (
    CHOICE_OPTION_MAX_CHARS, CHOICE_OPTIONS_MAX, CHOICE_OPTIONS_MIN, CHOICE_QUESTION_MAX_CHARS,
    CHOICE_WHY_MAX_CHARS,
)
from roost.records.tool_text import plain

CHOICE_TOOL = "ask_choice"
_QUESTION_LABEL = "Question"
_SAFE_LABEL = "Safe choice"
_WHY_LABEL = "Why"
_OWN_LABEL = "Own answer"
_EARLIER_LABEL = "Your earlier answer"


def _clean(text: str) -> str:
    return plain(text).strip()


class ChoiceArgs(BaseModel):
    """What the bot asks. Text is plain (the card shows it as text, never HTML) and every length is bounded."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    question: str = Field(min_length=1, max_length=CHOICE_QUESTION_MAX_CHARS)
    options: tuple[str, ...] = Field(min_length=CHOICE_OPTIONS_MIN, max_length=CHOICE_OPTIONS_MAX)
    safe: int = Field(ge=0, lt=CHOICE_OPTIONS_MAX)
    own: bool = True
    why: str = Field(default="", max_length=CHOICE_WHY_MAX_CHARS)

    @field_validator("question", "why", mode="before")
    @classmethod
    def _plain_text(cls, value: Any) -> Any:
        return _clean(value) if isinstance(value, str) else value

    @field_validator("options", mode="before")
    @classmethod
    def _plain_options(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            return value
        return tuple(_clean(v) if isinstance(v, str) else v for v in value)

    @model_validator(mode="after")
    def _within(self) -> "ChoiceArgs":
        if self.safe >= len(self.options):
            raise ValueError("safe is not one of the options")
        for option in self.options:
            if not option or len(option) > CHOICE_OPTION_MAX_CHARS:
                raise ValueError("an option is empty or too long")
        if len(set(o.casefold() for o in self.options)) != len(self.options):
            raise ValueError("options repeat")
        return self


@dataclass(frozen=True)
class ChoiceView:
    question: str
    options: tuple[str, ...]
    safe: int
    own: bool
    why: str


def parse_choice_args(arguments: Any) -> ChoiceArgs | None:
    try:
        return ChoiceArgs.model_validate(arguments)
    except ValidationError:
        return None


def choice_step(args: ChoiceArgs, *, earlier: str | None = None) -> PendingCall:
    """The one step of an options card: every stored argument is a row."""
    rows = [ArgRow("question", _QUESTION_LABEL, args.question)]
    rows += [ArgRow(f"option_{n}", f"Option {n}", text) for n, text in enumerate(args.options, start=1)]
    rows.append(ArgRow("safe", _SAFE_LABEL, args.options[args.safe]))
    rows.append(ArgRow("own", _OWN_LABEL, "Yes" if args.own else "No"))
    if args.why:
        rows.append(ArgRow("why", _WHY_LABEL, args.why))
    if earlier:
        rows.append(ArgRow("earlier", _EARLIER_LABEL, earlier))
    return PendingCall(
        tool=CHOICE_TOOL,
        arguments={"question": args.question, "options": list(args.options), "safe": args.safe,
                   "own": args.own, "why": args.why},
        topic=None, title=args.question, rows=tuple(rows),
    )


def choice_of(card: ApprovalCard) -> ChoiceView | None:
    """The options this card stored, or ``None`` when it is not an options card."""
    if card.kind != "ask" or len(card.steps) != 1 or card.steps[0].tool != CHOICE_TOOL:
        return None
    args = parse_choice_args(card.steps[0].arguments)
    if args is None:
        return None
    return ChoiceView(args.question, args.options, args.safe, args.own, args.why)
