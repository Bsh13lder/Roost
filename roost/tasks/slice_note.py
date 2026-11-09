"""Saying that a task's budget slice went with its project (projects hub H11, polish round A).

A slice is in its project's currency, so ``TaskStore.update`` clears it when a change moves the task to a
project in another currency or to none. Neither the store nor the service return why, so the tool and the
route that made the change compare the task before and after with ``slice_note`` and say so in the reply."""

from __future__ import annotations

from roost.money.models import Project
from roost.tasks.models import Task

SLICE_CLEARED_TEXT = "Its budget slice was cleared because {project} uses {currency}."
SLICE_UNLINKED_TEXT = "Its budget slice was cleared because it has no project now."


def slice_note(before: Task, after: Task, project: Project | None, *, asked: bool) -> str | None:
    """The sentence for a slice that this change cleared, else ``None``. ``asked``: the change itself
    sent a slice (a number, or ``null`` to clear it), so nothing was cleared behind the caller's back.
    ``project`` is the project the task moved to, ``None`` for an unlink."""
    if asked or before.allocated_budget is None or after.allocated_budget is not None:
        return None
    if project is None:
        return SLICE_UNLINKED_TEXT
    return SLICE_CLEARED_TEXT.format(project=project.name, currency=project.currency)
