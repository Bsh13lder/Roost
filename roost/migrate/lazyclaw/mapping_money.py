"""Expenses and recurring rules (pure)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from roost.migrate.lazyclaw.constants import EXPENSE_STATUSES, RECURRING_STATUSES
from roost.migrate.lazyclaw.mapping_common import choice, stamps, text
from roost.migrate.lazyclaw.models import (
    ImportedExpense, ImportedProject, ImportedRecurring, ImportedTask, LazyData, RoostContext, Row,
)
from roost.migrate.lazyclaw.notes import Log
from roost.migrate.lazyclaw.values import (
    ValueAnomaly, cron_to_cadence, currency, date_part, first_next_due, money, roost_anchor,
)


def project_targets(data: LazyData, projects: tuple[ImportedProject, ...], general: str | None) -> dict[str, str | None]:
    """LazyClaw project id -> Roost id. A deleted project's rows go to General (H9)."""
    targets: dict[str, str | None] = {str(r["id"]): general for r in data.projects if r.get("deleted_at")}
    targets.update({p.id: p.target_id for p in projects})
    return targets


def map_recurring(projects: tuple[ImportedProject, ...], data: LazyData, ctx: RoostContext,
                  log: Log) -> tuple[ImportedRecurring, ...]:
    live = {p.id: p for p in projects}
    out: list[ImportedRecurring] = []
    for row in data.recurring:
        ref, project = str(row.get("id")), live.get(str(row.get("project_id")))
        if project is None:
            log.skip("recurring_of_deleted_projects")
            continue
        try:
            item = _rule(row, project, ctx, log)
        except (ValueAnomaly, KeyError) as exc:
            log.note("recurring_invalid", ref, str(exc), blocking=True)
            continue
        if item is not None:
            out.append(item)
    return tuple(out)


def _rule(row: Row, project: ImportedProject, ctx: RoostContext, log: Log) -> ImportedRecurring | None:
    ref = str(row["id"])
    parts = cron_to_cadence(text(row, "cron_expression"))
    if parts is None:
        log.note("recurring_not_convertible", ref, "Only monthly, weekly and yearly rules can be imported.")
        return None
    status = choice(row, "status", RECURRING_STATUSES)
    created, updated = stamps(row, ctx.imported_at)
    due = first_next_due(parts[0], parts[1], text(row, "last_charged_at"), ctx.import_day)
    return ImportedRecurring(
        id=ref, project_id=project.target_id, amount=money(row.get("amount")),
        currency=currency(row.get("currency"), default=project.currency), description=text(row, "description"),
        vendor=text(row, "vendor"), cadence=parts[0], anchor_day=roost_anchor(parts[0], parts[1], due).isoformat(),
        next_due=due.isoformat(),
        created_at=created, updated_at=updated, deleted_at=ctx.imported_at if status == "paused" else None,
    )


def _task_links(row: Row, tasks: Mapping[str, ImportedTask], log: Log, ref: str) -> tuple[str | None, str | None]:
    task_id, step_id = text(row, "task_id"), text(row, "subtask_id")
    if task_id is None:
        return None, None
    task = tasks.get(task_id)
    if task is None:
        log.note("expense_task_missing", ref, "The expense's task was not imported; the link is dropped.")
        return None, None
    if step_id is not None and step_id not in {str(s["id"]) for s in task.steps}:
        log.note("expense_step_demoted", ref, "The expense's step is gone; it now belongs to the task.")
        return task_id, None
    return task_id, step_id


def _expense(row: Row, project_id: str, project_currency: str, tasks: Mapping[str, ImportedTask],
             ctx: RoostContext, log: Log) -> ImportedExpense:
    ref = str(row["id"])
    amount = money(row.get("amount"))
    if amount <= 0:
        raise ValueAnomaly("An expense amount must be more than 0.")
    created, updated = stamps(row, ctx.imported_at)
    spent = date_part(text(row, "spent_at"))
    if spent is None:
        spent = created[:10]
        log.note("expense_no_date", ref, "No spent date; the created date is used.")
    task_id, step_id = _task_links(row, tasks, log, ref)
    return ImportedExpense(
        id=ref, project_id=project_id, task_id=task_id, step_id=step_id, amount=amount,
        currency=currency(row.get("currency"), default=project_currency), description=text(row, "description"),
        vendor=text(row, "vendor"), notes=text(row, "notes"), spent_at=spent,
        status=choice(row, "status", EXPENSE_STATUSES), is_favorite=1 if row.get("is_favorite") else 0,
        recurring_id=None, occurrence=None, created_at=created, updated_at=updated,
    )


def _link_recurring(expenses: list[ImportedExpense], rows: Mapping[str, Row], rules: set[str],
                    log: Log) -> tuple[ImportedExpense, ...]:
    """Set ``recurring_id`` + ``occurrence``; a second row on one occurrence stays unlinked."""
    seen: set[tuple[str, str]] = set()
    out: list[ImportedExpense] = []
    for e in sorted(expenses, key=lambda x: (x.created_at, x.id)):
        rid = text(rows[e.id], "recurring_expense_id")
        if rid is None:
            out.append(e)
        elif rid not in rules:
            log.note("expense_recurring_missing", e.id, "The expense's recurring rule was not imported.")
            out.append(e)
        elif (rid, e.spent_at) in seen:
            log.note("expense_duplicate_occurrence", e.id, "A second charge on one occurrence; kept unlinked.")
            out.append(e)
        else:
            seen.add((rid, e.spent_at))
            out.append(_linked(e, rid))
    order = {e.id: i for i, e in enumerate(expenses)}
    return tuple(sorted(out, key=lambda x: order[x.id]))


def _linked(expense: ImportedExpense, rid: str) -> ImportedExpense:
    return replace(expense, recurring_id=rid, occurrence=expense.spent_at)


def map_expenses(projects: tuple[ImportedProject, ...], tasks: tuple[ImportedTask, ...],
                 recurring: tuple[ImportedRecurring, ...], data: LazyData, targets: Mapping[str, str | None],
                 ctx: RoostContext, log: Log) -> tuple[ImportedExpense, ...]:
    currencies = {p.target_id: p.currency for p in projects}
    if ctx.general_project_id:
        currencies.setdefault(ctx.general_project_id, ctx.general_currency)
    task_by_id = {t.id: t for t in tasks}
    rows = {str(r["id"]): r for r in data.expenses}
    mapped: list[ImportedExpense] = []
    for row in data.expenses:
        ref = str(row.get("id"))
        if row.get("deleted_at"):
            log.skip("expenses_deleted")
            continue
        target = targets.get(str(row.get("project_id")))
        if target is None or target not in currencies:
            log.note("expense_no_project", ref, "The expense's project could not be found.", blocking=True)
            continue
        try:
            mapped.append(_expense(row, target, currencies[target], task_by_id, ctx, log))
        except (ValueAnomaly, KeyError) as exc:
            log.note("expense_invalid", ref, str(exc), blocking=True)
    return _link_recurring(mapped, rows, {r.id for r in recurring}, log)
