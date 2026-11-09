"""Projects and the budget ledger (pure)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal

from roost.migrate.lazyclaw.constants import (
    GENERAL_NAME_KEY, OPENING_BUDGET_SOURCE, PROJECT_STATUSES, TOPUP_KINDS,
)
from roost.migrate.lazyclaw.mapping_common import choice, required, stamps, text
from roost.migrate.lazyclaw.models import (
    ImportedProject, ImportedTopup, LazyData, RoostContext, Row,
)
from roost.migrate.lazyclaw.notes import Log
from roost.migrate.lazyclaw.values import ValueAnomaly, currency, date_part, money, nearest_color, utc_stamp


def _is_general(row: Row) -> bool:
    return (text(row, "name_key") or "").casefold() == GENERAL_NAME_KEY


def general_target(data: LazyData, ctx: RoostContext) -> str | None:
    """Where General's rows go: Roost's General, else LazyClaw's own General id, else nowhere."""
    if ctx.general_project_id:
        return ctx.general_project_id
    for row in data.projects:
        if _is_general(row) and not row.get("deleted_at"):
            return str(row["id"])
    return None


def _project(row: Row, ctx: RoostContext, target: str) -> ImportedProject:
    budget = money(row.get("budget") if row.get("budget") is not None else 0)
    created, updated = stamps(row, ctx.imported_at)
    return ImportedProject(
        id=str(row["id"]), target_id=target, name=required(row, "name"), description=text(row, "description"),
        budget=budget, currency=currency(row.get("currency")), status=choice(row, "status", PROJECT_STATUSES),
        start_date=date_part(text(row, "start_date")), due_date=date_part(text(row, "due_date")),
        color=nearest_color(text(row, "color")), created_at=created, updated_at=updated,
        is_general=_is_general(row),
    )


def map_projects(data: LazyData, ctx: RoostContext, log: Log) -> tuple[ImportedProject, ...]:
    """Live projects only. The budget is final only after ``map_topups`` has weighed the ledger."""
    out: list[ImportedProject] = []
    for row in data.projects:
        ref = str(row.get("id"))
        if row.get("deleted_at"):
            log.skip("projects_deleted")
            continue
        try:
            target = (ctx.general_project_id or ref) if _is_general(row) else ref
            out.append(_project(row, ctx, target))
        except (ValueAnomaly, KeyError) as exc:
            log.note("project_invalid", ref, str(exc), blocking=True)
        if row.get("is_favorite"):
            log.lose("project_favorites")
    return tuple(out)


def _topup(row: Row, project: ImportedProject, ctx: RoostContext) -> ImportedTopup:
    created, updated = stamps(row, ctx.imported_at)
    deleted = utc_stamp(text(row, "deleted_at"))
    return ImportedTopup(
        id=str(row["id"]), project_id=project.target_id, amount=money(row.get("amount")),
        currency=currency(row.get("currency")), source=text(row, "source"),
        kind=choice(row, "kind", TOPUP_KINDS), created_at=created, updated_at=updated, deleted_at=deleted,
    )


def _read_topups(data: LazyData, by_id: Mapping[str, ImportedProject], ctx: RoostContext,
                 log: Log) -> list[ImportedTopup]:
    out: list[ImportedTopup] = []
    for row in data.topups:
        ref, project = str(row.get("id")), by_id.get(str(row.get("project_id")))
        if project is None:
            log.skip("topups_of_deleted_projects")
            continue
        try:
            item = _topup(row, project, ctx)
        except (ValueAnomaly, KeyError) as exc:
            log.note("topup_invalid", ref, str(exc), blocking=True)
            continue
        if item.currency != project.currency:
            log.note("topup_currency", ref, f"{item.currency} top-up in a {project.currency} project.", blocking=True)
            continue
        out.append(item)
    return out


def _opening_row(project: ImportedProject, gap: Decimal) -> ImportedTopup:
    return ImportedTopup(
        id=f"opening-{project.id}", project_id=project.target_id, amount=gap, currency=project.currency,
        source=OPENING_BUDGET_SOURCE, kind="edit", created_at=project.created_at, updated_at=project.created_at,
        deleted_at=None, opening=True,
    )


def map_topups(projects: tuple[ImportedProject, ...], data: LazyData, ctx: RoostContext,
               log: Log) -> tuple[tuple[ImportedProject, ...], tuple[ImportedTopup, ...]]:
    """Top-ups plus H4's invariant: ``budget == sum of live rows``. A gap becomes an opening row.

    Returns the projects with their final budget (0 with no live rows is no budget at all).
    """
    by_id = {p.id: p for p in projects}
    rows = _read_topups(data, by_id, ctx, log)
    live_sum: dict[str, Decimal] = {}
    live_count: dict[str, int] = {}
    for t in rows:
        if t.deleted_at is None:
            live_sum[t.project_id] = live_sum.get(t.project_id, Decimal(0)) + t.amount
            live_count[t.project_id] = live_count.get(t.project_id, 0) + 1
    final: list[ImportedProject] = []
    openings: list[ImportedTopup] = []
    for p in projects:
        budget = p.budget or Decimal("0.00")
        gap = budget - live_sum.get(p.target_id, Decimal(0))
        if gap != 0:
            openings.append(_opening_row(p, gap))
            log.note("budget_gap", p.id, f"Budget is {gap} away from its top-ups; an opening row covers it.")
        has_rows = live_count.get(p.target_id, 0) > 0 or gap != 0
        final.append(_with_budget(p, budget if (budget != 0 or has_rows) else None))
    return tuple(final), tuple(rows + openings)


def _with_budget(project: ImportedProject, budget: Decimal | None) -> ImportedProject:
    return replace(project, budget=budget)
