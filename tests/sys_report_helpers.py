"""Shared rig for the reminder, day-summary and budget-alert job tests (not a test module)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from roost.bots.main_bot import ensure_main_bot
from roost.bots.models import Bot
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.money.expense_store import ExpenseStore
from roost.money.project_store import ProjectStore
from roost.notes.store import NoteStore
from roost.documents.store import DocumentStore
from roost.projects.service import ProjectService
from roost.routines.models import ReportBody
from roost.routines.runs import RoutineRunStore
from roost.routines.store import RoutineStore
from roost.routines.system_reports import JobDeps
from roost.talk.store import TalkStore
from roost.tasks.store import TaskStore

UTC = timezone.utc
NOW = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)     # 10:00 in Madrid


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@dataclass(frozen=True)
class Rig:
    cfg: object
    user_id: str
    main: Bot
    bots: BotStore
    talk: TalkStore
    events: EventHub
    runs: RoutineRunStore
    routines: RoutineStore
    tasks: TaskStore
    expenses: ExpenseStore
    project_store: ProjectStore
    projects: ProjectService
    deps: JobDeps

    async def reports(self, bot: Bot) -> tuple[ReportBody, ...]:
        thread = await self.talk.main_thread(self.user_id, bot.id)
        if thread is None:
            return ()
        found = await self.talk.list_messages(self.user_id, thread.id, limit=200)
        return tuple(ReportBody(**json.loads(m.body)) for m in found if m.kind == "report")

    async def count(self, table: str, **where: str) -> int:
        clause = " AND ".join(f"{k} = ?" for k in where) or "1 = 1"
        async with db_session(self.cfg) as db:
            row = await (await db.execute(f"SELECT COUNT(*) FROM {table} WHERE {clause}", tuple(where.values()))).fetchone()
        return int(row[0])


async def make_rig(username: str = "alice") -> Rig:
    cfg = load_config()
    await init_db(cfg)
    return await rig_for(cfg, username)


async def rig_for(cfg, username: str) -> Rig:
    user_id = (await register_user(cfg, username, "pw-123456")).id
    bots, talk, events = BotStore(cfg), TalkStore(cfg), EventHub(cfg)
    main = (await ensure_main_bot(bots, user_id)).bot
    runs, routines = RoutineRunStore(cfg), RoutineStore(cfg, talk)
    tasks, expenses, project_store = TaskStore(cfg), ExpenseStore(cfg), ProjectStore(cfg)
    projects = ProjectService(project_store, expenses, tasks, NoteStore(cfg), DocumentStore(cfg), bots, events)
    deps = JobDeps(cfg, bots, talk, events, runs)
    return Rig(cfg, user_id, main, bots, talk, events, runs, routines, tasks, expenses, project_store, projects, deps)
