"""A template file's skills (Skills design §5): Share as Template carries the skills on for that bot, and a file's
skills are added only on the Add its skills? sheet, marked as outside content.

``TemplateSkill`` is what the file holds (``steps`` is the skill's body). Secrets are refused at export
(``template_file_for``) and at import (``SkillDraft``), never quietly kept."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from roost.constants import SKILL_NAME_MAX, SKILL_USE_WHEN_MAX, TEMPLATE_SKILLS_MAX
from roost.skills.models import Skill, check_line, check_steps
from roost.skills.names import fold_name
from roost.skills.texts import NAME_BAD, USE_WHEN_BAD

TOO_MANY_SKILLS = f"This file has more than {TEMPLATE_SKILLS_MAX} skills."


class TemplateSkill(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    use_when: str
    steps: str

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return check_line(value, SKILL_NAME_MAX, NAME_BAD)

    @field_validator("use_when")
    @classmethod
    def _use_when(cls, value: str) -> str:
        return check_line(value, SKILL_USE_WHEN_MAX, USE_WHEN_BAD)

    @field_validator("steps")
    @classmethod
    def _steps(cls, value: str) -> str:
        return check_steps(value)


@dataclass(frozen=True)
class ImportLine:
    skill: TemplateSkill
    state: Literal["add", "have"]


def skills_for_template(skills: Iterable[Skill]) -> tuple[TemplateSkill, ...]:
    """The skills a shared file carries: at most ``TEMPLATE_SKILLS_MAX``, in the given (folded-name) order."""
    return tuple(TemplateSkill(name=s.name, use_when=s.use_when, steps=s.body) for s in skills)[:TEMPLATE_SKILLS_MAX]


def import_plan(have_names: Iterable[str], wanted: Iterable[TemplateSkill]) -> tuple[ImportLine, ...]:
    """Each wanted skill is ``have`` when the user already has that (folded) name, or an earlier line adds it."""
    seen = {fold_name(name) for name in have_names}
    lines: list[ImportLine] = []
    for skill in wanted:
        key = fold_name(skill.name)
        lines.append(ImportLine(skill, "have" if key in seen else "add"))
        seen = seen | {key}
    return tuple(lines)
