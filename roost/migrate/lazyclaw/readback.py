"""After the commit: read every imported row back through Roost's own stores and compare the money
with what the mapping (the dry run) promised, using ``roost/projects/numbers.py`` for the sums.

Problems name ids and kinds, never user text."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from decimal import Decimal

from roost.config import Config
from roost.crypto.encryption import decrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import get_db_path
from roost.migrate.lazyclaw.models import ImportedExpense, ImportedProject, ImportedTask, Mapped
from roost.money.expense_store import ExpenseStore
from roost.money.models import Expense
from roost.money.project_store import ProjectStore
from roost.projects.numbers import counted, project_numbers, task_money
from roost.tasks.comment_store import CommentStore
from roost.tasks.store import TaskStore

UNREADABLE = "[encrypted]"
_LINK_TABLES = {"project": "money_projects", "task": "tasks", "comment": "task_comments", "topup": "money_topups",
                "expense": "money_expenses", "recurring": "money_recurring"}
_ZERO = Decimal("0.00")


@dataclass(frozen=True)
class ReadbackResult:
    problems: tuple[str, ...] = ()
    checked: dict[str, int] = field(default_factory=dict)
    spent: dict[str, Decimal] = field(default_factory=dict)                  # project id -> Roost-way spent
    other_currencies: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    task_spent: dict[str, Decimal] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems


def _same(problems: list[str], label: str, ref: str, got: object, want: object) -> None:
    if got != want:
        problems.append(f"{label} {ref}: read back differently from what was imported.")


async def _check_tasks(cfg: Config, user_id: str, tasks: tuple[ImportedTask, ...], problems: list[str]) -> None:
    store = TaskStore(cfg)
    for t in tasks:
        got = await store.get(user_id, t.id)
        if got is None:
            problems.append(f"task {t.id}: missing after the import.")
            continue
        if UNREADABLE in (got.title, got.description, got.category):
            problems.append(f"task {t.id}: could not be decrypted.")
        _same(problems, "task", t.id, (got.title, got.description, got.status, got.project_id, got.tainted),
              (t.title, t.description, t.status, t.project_id, False))
        _same(problems, "task steps", t.id, [s.id for s in got.steps], [str(s["id"]) for s in t.steps])
        _same(problems, "task budget slice", t.id, got.allocated_budget, t.allocated_budget)


async def _check_comments(cfg: Config, user_id: str, m: Mapped, problems: list[str]) -> None:
    store = CommentStore(cfg)
    for task in m.tasks:
        want = sorted(c.body for c in m.comments if c.task_id == task.id)
        got = sorted(c.body for c in await store.list(user_id, task.id, limit=10_000))
        _same(problems, "comments of task", task.id, got, want)


def _expected_spent(project: ImportedProject, expenses: tuple[ImportedExpense, ...], currency: str) -> Decimal:
    return sum((e.amount for e in expenses if e.project_id == project.target_id and e.status == "posted"
                and e.currency == currency), _ZERO)


async def _check_project(cfg: Config, user_id: str, p: ImportedProject, m: Mapped, month: str,
                         result: dict, problems: list[str]) -> tuple[Expense, ...]:
    projects, expenses = ProjectStore(cfg), ExpenseStore(cfg)
    got = await projects.get(user_id, p.target_id)
    if got is None:
        problems.append(f"project {p.target_id}: missing after the import.")
        return ()
    if not p.is_general:
        _same(problems, "project", p.target_id, (got.name, got.budget, got.currency, got.status, got.tainted),
              (p.name, p.budget, p.currency, p.status, False))
    live = [t for t in await projects.topups(user_id, p.target_id) if not t.undone]
    if got.budget is not None:
        _same(problems, "ledger of project", p.target_id, sum((t.amount for t in live), _ZERO), got.budget)
    rows = await expenses.list_project(user_id, p.target_id)
    want_ids = sorted(e.id for e in m.expenses if e.project_id == p.target_id)
    _same(problems, "expenses of project", p.target_id, sorted(e.id for e in rows), want_ids)
    numbers = project_numbers(got, rows, month)
    want = _expected_spent(p, m.expenses, got.currency)
    _same(problems, "spent of project", p.target_id, numbers.total.spent, want)
    result["spent"][p.target_id] = numbers.total.spent
    result["other"][p.target_id] = dict(numbers.other_currencies)
    return rows


def _check_links_and_rules(cfg: Config, user_id: str, dek: bytes, mapped: Mapped, problems: list[str]) -> None:
    """Every link resolves to a row of this user; every recurring rule decrypts (no store reads them yet)."""
    conn = sqlite3.connect(get_db_path(cfg))
    try:
        for kind, old_id, new_id in conn.execute(
                "SELECT kind, old_id, new_id FROM import_links WHERE user_id = ? AND source = 'lazyclaw' AND kind != 'wipe'", (user_id,)):
            table = _LINK_TABLES[kind]
            if conn.execute(f"SELECT 1 FROM {table} WHERE id = ? AND user_id = ?", (new_id, user_id)).fetchone() is None:
                problems.append(f"link {kind} {old_id}: the Roost row {new_id} is missing.")
        for rule in mapped.recurring:
            row = conn.execute("SELECT amount, cadence FROM money_recurring WHERE id = ? AND user_id = ?",
                               (rule.id, user_id)).fetchone()
            if row is None:
                problems.append(f"recurring {rule.id}: missing after the import.")
                continue
            amount = decrypt_field(row[0], dek, user_aad(user_id, "money_recurring:amount"))
            cadence = decrypt_field(row[1], dek, user_aad(user_id, "money_recurring:cadence"))
            _same(problems, "recurring", rule.id, (amount, cadence), (f"{rule.amount:.2f}", rule.cadence))
    finally:
        conn.close()


async def read_back(cfg: Config, user_id: str, mapped: Mapped, *, today_month: str) -> ReadbackResult:
    """``today_month`` is the Madrid month (``roost.money.months.current_month()``)."""
    problems: list[str] = []
    result: dict = {"spent": {}, "other": {}}
    await _check_tasks(cfg, user_id, mapped.tasks, problems)
    await _check_comments(cfg, user_id, mapped, problems)
    all_rows: list[Expense] = []
    currencies: dict[str, str] = {}
    for p in mapped.projects:
        all_rows.extend(await _check_project(cfg, user_id, p, mapped, today_month, result, problems))
        got = await ProjectStore(cfg).get(user_id, p.target_id)
        if got is not None:
            currencies[p.target_id] = got.currency
    task_spent: dict[str, Decimal] = {}
    store = TaskStore(cfg)
    for t in mapped.tasks:
        task = await store.get(user_id, t.id)
        if task is None:
            continue
        currency = currencies.get(task.project_id or "", "EUR")
        task_spent[t.id] = task_money(task, tuple(e for e in all_rows if e.task_id == t.id), currency).spent
    _check_links_and_rules(cfg, user_id, await get_user_dek(cfg, user_id), mapped, problems)
    checked = {"tasks": len(mapped.tasks), "projects": len(mapped.projects), "expenses": len(mapped.expenses),
               "comments": len(mapped.comments), "topups": len(mapped.topups)}
    return ReadbackResult(problems=tuple(problems), checked=checked, spent=result["spent"],
                          other_currencies=result["other"], task_spent=task_spent)
