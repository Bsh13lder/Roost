"""LazyClaw rows (decrypted) to the shapes Roost would write. Pure: no I/O, no clock, no randomness.

Plan section 1 (field-by-field mapping) and the user decisions of 2026-10-20: imported rows are
trusted (``tainted = 0``).
"""

from __future__ import annotations

from roost.migrate.lazyclaw.constants import EXPECTED_TIMEZONE
from roost.migrate.lazyclaw.mapping_money import map_expenses, map_recurring, project_targets
from roost.migrate.lazyclaw.mapping_projects import general_target, map_projects, map_topups
from roost.migrate.lazyclaw.mapping_tasks import map_comments, map_tasks
from roost.migrate.lazyclaw.models import LazyData, Mapped, RoostContext
from roost.migrate.lazyclaw.notes import Log


def map_lazyclaw(data: LazyData, ctx: RoostContext) -> Mapped:
    log = Log()
    if data.settings_timezone and data.settings_timezone != EXPECTED_TIMEZONE:
        log.note("timezone", "settings", f"LazyClaw's timezone is {data.settings_timezone}, not {EXPECTED_TIMEZONE}.")
    general = general_target(data, ctx)
    projects = map_projects(data, ctx, log)
    projects, topups = map_topups(projects, data, ctx, log)
    tasks = map_tasks(projects, data, ctx, log)
    comments = map_comments(tasks, data, ctx, log)
    recurring = map_recurring(projects, data, ctx, log)
    targets = project_targets(data, projects, general)
    expenses = map_expenses(projects, tasks, recurring, data, targets, ctx, log)
    return Mapped(projects=projects, tasks=tasks, comments=comments, topups=topups, expenses=expenses,
                  recurring=recurring, anomalies=tuple(log.anomalies), skipped=dict(log.skipped),
                  lost=dict(log.lost))
