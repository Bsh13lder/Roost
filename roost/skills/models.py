"""Skill shapes: the stored skill, the user's or a bot's draft, a patch, and a bot's proposal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from roost.bots.limits import fits_on_one_line
from roost.bots.redact import find_secret_kinds
from roost.constants import SKILL_BODY_MAX, SKILL_NAME_MAX, SKILL_USE_WHEN_MAX
from roost.skills.texts import BODY_BAD, FIELD_WORDS, NAME_BAD, USE_WHEN_BAD, secret_sentence

SkillOrigin = Literal["user", "bot", "file"]
ProposalAction = Literal["create", "change"]
ProposalState = Literal["open", "saved", "declined"]
_PYDANTIC_PREFIX = "Value error, "


@dataclass(frozen=True)
class Skill:
    id: str
    user_id: str
    name: str
    use_when: str
    body: str
    origin: SkillOrigin
    tainted: bool
    created_by_bot: str | None
    revision: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SkillForBot:
    skill: Skill
    on: bool


def check_line(value: str, limit: int, sentence: str) -> str:
    text = value.strip()
    if not text or len(text) > limit or not fits_on_one_line(text):
        raise ValueError(sentence)
    return text


def check_steps(value: str) -> str:
    text = value.strip()
    if not text or len(text) > SKILL_BODY_MAX:
        raise ValueError(BODY_BAD)
    return text


def _refuse_secrets(fields: dict[str, str | None]) -> None:
    found = {field: find_secret_kinds(text) for field, text in fields.items() if text}
    flagged = [field for field, kinds in found.items() if kinds]
    if flagged:
        kinds = list(dict.fromkeys(kind for field in flagged for kind in found[field]))
        raise ValueError(secret_sentence(kinds, [FIELD_WORDS[field] for field in flagged]))


class _SkillText(BaseModel):
    @field_validator("name", check_fields=False)
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return None if value is None else check_line(value, SKILL_NAME_MAX, NAME_BAD)

    @field_validator("use_when", check_fields=False)
    @classmethod
    def _use_when(cls, value: str | None) -> str | None:
        return None if value is None else check_line(value, SKILL_USE_WHEN_MAX, USE_WHEN_BAD)

    @field_validator("body", check_fields=False)
    @classmethod
    def _body(cls, value: str | None) -> str | None:
        return None if value is None else check_steps(value)

    @model_validator(mode="after")
    def _no_secrets(self):
        _refuse_secrets({"name": self.name, "use_when": self.use_when, "body": self.body})
        return self


class SkillDraft(_SkillText):
    """A whole skill: one-line name and Use when, Markdown steps, no secret."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    use_when: str
    body: str


class SkillPatch(_SkillText):
    """Some of a skill's fields; ``None`` keeps the stored one."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str | None = None
    use_when: str | None = None
    body: str | None = None

    def is_empty(self) -> bool:
        return self.name is None and self.use_when is None and self.body is None


class SkillProposalPayload(BaseModel):
    """What a bot proposed, sealed in ``skill_proposals.payload``. A change carries only the fields it changes."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    name: str | None = None
    use_when: str | None = None
    body: str | None = None


@dataclass(frozen=True)
class SkillProposal:
    id: str
    user_id: str
    bot_id: str
    skill_id: str | None
    action: ProposalAction
    payload: SkillProposalPayload
    base_revision: int | None
    tainted: bool
    from_routine: bool
    state: ProposalState
    thread_id: str
    message_id: str | None
    created_at: str
    decided_at: str | None


def plain_error(exc: ValidationError) -> str:
    """The first problem as one plain sentence (our own validators already speak plainly)."""
    first = exc.errors()[0]
    message = str(first.get("msg", "That is not a valid skill."))
    return message.removeprefix(_PYDANTIC_PREFIX)
