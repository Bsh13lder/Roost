"""Row inserts for the importer: Roost's own column set, ``enc:v2`` under Roost's AADs, every row with
the target ``user_id``. Pure SQL over the caller's connection and transaction."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from roost.crypto.encryption import encrypt_field, user_aad
from roost.money.amounts import amount_text
from roost.money.project_store import _name_key
from roost.migrate.lazyclaw.models import (
    ImportedComment, ImportedExpense, ImportedProject, ImportedRecurring, ImportedTask, ImportedTopup,
)
from roost.tasks.steps import steps_from_json, steps_to_json


@dataclass(frozen=True)
class Sealer:
    """Encrypts a value for one column of one table under the user's DEK and Roost's AAD."""

    dek: bytes
    user_id: str

    def seal(self, table: str, column: str, value: str | None) -> str | None:
        return encrypt_field(value, self.dek, user_aad(self.user_id, f"{table}:{column}"))

    def money(self, table: str, column: str, amount: Decimal | None) -> str | None:
        return self.seal(table, column, None if amount is None else amount_text(amount))


def _tags(raw: str | None) -> str:
    try:
        parsed = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        parsed = []
    return json.dumps([str(t) for t in parsed] if isinstance(parsed, list) else [])


def insert_project(conn: sqlite3.Connection, s: Sealer, p: ImportedProject) -> None:
    t = "money_projects"
    conn.execute(
        "INSERT INTO money_projects (id, user_id, name, name_key, budget, currency, status, description, color, "
        "start_date, due_date, created_at, updated_at, tainted) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
        (p.target_id, s.user_id, s.seal(t, "name", p.name), _name_key(s.dek, p.name), s.money(t, "budget", p.budget),
         p.currency, p.status, s.seal(t, "description", p.description), p.color, p.start_date, p.due_date,
         p.created_at, p.updated_at))


def insert_topup(conn: sqlite3.Connection, s: Sealer, x: ImportedTopup, new_id: str) -> None:
    t = "money_topups"
    conn.execute(
        "INSERT INTO money_topups (id, user_id, project_id, amount, currency, source, kind, topup_id, created_at, "
        "updated_at, deleted_at, tainted) VALUES (?,?,?,?,?,?,?,NULL,?,?,?,0)",
        (new_id, s.user_id, x.project_id, s.money(t, "amount", x.amount), x.currency, s.seal(t, "source", x.source),
         x.kind, x.created_at, x.updated_at, x.deleted_at))


def insert_task(conn: sqlite3.Connection, s: Sealer, x: ImportedTask) -> None:
    t = "tasks"
    steps = steps_to_json(steps_from_json(json.dumps(list(x.steps))))
    conn.execute(
        "INSERT INTO tasks (id, user_id, title, description, category, priority, status, owner, due_date, "
        "reminder_at, pre_reminders, recurring, recur_until, tags, steps, created_at, updated_at, completed_at, "
        "tainted, project_id, allocated_budget, starred, estimate) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (x.id, s.user_id, s.seal(t, "title", x.title), s.seal(t, "description", x.description),
         s.seal(t, "category", x.category), x.priority, x.status, x.owner, x.due_date, x.reminder_at,
         x.pre_reminders, x.recurring, x.recur_until, s.seal(t, "tags", _tags(x.tags)), s.seal(t, "steps", steps),
         x.created_at, x.updated_at, x.completed_at, x.tainted, x.project_id,
         s.money(t, "allocated_budget", x.allocated_budget), x.starred, None))


def insert_comment(conn: sqlite3.Connection, s: Sealer, x: ImportedComment, new_id: str) -> None:
    conn.execute(
        "INSERT INTO task_comments (id, user_id, task_id, step_id, author, body, tainted, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (new_id, s.user_id, x.task_id, x.step_id, x.author, s.seal("task_comments", "body", x.body), x.tainted,
         x.created_at))


def insert_expense(conn: sqlite3.Connection, s: Sealer, x: ImportedExpense) -> None:
    t = "money_expenses"
    conn.execute(
        "INSERT INTO money_expenses (id, user_id, project_id, task_id, step_id, amount, currency, description, "
        "vendor, notes, spent_at, status, is_favorite, recurring_id, occurrence, created_at, updated_at, tainted) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (x.id, s.user_id, x.project_id, x.task_id, x.step_id, s.money(t, "amount", x.amount), x.currency,
         s.seal(t, "description", x.description), s.seal(t, "vendor", x.vendor), s.seal(t, "notes", x.notes),
         x.spent_at, x.status, x.is_favorite, x.recurring_id, x.occurrence, x.created_at, x.updated_at, x.tainted))


def insert_recurring(conn: sqlite3.Connection, s: Sealer, x: ImportedRecurring) -> None:
    t = "money_recurring"
    conn.execute(
        "INSERT INTO money_recurring (id, user_id, project_id, amount, currency, description, vendor, cadence, "
        "anchor_day, next_due, created_at, updated_at, deleted_at, tainted) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (x.id, s.user_id, x.project_id, s.money(t, "amount", x.amount), x.currency, s.seal(t, "description", x.description),
         s.seal(t, "vendor", x.vendor), s.seal(t, "cadence", x.cadence), x.anchor_day, x.next_due, x.created_at,
         x.updated_at, x.deleted_at, x.tainted))
