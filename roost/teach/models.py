"""Teach shapes: one recorded step, a session, and the HTTP body of "I'm done teaching".

A step never holds what was typed: only where (host and path, title), what kind of control, its accessible label,
and for a key its name. Every text is collapsed to one line and cut to its constant, so a step stays small."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, field_validator

from roost.bots.limits import fits_on_one_line
from roost.constants import TEACH_DESCRIPTION_MAX, TEACH_LABEL_MAX, TEACH_PATH_MAX, TEACH_TITLE_MAX
from roost.teach.texts import DESCRIPTION_BAD

StepKind = Literal["click", "type", "password", "key", "paste", "browser"]
StepKey = Literal["", "Enter", "Tab", "Escape"]
_WEB_SCHEMES = ("http", "https")


def one_line(text: str, limit: int) -> str:
    """Whitespace collapsed to single spaces, cut to ``limit`` characters."""
    return " ".join(str(text or "").split())[:limit]


def url_parts(url: str) -> tuple[str, str]:
    """(host, path) of a web address; the query and fragment are dropped (they can hold an email or a token).
    Anything that is not http(s) gives ("", "")."""
    try:
        parts = urlsplit(url or "")
    except ValueError:
        return "", ""
    if parts.scheme not in _WEB_SCHEMES or not parts.hostname:
        return "", ""
    return parts.hostname.lower(), one_line(parts.path or "/", TEACH_PATH_MAX)


class TeachStep(BaseModel):
    """One thing you did while teaching. ``label`` is the control's accessible name, never a field's value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: StepKind
    host: str = ""
    path: str = ""
    title: str = ""
    role: str = ""
    label: str = ""
    key: StepKey = ""

    @field_validator("host", "role")
    @classmethod
    def _short(cls, value: str) -> str:
        return one_line(value, TEACH_LABEL_MAX)

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        return one_line(value, TEACH_PATH_MAX)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return one_line(value, TEACH_TITLE_MAX)

    @field_validator("label")
    @classmethod
    def _label(cls, value: str) -> str:
        return one_line(value, TEACH_LABEL_MAX)


@dataclass(frozen=True)
class TeachSession:
    id: str
    user_id: str
    bot_id: str
    steps: tuple[TeachStep, ...]
    capped: bool
    started_at: str


@dataclass(frozen=True)
class TeachOutcome:
    """What "I'm done teaching" did: the proposal it made, or that the recording was thrown away."""

    proposal_id: str | None
    steps: int
    discarded: bool


class TeachStopIn(BaseModel):
    """``POST /api/bots/{id}/teach/stop``: an optional one-line description, or ``discard`` to throw it away."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str | None = None
    discard: bool = False

    @field_validator("description")
    @classmethod
    def _description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if len(text) > TEACH_DESCRIPTION_MAX or not fits_on_one_line(text):
            raise ValueError(DESCRIPTION_BAD)
        return text or None


class TeachRefused(ValueError):
    """Teach can't do this now; ``text`` is a plain sentence for the user."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text
