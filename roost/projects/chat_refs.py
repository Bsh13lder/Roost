"""#project in a bot's chat (owner, 2026-10-26): "# is project name".

The chat composer's ``#`` picker writes ``#Project Name`` into your message as plain text. ``chat_projects`` reads
those names back, matched exactly (case-insensitive, longest name first so "#Casa Nueva" never reads as "#Casa")
against your own projects only; General is never named, a ``#`` inside a word is not one, and an unknown name is
just text. ``project_mention_section`` is the run's one trusted line per project: its name (escaped, as typed by
you) and its id, so the bot's project tools get the right one without asking. Nothing is stored: the message keeps
its text, and every run reads it again."""

from __future__ import annotations

import html
import re
from collections.abc import Sequence

from roost.constants import CHAT_PROJECTS_PER_MESSAGE_MAX
from roost.money.models import Project
from roost.money.project_store import is_general

PROJECT_MENTION_LINE = (
    "The user means the project “{name}” (id {project_id}) when they write #{name}. Use this project for the "
    "tasks, money, notes and documents they ask about, without asking which one."
)


def _pattern(names: Sequence[str]) -> re.Pattern[str]:
    choices = "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    return re.compile(rf"(?<![\w#])#({choices})(?![\w\-])", re.IGNORECASE)


def chat_projects(text: str, projects: Sequence[Project]) -> tuple[Project, ...]:
    """The projects ``text`` names as ``#Name``, in text order, each once, at most the cap. ``projects`` must be only
    the user's own."""
    by_name = {project.name.casefold(): project for project in projects if not is_general(project)}
    if not by_name or "#" not in text:
        return ()
    found = (by_name[match.group(1).casefold()] for match in _pattern(tuple(by_name)).finditer(text))
    unique = tuple({project.id: project for project in found}.values())
    return unique[:CHAT_PROJECTS_PER_MESSAGE_MAX]


def project_mention_section(projects: Sequence[Project]) -> str | None:
    """One line per named project for the run's instructions, or None when the message named none."""
    if not projects:
        return None
    return "\n".join(PROJECT_MENTION_LINE.format(name=html.escape(project.name, quote=True), project_id=project.id)
                     for project in projects)
