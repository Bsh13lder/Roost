"""How a record tool names one of the user's projects (projects hub H3, H12).

Every tool but ``log_expense`` names a project through
``ProjectService.resolve``: its id, its exact name or a unique part of one.
A lone near miss may be read (``change=False``) but is never changed or
linked to, and no project is ever created from a name here. A refusal comes
back as the tool's own result and carries the taint of the project names it
shows (M1 D3).

General (H2) is hidden from the Board and is where loose money goes, so a
change or a link never lands on it: ``project_ref`` refuses it with the
service's own sentence unless the caller is moving money (``allow_general``)."""

from __future__ import annotations

import html

from roost.money.models import Project
from roost.money.project_store import is_general
from roost.projects.service import GENERAL_FIXED_TEXT, ProjectRefusal, ProjectService
from roost.talk.outcome import ToolOutcome

NAME_THE_PROJECT_TEXT = "Refused: name the project (its name or id)."


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


async def project_ref(projects: ProjectService, user_id: str, name: str | None, *, change: bool,
                      allow_general: bool = False) -> Project | ToolOutcome | None:
    """The project ``name`` means, or the refusal to hand back. ``None`` or a
    blank name means no project; on a change that unlinks the record. A
    change never lands on General unless ``allow_general`` (an expense moved
    out of a project goes there)."""
    if name is None or not name.strip():
        return None
    found = await projects.resolve(user_id, name, change=change)
    if isinstance(found, ProjectRefusal):
        return ToolOutcome(f"Refused: {_escape(found)}", tainted=found.tainted)
    if change and not allow_general and is_general(found):
        return ToolOutcome(f"Refused: {GENERAL_FIXED_TEXT}")
    return found


async def required_project(projects: ProjectService, user_id: str, name: str, *,
                           change: bool) -> Project | ToolOutcome:
    """Like ``project_ref``, for a tool that must name a project."""
    found = await project_ref(projects, user_id, name, change=change)
    return ToolOutcome(NAME_THE_PROJECT_TEXT) if found is None else found


def id_of(project: Project | None) -> str | None:
    return None if project is None else project.id


def project_taint(project: Project | None) -> bool:
    """A reply that echoes a web-made project's name is web text (M1 D3)."""
    return project is not None and project.tainted


def project_suffix(project: Project | None, *, unlinked: bool = False) -> str:
    """The end of a reply that filed a record: the project it is in now."""
    if project is not None:
        return f" Project: “{_escape(project.name)}”."
    return " No project." if unlinked else ""
