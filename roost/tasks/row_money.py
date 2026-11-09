"""The money on a task row (G3): planned, spent and left in the task's project's currency.

The numbers come from ``roost.projects.numbers.task_money``; the web adds nothing up. A task with no
project or no budget slice has no money, and another currency is never mixed in."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from roost.money.amounts import amount_text
from roost.money.models import Expense, Project
from roost.projects.numbers import task_money
from roost.tasks.models import Task


@dataclass(frozen=True)
class RowMoney:
    planned: Decimal
    spent: Decimal
    left: Decimal
    currency: str

    @property
    def over(self) -> bool:
        return self.spent > self.planned


def money_task_ids(tasks: Sequence[Task], projects: Mapping[str, Project]) -> tuple[str, ...]:
    """The tasks that will show money, so their expenses can be read in one query."""
    return tuple(t.id for t in tasks if t.allocated_budget is not None and t.project_id in projects)


def rows_money(tasks: Sequence[Task], expenses: Sequence[Expense],
               projects: Mapping[str, Project]) -> Mapping[str, RowMoney]:
    """Money by task id, only for tasks with a project of the user's and a budget slice."""
    found: dict[str, RowMoney] = {}
    for task in tasks:
        project = projects.get(task.project_id or "")
        if project is None or task.allocated_budget is None:
            continue
        got = task_money(task, expenses, project.currency)
        if got.planned is None or got.left is None:
            continue
        found[task.id] = RowMoney(got.planned, got.spent, got.left, project.currency)
    return MappingProxyType(found)


def row_money_out(money: RowMoney | None) -> dict[str, Any] | None:
    if money is None:
        return None
    return {"planned": amount_text(money.planned), "spent": amount_text(money.spent),
            "left": amount_text(money.left), "currency": money.currency, "over": money.over}


def sort_by_money_left(tasks: Sequence[Task], money: Mapping[str, RowMoney]) -> tuple[Task, ...]:
    """Tasks with a slice first, the most left first; those without keep their order after them.
    Left amounts in different currencies are never compared: each currency's tasks stay together,
    in the order their first task appears."""
    with_slice = [task for task in tasks if task.id in money]
    without = [task for task in tasks if task.id not in money]
    order: list[str] = []
    for task in with_slice:
        if money[task.id].currency not in order:
            order.append(money[task.id].currency)
    ranked = sorted(with_slice, key=lambda task: (order.index(money[task.id].currency), -money[task.id].left))
    return (*ranked, *without)
