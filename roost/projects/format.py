"""Tool-result text for projects (projects hub §3, H4, H8). Names and other
record text are escaped here, by their producer (tool results reach the model
raw); every number comes from ``roost.projects.numbers`` and nothing is
summed here."""

from __future__ import annotations

from typing import Sequence

from roost.constants import PROJECT_PAGE_ITEMS, PROJECT_STATUSES
from roost.documents.format import document_line
from roost.money.format import escape, expense_line, money
from roost.money.models import TOPUP_CREDIT, Project, TopUp
from roost.notes.models import Note
from roost.projects.numbers import BudgetLine, Progress, ProjectNumbers, TaskMoney
from roost.projects.service import WEB_MARK, ProjectDetail, ProjectRow
from roost.tasks.format import task_line

NO_PROJECTS_TEXT = "No projects yet."
NO_ACTIVE_PROJECTS_TEXT = "No active projects."
_ARCHIVED = PROJECT_STATUSES[1]


def budget_text(label: str, line: BudgetLine, currency: str) -> str:
    """One budget: what is spent and, with a budget, of how much, what is left
    or over, and the bar's percent (H8)."""
    spent = money(line.spent, currency)
    if line.budget is None or line.remaining is None:
        return f"{label}: {spent} spent"
    left = (f"{money(line.remaining, currency)} left" if line.remaining >= 0
            else f"over by {money(-line.remaining, currency)}")
    return f"{label}: {spent} of {money(line.budget, currency)}, {left} ({line.used_percent}%)"


def task_money_text(task_money: TaskMoney | None, currency: str) -> str:
    """A task's slice on its project's page (design §2, P6): planned, spent, and
    left or over. Empty for a task with no slice and nothing spent on it."""
    if task_money is None or (task_money.planned is None and not task_money.spent):
        return ""
    spent = f"spent {money(task_money.spent, currency)}"
    if task_money.planned is None or task_money.left is None:
        return f" · {spent}"
    left = (f"{money(task_money.left, currency)} left" if task_money.left >= 0
            else f"over by {money(-task_money.left, currency)}")
    return f" · budget {money(task_money.planned, currency)}, {spent}, {left}"


def progress_text(progress: Progress) -> str:
    """Done of all but the cancelled ones; failed ones counted apart (H11)."""
    failed = f", {progress.failed} failed" if progress.failed else ""
    return f"{progress.done} done{failed} of {progress.total}"


def _marks(project: Project) -> str:
    archived = " [archived]" if project.status == _ARCHIVED else ""
    return f"{archived}{WEB_MARK if project.tainted else ''}"


def _others(numbers: ProjectNumbers) -> str:
    return "".join(f", also {money(total, code)}" for code, total in numbers.other_currencies.items())


def project_line(row: ProjectRow) -> str:
    project, numbers, progress = row
    total = budget_text("total", numbers.total, numbers.currency)
    month = budget_text("this month", numbers.month, numbers.currency)
    return (f"- “{escape(project.name)}”{_marks(project)} · {total} · {month}{_others(numbers)} · "
            f"tasks: {progress_text(progress)} id={project.id}")


def project_list_text(rows: Sequence[ProjectRow], *, include_archived: bool) -> str:
    if not rows:
        return NO_PROJECTS_TEXT if include_archived else NO_ACTIVE_PROJECTS_TEXT
    return "\n".join(project_line(row) for row in rows)


def project_brief(project: Project) -> str:
    """A project's settings on one line: the create_project and update_project replies."""
    parts = (
        f"“{escape(project.name)}”{_marks(project)} in {project.currency}",
        f"budget {money(project.budget, project.currency)}" if project.budget is not None else "",
        (f"monthly limit {money(project.monthly_budget, project.currency)}"
         if project.monthly_budget is not None else ""),
        f"starts {project.start_date}" if project.start_date else "",
        f"due {project.due_date}" if project.due_date else "",
    )
    return ", ".join(part for part in parts if part) + f" id={project.id}"


def topup_label(topup: TopUp) -> str:
    """H4's history labels: a credit, an edit of one, or a set_budget edit."""
    if topup.kind == TOPUP_CREDIT:
        return "Top-up"
    return "Top-up changed" if topup.topup_id else "Budget set"


def topup_line(topup: TopUp) -> str:
    source = f" · {escape(topup.source)}" if topup.source else ""
    undone = " [undone]" if topup.undone else ""
    web = WEB_MARK if topup.tainted else ""
    return (f"- {topup.created_at[:10]} · {topup_label(topup)} {money(topup.amount, topup.currency)}"
            f"{source}{undone}{web} id={topup.id}")


def _more(total: int, shown: int, hint: str) -> tuple[str, ...]:
    return (f"…and {total - shown} more: {hint}",) if total > shown else ()


def _section(title: str, lines: Sequence[str]) -> tuple[str, ...]:
    return (f"{title}:", *lines) if lines else ()


def _note_line(note: Note) -> str:
    return f"- “{escape(note.title)}”{WEB_MARK if note.tainted else ''} id={note.id}"


def _head(detail: ProjectDetail) -> tuple[str, ...]:
    project = detail.project
    facts = tuple(fact for fact in (
        f"Lead bot: {escape(detail.lead_bot_name)}" if detail.lead_bot_name else "",
        f"starts {project.start_date}" if project.start_date else "",
        f"due {project.due_date}" if project.due_date else "",
    ) if fact)
    title = f"“{escape(project.name)}”{_marks(project)} in {project.currency} id={project.id}"
    return (title, " · ".join(facts)) if facts else (title,)


def _money_lines(numbers: ProjectNumbers) -> tuple[str, ...]:
    others = ", ".join(money(total, code) for code, total in numbers.other_currencies.items())
    received = ", ".join(money(total, code) for code, total in numbers.money_in.items())
    return (
        budget_text("Total", numbers.total, numbers.currency),
        budget_text("This month", numbers.month, numbers.currency),
        *((f"Also {others}, not counted in the budgets",) if others else ()),
        f"Starred: {money(numbers.starred_total, numbers.currency)}",
        *((f"Money in: {received} (not in the budgets)",) if received else ()),
    )


def _tasks(detail: ProjectDetail) -> tuple[str, ...]:
    shown, currency = detail.tasks[:PROJECT_PAGE_ITEMS], detail.project.currency
    more = _more(len(detail.tasks), len(shown), "call list_tasks with this project and status all.")
    lines = tuple(task_line(task) + task_money_text(detail.task_money.get(task.id), currency) for task in shown)
    return (f"Tasks ({progress_text(detail.progress)}):", *lines, *more)


def project_page_text(detail: ProjectDetail) -> str:
    """``get_project``: the project, its numbers, its tasks, its latest
    expenses, notes and documents, and its newest top-ups with their ids."""
    name, topups = detail.project.name, detail.topups[:PROJECT_PAGE_ITEMS]
    return "\n".join((
        *_head(detail), *_money_lines(detail.numbers), *_tasks(detail),
        *_section("Latest expenses", tuple(f"- {expense_line(expense, name)}" for expense in detail.expenses)),
        *_section("Notes", tuple(_note_line(note) for note in detail.notes)),
        *_section("Documents", tuple(f"- {document_line(meta)}" for meta in detail.documents)),
        *_section("Top-ups", tuple(topup_line(topup) for topup in topups)),
        *_more(len(detail.topups), len(topups), "the Board shows the older ones."),
    ))
