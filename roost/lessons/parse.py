"""The worker's lesson, read strictly (docs/plans/2026-10-31-roost-lessons.md §3).

A create must pass ``SkillDraft`` and a change ``SkillPatch`` (one-line name and Use when, the length limits, no
secret) and hold a change. Anything else (no JSON, ``{"lesson": null}``, another action, a bad field) is None."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from roost.lessons.constants import LESSON_LESSON_STEPS_MAX
from roost.skills.models import SkillDraft, SkillPatch

Steps = Union[str, Annotated[list[str], Field(min_length=1, max_length=LESSON_LESSON_STEPS_MAX)]]


class _Create(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    action: Literal["create"]
    name: str
    use_when: str
    steps: Steps


class _Change(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    action: Literal["change"]
    skill: str = Field(min_length=1)
    use_when: str | None = None
    steps: Steps | None = None


class _Reply(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    lesson: Annotated[Union[_Create, _Change], Field(discriminator="action")] | None


_REPLY = TypeAdapter(_Reply)


@dataclass(frozen=True)
class LessonCreate:
    draft: SkillDraft


@dataclass(frozen=True)
class LessonChange:
    skill: str            # the existing skill's name, as the worker wrote it
    patch: SkillPatch


Lesson = Union[LessonCreate, LessonChange]


def _body(steps: str | list[str] | None) -> str | None:
    if steps is None or isinstance(steps, str):
        return steps
    lines = [" ".join(line.split()) for line in steps if line.strip()]
    return "\n".join(f"{n}. {line}" for n, line in enumerate(lines, start=1))


def _lesson(raw: _Create | _Change) -> Lesson | None:
    if isinstance(raw, _Create):
        return LessonCreate(SkillDraft(name=raw.name, use_when=raw.use_when, body=_body(raw.steps) or ""))
    patch = SkillPatch(use_when=raw.use_when, body=_body(raw.steps))
    return None if patch.is_empty() else LessonChange(raw.skill, patch)


def parse_lesson(reply: str) -> Lesson | None:
    """The lesson in the worker's reply, or None."""
    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = _REPLY.validate_python(json.loads(reply[start:end + 1]))
        return _lesson(parsed.lesson) if parsed.lesson is not None else None
    except (ValueError, ValidationError):
        return None
