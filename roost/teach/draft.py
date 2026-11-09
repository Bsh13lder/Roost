"""A skill draft from a teach recording: one worker-model call, or a plain draft made from the steps.

The worker (``make_worker_model``; a fake in tests) gets the step lines HTML-escaped inside ``<steps>`` and your
description inside ``<description>``: page titles and labels are web content, quoted as data. Its JSON answer must
pass ``SkillDraft`` (one-line name and Use when, no secret). Anything else, a tool call, a timeout or an error,
falls back to the plain draft, which leaves out a line with an email address or a secret and is cut to fit the
skill body limit. A plain draft that still fails (a secret in your description) is ``TeachRefused``."""

from __future__ import annotations

import html
import json
import logging
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import SKILL_BODY_MAX, SKILL_NAME_MAX, SKILL_USE_WHEN_MAX, TEACH_STEPS_MAX, TEACH_WORKER_AGENT
from roost.llm.types import Model
from roost.memory.worker import ask_worker
from roost.skills.models import SkillDraft, plain_error
from roost.teach import texts
from roost.teach.models import TeachRefused, TeachStep
from roost.teach.steps import fitted_body, numbered, step_lines

__all__ = ["TeachRefused", "make_draft", "worker_input"]

logger = logging.getLogger(__name__)


class _WorkerReply(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    name: str
    use_when: str
    steps: list[str] = Field(min_length=1, max_length=TEACH_STEPS_MAX)


def worker_input(steps: Sequence[TeachStep], description: str | None) -> str:
    quoted = "\n".join(html.escape(line) for line in step_lines(steps))
    head = f"<description>{html.escape(description)}</description>\n" if description else ""
    return f"{head}<steps>\n{numbered(quoted.splitlines())}\n</steps>"


def _parse(reply: str) -> SkillDraft:
    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON in the worker's reply")
    answer = _WorkerReply.model_validate(json.loads(reply[start:end + 1]))
    lines = [" ".join(step.split()) for step in answer.steps if step.strip()]
    return SkillDraft(name=answer.name, use_when=answer.use_when, body=numbered(lines))


def _first_host(steps: Sequence[TeachStep]) -> str:
    return next((step.host for step in steps if step.host), "")


def plain_draft(steps: Sequence[TeachStep], description: str | None) -> SkillDraft:
    host = _first_host(steps)
    name = description or (texts.FALLBACK_NAME.format(host=host) if host else texts.FALLBACK_NAME_PLAIN)
    use_when = description or (texts.FALLBACK_USE_WHEN.format(host=host) if host else texts.FALLBACK_USE_WHEN_PLAIN)
    try:
        return SkillDraft(name=name[:SKILL_NAME_MAX], use_when=use_when[:SKILL_USE_WHEN_MAX],
                          body=fitted_body(step_lines(steps), SKILL_BODY_MAX))
    except ValidationError as exc:
        raise TeachRefused(plain_error(exc)) from None


async def make_draft(worker: Model, steps: Sequence[TeachStep], description: str | None) -> SkillDraft:
    """The worker's draft when it gives a valid one, else the plain draft."""
    try:
        reply = await ask_worker(worker, agent=TEACH_WORKER_AGENT, system=texts.WORKER_SYSTEM,
                                 text=worker_input(steps, description))
        return _parse(reply)
    except Exception as exc:      # any failure of the worker falls back; its text is never logged
        logger.info("teach draft fell back to the plain draft: %s", type(exc).__name__)
    return plain_draft(steps, description)
