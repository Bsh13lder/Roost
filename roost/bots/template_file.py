"""A shared bot file, ``<name>.roost-bot.json`` (S1.7).

It holds name, job, instructions and look, and nothing else: never chats,
records, logins, the computer or model choices (the format has no field for
them). Sharing refuses text that looks like a secret. Reading a file only
fills the New bot form; nothing is created until the user clicks Create."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import (
    BaseModel, ConfigDict, Field, SerializerFunctionWrapHandler, ValidationError, field_validator, model_serializer,
)

from roost.bots.limits import fits_on_one_line
from roost.bots.models import AvatarScreen, AvatarShape, Bot, BotRole
from roost.bots.redact import find_secret_kinds
from roost.constants import (
    AVATAR_COLOR_PATTERN, BOT_NAME_PATTERN, DEFAULT_ROBOT_SCREEN, MAX_BOT_INSTRUCTIONS_LENGTH, MAX_BOT_JOB_LENGTH,
    MAX_BOT_NAME_LENGTH, TEMPLATE_SKILLS_MAX,
)
from roost.skills.template_skills import TOO_MANY_SKILLS, TemplateSkill

TEMPLATE_SUFFIX = ".roost-bot.json"


class TemplateFileError(ValueError):
    """The file isn't a Roost bot file; the message says why, plainly."""


class SecretInTemplate(ValueError):
    """Share refused: a field looks like it holds a key or a password."""


class TemplateAvatar(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    shape: AvatarShape
    color: str = Field(pattern=AVATAR_COLOR_PATTERN)
    screen: AvatarScreen = DEFAULT_ROBOT_SCREEN   # a file shared before the robots has none
    role: BotRole | None = None                   # a file shared before the roles has none

    @model_serializer(mode="wrap")
    def _no_empty_role(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """A file with no role leaves it out, so a Roost from before the roles still reads it."""
        data = handler(self)
        return {key: value for key, value in data.items() if not (key == "role" and value is None)}


class TemplateFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    format: Literal["roost-bot"]
    version: Literal[1]
    name: str = Field(min_length=1, max_length=MAX_BOT_NAME_LENGTH, pattern=BOT_NAME_PATTERN)
    job: str = Field(min_length=1, max_length=MAX_BOT_JOB_LENGTH)
    instructions: str = Field(default="", max_length=MAX_BOT_INSTRUCTIONS_LENGTH)
    avatar: TemplateAvatar
    skills: tuple[TemplateSkill, ...] = ()        # Skills: a file shared before skills has none

    @field_validator("skills", mode="before")
    @classmethod
    def _few_skills(cls, value: Any) -> Any:
        if isinstance(value, (list, tuple)) and len(value) > TEMPLATE_SKILLS_MAX:
            raise ValueError(TOO_MANY_SKILLS)
        return value

    @model_serializer(mode="wrap")
    def _no_empty_skills(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """A file with no skills leaves the key out, so a Roost from before skills still reads it."""
        data = handler(self)
        return {key: value for key, value in data.items() if not (key == "skills" and not value)}

    @field_validator("name", "job")
    @classmethod
    def _one_line(cls, value: str) -> str:
        if not fits_on_one_line(value):
            raise ValueError("must fit on one line")
        return value


def _join(words: list[str]) -> str:
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def _secret_sentence(found: dict[str, tuple[str, ...]]) -> str | None:
    flagged = [field for field, kinds in found.items() if kinds]
    if not flagged:
        return None
    kinds = list(dict.fromkeys(kind for field in flagged for kind in found[field]))
    return f"Not shared: {_join(kinds)} seems to be in the {_join(flagged)}. Remove it, then share again."


def _skill_label(index: int, skill: TemplateSkill) -> str:
    """The skill by name, unless the name itself looks like a secret (then by its place in the list)."""
    return f"skill {index + 1}" if find_secret_kinds(skill.name) else f"skill “{skill.name}”"


def template_file_for(bot: Bot, skills: tuple[TemplateSkill, ...] = ()) -> TemplateFile:
    fields = {"name": bot.name, "job": bot.job, "instructions": bot.instructions}
    found = {field: find_secret_kinds(text) for field, text in fields.items()}
    found |= {_skill_label(n, s): find_secret_kinds(f"{s.name}\n{s.use_when}\n{s.steps}")
              for n, s in enumerate(skills)}
    refused = _secret_sentence(found)
    if refused is not None:
        raise SecretInTemplate(refused)
    return TemplateFile(format="roost-bot", version=1, name=bot.name, job=bot.job, instructions=bot.instructions,
                        avatar=TemplateAvatar(shape=bot.avatar.shape, color=bot.avatar.color, screen=bot.avatar.screen,
                                              role=bot.avatar.role), skills=skills[:TEMPLATE_SKILLS_MAX])


def read_template_file(data: object) -> TemplateFile:
    try:
        return TemplateFile.model_validate(data)
    except ValidationError as exc:
        extra = [str(error["loc"][0]) for error in exc.errors() if error["type"] == "extra_forbidden"]
        if extra:
            raise TemplateFileError(f"This file has parts Roost does not read: {', '.join(extra)}.") from exc
        first = exc.errors()[0]
        if first["type"] == "value_error" and first["loc"][:1] == ("skills",):
            raise TemplateFileError(str(first["msg"]).removeprefix("Value error, ")) from exc
        where = ".".join(str(part) for part in first["loc"]) or "the file"
        raise TemplateFileError(f"This is not a Roost bot file: {where}: {first['msg']}.") from exc


def template_filename(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9 _-]", "", name).strip() or "bot"
    return f"{safe}{TEMPLATE_SUFFIX}"
