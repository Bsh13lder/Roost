"""Tasks, their steps and comments (pure)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal

from roost.migrate.lazyclaw.constants import TASK_OWNERS, TASK_PRIORITIES, TASK_STATUSES
from roost.migrate.lazyclaw.mapping_common import choice, json_list, required, stamps, text
from roost.migrate.lazyclaw.models import (
    ImportedComment, ImportedProject, ImportedTask, LazyData, RoostContext, Row,
)
from roost.migrate.lazyclaw.notes import Log
from roost.migrate.lazyclaw.values import ValueAnomaly, local_stamp, money, utc_stamp
from roost.tasks.recurrence import validate_cron
from roost.tasks.steps import normalize_steps


def _project_index(projects: tuple[ImportedProject, ...], data: LazyData) -> dict[str, str]:
    """Folded name -> Roost project id, for live projects (LazyClaw's plaintext ``name_key``)."""
    live = {p.id: p.target_id for p in projects}
    return {
        str(r["name_key"]).casefold(): live[str(r["id"])]
        for r in data.projects if str(r.get("id")) in live and r.get("name_key")
    }


def _steps(row: Row) -> tuple[Mapping[str, object], ...]:
    """Deterministic: only steps that already carry an id and a title are kept."""
    raw = [s for s in json_list(text(row, "steps"), "steps") if isinstance(s, dict) and s.get("id")]
    return tuple(normalize_steps(raw))


def _category(row: Row, index: Mapping[str, str]) -> tuple[str | None, str | None]:
    """``(project_id, category)``: a matching live project replaces the list."""
    category = (text(row, "category") or "").strip()
    if not category:
        return None, None
    project = index.get(category.casefold())
    return (project, None) if project else (None, text(row, "category"))


def _allocated(row: Row, project_id: str | None, log: Log) -> Decimal | None:
    raw = row.get("allocated_budget")
    if raw is None:
        return None
    amount = money(raw)
    if project_id is None:
        log.note("allocated_budget_dropped", str(row["id"]), "A budget slice needs a project; dropped.")
        return None
    return amount


def _task(row: Row, index: Mapping[str, str], ctx: RoostContext, log: Log) -> ImportedTask:
    project_id, category = _category(row, index)
    recurring = (text(row, "recurring") or "").strip() or None
    created, updated = stamps(row, ctx.imported_at)
    return ImportedTask(
        id=str(row["id"]), title=required(row, "title"), description=text(row, "description"),
        project_id=project_id, category=category,
        priority=choice(row, "priority", TASK_PRIORITIES), status=choice(row, "status", TASK_STATUSES),
        owner=choice(row, "owner", TASK_OWNERS), due_date=local_stamp(text(row, "due_date")),
        reminder_at=local_stamp(text(row, "reminder_at")), pre_reminders=text(row, "pre_reminders") or None,
        recurring=validate_cron(recurring), recur_until=local_stamp(text(row, "recur_until")),
        tags=text(row, "tags") or None, steps=_steps(row), allocated_budget=_allocated(row, project_id, log),
        created_at=created, updated_at=updated, completed_at=utc_stamp(text(row, "completed_at")),
    )


def _count_progress(row: Row, log: Log) -> None:
    raw = text(row, "progress_log")
    if not raw or not raw.strip():
        return
    try:
        parsed = json.loads(raw)
        log.lose("progress_log_entries", len(parsed) if isinstance(parsed, list) else 1)
    except json.JSONDecodeError:
        log.lose("progress_log_entries")


def map_tasks(projects: tuple[ImportedProject, ...], data: LazyData, ctx: RoostContext,
              log: Log) -> tuple[ImportedTask, ...]:
    index = _project_index(projects, data)
    out: list[ImportedTask] = []
    for row in data.tasks:
        if row.get("deleted_at"):
            log.skip("tasks_deleted")
            continue
        _count_progress(row, log)
        try:
            out.append(_task(row, index, ctx, log))
        except (ValueAnomaly, ValueError, KeyError) as exc:
            log.note("task_invalid", str(row.get("id")), str(exc), blocking=True)
    return tuple(out)


def _comment(raw: object, task: ImportedTask, ctx: RoostContext, log: Log) -> ImportedComment | None:
    if not isinstance(raw, dict) or not raw.get("id") or not str(raw.get("text") or "").strip():
        log.note("comment_skipped", task.id, "A comment without an id or text was skipped.")
        return None
    step_ids = {str(s["id"]) for s in task.steps}
    step = raw.get("subtask_id")
    if step is not None and str(step) not in step_ids:
        log.note("comment_step_missing", task.id, "A comment's step is gone; it now belongs to the task.")
        step = None
    author = ctx.main_bot_id if raw.get("author") == "agent" and ctx.main_bot_id else "user"
    try:
        created = utc_stamp(str(raw["ts"])) if raw.get("ts") else None
    except ValueAnomaly:
        created = None
    return ImportedComment(id=str(raw["id"]), task_id=task.id, step_id=None if step is None else str(step),
                           author=author, body=str(raw["text"]), created_at=created or task.created_at)


def map_comments(tasks: tuple[ImportedTask, ...], data: LazyData, ctx: RoostContext,
                 log: Log) -> tuple[ImportedComment, ...]:
    by_id = {t.id: t for t in tasks}
    out: list[ImportedComment] = []
    for row in data.tasks:
        task = by_id.get(str(row.get("id")))
        if task is None:
            continue
        try:
            raws = json_list(text(row, "comments"), "comments")
        except ValueAnomaly as exc:
            log.note("task_invalid", task.id, str(exc), blocking=True)
            continue
        out.extend(c for c in (_comment(r, task, ctx, log) for r in raws) if c is not None)
    return tuple(out)
