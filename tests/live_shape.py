"""The live account's shape (S1 D4/D6), built in a test's own temp data dir.

It uses the CURRENT schema (``tests/fixtures/schema_v10.sql``), migrated by
``init_db`` like the real boot, plus real encrypted rows made through the
stores: bots, a thread with messages, a task, an expense, a note and a
document. It never touches ~/Roost/data (``tests/conftest.py``'s tripwire)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from roost.bots.models import Avatar, BotDraft
from roost.bots.store import BotStore
from roost.db.connection import get_db_path, init_db
from roost.documents.service import DocumentService
from roost.documents.store import DocumentStore
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.money.expense_store import ExpenseStore
from roost.money.project_store import ProjectStore
from roost.money.service import ExpenseEntry, MoneyService
from roost.notes.models import NoteDraft
from roost.notes.service import NoteService
from roost.notes.store import NoteStore
from roost.talk.store import TalkStore
from roost.tasks.models import TaskDraft
from roost.tasks.service import TaskService
from roost.tasks.store import TaskStore

V10_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v10.sql"
COUNTED = ("users", "bots", "bot_roles", "threads", "messages", "tasks", "money_expenses", "notes", "documents")
AVATAR = Avatar("round", "#22c55e", "none")


def _create_v10_file(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.executescript(V10_SCHEMA.read_text())
        con.execute("PRAGMA user_version = 10")
        con.commit()
    finally:
        con.close()


async def _records(cfg, user_id: str, bot_id: str) -> None:
    events = EventHub(cfg)
    talk = TalkStore(cfg)
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "hello")
    await talk.add_message(user_id, thread.id, "bot", "hi", author_bot_id=bot_id)
    await TaskService(TaskStore(cfg), events).add(user_id, TaskDraft(title="Pay rent"), created_by_bot=bot_id)
    money = MoneyService(ProjectStore(cfg), ExpenseStore(cfg), events)
    await money.log_expense(user_id, ExpenseEntry(amount=Decimal("12.50"), spent_at="2026-10-03", project="food"))
    await NoteService(NoteStore(cfg), events).add(user_id, NoteDraft(title="Ideas", content="orchids"))
    await DocumentService(DocumentStore(cfg), events).create_doc(user_id, "Plan", "# Plan")


async def seed_live_account(cfg, bots: tuple[tuple[str, str | None], ...] = (("Chief", "chief"), ("Life admin", None)),
                            *, star: str | None = None, username: str = "blckit") -> str:
    """``bots`` are (name, template_id) pairs, created in order. Returns the user id."""
    _create_v10_file(get_db_path(cfg))
    await init_db(cfg)
    user = await register_user(cfg, username, "pw-123456")
    store = BotStore(cfg)
    made = {name: await store.create(user.id, BotDraft(name=name, job="helps", instructions="", avatar=AVATAR,
                                                       template_id=template_id))
            for name, template_id in bots}
    if star is not None:
        await store.set_primary(user.id, made[star].id)
    await _records(cfg, user.id, next(iter(made.values())).id)
    return user.id


def _query(cfg, sql: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def counts(cfg) -> dict[str, int]:
    return {table: _query(cfg, f"SELECT COUNT(*) FROM {table}")[0][0] for table in COUNTED}


def main_bot_ids(cfg, user_id: str) -> list[str]:
    return [row[0] for row in _query(cfg, "SELECT id FROM bots WHERE user_id = ? AND is_primary = 1", (user_id,))]
