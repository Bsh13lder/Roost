"""``ExportSources`` — reads what the export writes, for one user: the projects switched on (with their
tasks, notes and expenses) and, when asked, the bots' journal days of the last ``VAULT_EXPORT_JOURNAL_DAYS``."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Sequence

from roost.bots.store import BotStore
from roost.config import Config
from roost.constants import NOTE_SCAN_LIMIT, VAULT_EXPORT_JOURNAL_DAYS, VAULT_EXPORT_MANIFEST_MAX
from roost.journal.store import JournalStore
from roost.money.expense_store import ExpenseStore
from roost.money.project_store import ProjectStore
from roost.notes.store import NoteStore
from roost.tasks.store import TaskStore
from roost.vault_export.render import ExportFile, ProjectBundle, journal_files, project_files


class ExportSources:
    def __init__(self, config: Config) -> None:
        self._projects = ProjectStore(config)
        self._tasks = TaskStore(config)
        self._notes = NoteStore(config)
        self._expenses = ExpenseStore(config)
        self._journals = JournalStore(config)
        self._bots = BotStore(config)

    async def _bundles(self, user_id: str, project_ids: Sequence[str]) -> tuple[ProjectBundle, ...]:
        wanted = set(project_ids)
        bundles = []
        for project in await self._projects.list(user_id):
            if project.id not in wanted:
                continue
            bundles.append(ProjectBundle(
                project=project,
                tasks=await self._tasks.list(user_id, status="all", project_id=project.id),
                notes=await self._notes.for_project(user_id, project.id, NOTE_SCAN_LIMIT),
                expenses=await self._expenses.list_project(user_id, project.id),
            ))
        return tuple(bundles)

    async def files(self, user_id: str, project_ids: Sequence[str], *, journals: bool,
                    today: date) -> tuple[ExportFile, ...]:
        out = project_files(await self._bundles(user_id, project_ids))
        if journals:
            days = await self._journals.since(user_id, today - timedelta(days=VAULT_EXPORT_JOURNAL_DAYS),
                                              VAULT_EXPORT_MANIFEST_MAX)
            names = {bot.id: bot.name for bot in await self._bots.list(user_id)}
            out = (*out, *journal_files(days, names))
        return out
