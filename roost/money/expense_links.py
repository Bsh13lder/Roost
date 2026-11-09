"""An expense's task and step (projects hub H11).

- The task is found among tasks of EVERY status, since money is often logged
  after the work is done: its id, its exact title or a unique part of one. A
  near miss is refused (linking money to the wrong task is a change), and so
  is a title several tasks share — a repeating task's next occurrence has the
  same title — so the refusals list ids.
- A step needs its task and must be one of that task's steps, by id or title.
- A refusal that shows titles carries those tasks' taint (M1 D3)."""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Sequence

from roost.constants import EXPENSE_TASK_MATCHES_SHOWN
from roost.money.models import Project
from roost.projects.service import WEB_MARK
from roost.records.resolver import NamedRef, resolve
from roost.talk.outcome import ToolOutcome
from roost.tasks.models import Step, Task
from roost.tasks.service import TaskService

STEP_NEEDS_TASK_TEXT = "A step needs its task: name the task too."
TASK_NEAR_TEXT = "Refused: no task is called “{ref}”. Did you mean {titles}? Say it exactly."
TASK_SEVERAL_TEXT = "Refused: several tasks match “{ref}”: {titles}. Say which one (its id)."
TASK_NONE_TEXT = "Refused: no task matches “{ref}”."
STEP_NONE_TEXT = "Refused: “{task}” has no step “{ref}”. Its steps: {steps}."
TASK_IN_TEXT = "That task is in {project}."
TASK_NO_PROJECT_TEXT = "That task has no project."
GENERAL_NAME = "general"
NO_STEPS_TEXT = "Refused: “{task}” has no steps."


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def _blank(text: str | None) -> bool:
    return text is None or not text.strip()


@dataclass(frozen=True)
class ExpenseLink:
    task: Task | None = None
    step: Step | None = None

    @property
    def task_id(self) -> str | None:
        return None if self.task is None else self.task.id

    @property
    def step_id(self) -> str | None:
        return None if self.step is None else self.step.id

    @property
    def tainted(self) -> bool:
        """A reply that echoes a web-made task's title is web text."""
        return self.task is not None and self.task.tainted


NO_LINK = ExpenseLink()


def project_conflict(task: Task, task_project: Project | None, *, project_id: str | None = None,
                     name: str | None = None) -> str | None:
    """Why the project named (by id and/or name) can't hold an expense for ``task``, or ``None``.
    An expense lives in its task's project; a task with no project only takes General."""
    given_name = (name or "").strip()
    if project_id is None and not given_name:
        return None
    if task.project_id is None:
        return None if project_id is None and given_name.casefold() == GENERAL_NAME else TASK_NO_PROJECT_TEXT
    if task_project is None:
        return None
    same_id = project_id is None or project_id == task.project_id
    same_name = not given_name or given_name.casefold() == task_project.name.casefold()
    return None if same_id and same_name else TASK_IN_TEXT.format(project=task_project.name)


async def find_link(tasks: TaskService, user_id: str, task_ref: str | None,
                    step_ref: str | None) -> ExpenseLink | ToolOutcome:
    """The task and step an expense is for. No task named: no link. A step
    alone is a ``ValueError`` (a step needs its task)."""
    if _blank(task_ref):
        if not _blank(step_ref):
            raise ValueError(STEP_NEEDS_TASK_TEXT)
        return NO_LINK
    task = await find_task(tasks, user_id, task_ref or "")
    if isinstance(task, ToolOutcome):
        return task
    if _blank(step_ref):
        return ExpenseLink(task)
    step = find_step(task, step_ref or "")
    return step if isinstance(step, ToolOutcome) else ExpenseLink(task, step)


async def find_task(tasks: TaskService, user_id: str, ref: str) -> Task | ToolOutcome:
    known = await tasks.list(user_id, status="all")
    by_id = {task.id: task for task in known}
    if ref.strip() in by_id:
        return by_id[ref.strip()]
    hit = resolve(ref, [NamedRef(task.id, task.title) for task in known])
    if hit.resolved is not None and hit.reason != "fuzzy":
        return by_id[hit.resolved.id]
    shown = tuple(by_id[candidate.id] for candidate in hit.candidates[:EXPENSE_TASK_MATCHES_SHOWN])
    return _task_refusal(ref.strip(), hit.reason, shown)


def _titles(tasks: Sequence[Task]) -> str:
    return "; ".join(f"“{_escape(task.title)}” id={task.id}" + (WEB_MARK if task.tainted else "") for task in tasks)


def _task_refusal(ref: str, reason: str, shown: Sequence[Task]) -> ToolOutcome:
    tainted = any(task.tainted for task in shown)
    if reason == "fuzzy":
        return ToolOutcome(TASK_NEAR_TEXT.format(ref=_escape(ref), titles=_titles(shown)), tainted=tainted)
    if reason == "multi":
        return ToolOutcome(TASK_SEVERAL_TEXT.format(ref=_escape(ref), titles=_titles(shown)), tainted=tainted)
    return ToolOutcome(TASK_NONE_TEXT.format(ref=_escape(ref)))


def find_step(task: Task, ref: str) -> Step | ToolOutcome:
    """One of ``task``'s steps by id, exact title or a unique part of one; a
    refusal lists the task's steps (the task's own text, so its taint)."""
    by_id = {step.id: step for step in task.steps}
    if ref.strip() in by_id:
        return by_id[ref.strip()]
    hit = resolve(ref, [NamedRef(step.id, step.title) for step in task.steps])
    if hit.resolved is not None and hit.reason != "fuzzy":
        return by_id[hit.resolved.id]
    if not task.steps:
        return ToolOutcome(NO_STEPS_TEXT.format(task=_escape(task.title)), tainted=task.tainted)
    steps = "; ".join(f"“{_escape(step.title)}”" for step in task.steps)
    text = STEP_NONE_TEXT.format(task=_escape(task.title), ref=_escape(ref.strip()), steps=steps)
    return ToolOutcome(text, tainted=task.tainted)
