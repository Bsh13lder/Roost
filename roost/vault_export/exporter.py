"""``VaultExporter`` — one export pass for one user, through the keeper's signed file API only.

The pass needs the user's chosen grant, live and ``read_write``; every path is relative to it, so the keeper's
``openat`` walk keeps every write inside it. It reads the disk's hashes with ``stat`` (in chunks), then for each
file follows ``plan.decide``: create (making folders), leave alone, overwrite with the expected hash, or write a
``.conflict.md`` copy. It never deletes anything. The keeper's per-minute limit or an away keeper ends the pass
early (``partial`` / ``away``); the manifest keeps what was written, so the next pass carries on. One pass per
user at a time; the ``vault_export_changed`` frame carries the result's code and counts, never a path."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from typing import Callable, Mapping, Sequence

from roost.constants import MAC_STAT_MAX_PATHS, VAULT_EXPORT_ACTOR_ID, VAULT_EXPORT_MANIFEST_MAX
from roost.desk import DeskUnavailable
from roost.events.hub import EventHub
from roost.keeper.macfs.errors import MacFsError
from roost.mac.files import MacFiles
from roost.mac.grants import GrantStore
from roost.mac.models import FileRef, Grant
from roost.vault_export.plan import conflict_path, decide
from roost.vault_export.render import ExportFile
from roost.vault_export.sources import ExportSources
from roost.vault_export.store import ExportResult, VaultExportStore

log = logging.getLogger(__name__)

_STOP_CODES = {"rate_limited": "partial", "grants_unset": "away", "no_grant": "no_grant", "read_only": "no_grant"}


class _Stop(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class _Pass:
    """One pass's running state: the manifest it builds and its counts (local to one ``run``)."""

    grant: Grant
    manifest: dict[str, str]
    written: int = 0
    conflicts: int = 0
    failed: int = 0

    @property
    def actor(self) -> str:
        return self.grant.bot_id or VAULT_EXPORT_ACTOR_ID

    def ref(self, path: str) -> FileRef:
        return FileRef(self.grant.id, self.actor, path)

    def result(self, code: str) -> ExportResult:
        return ExportResult(code, self.written, self.conflicts, self.failed)


class VaultExporter:
    def __init__(self, store: VaultExportStore, sources: ExportSources, files: MacFiles, grants: GrantStore,
                 events: EventHub, *, today: Callable[[], date]) -> None:
        self._store = store
        self._sources = sources
        self._files = files
        self._grants = grants
        self._events = events
        self._today = today
        self._locks: dict[str, asyncio.Lock] = {}

    async def run(self, user_id: str) -> ExportResult:
        lock = self._locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            return await self._run(user_id)

    async def _run(self, user_id: str) -> ExportResult:
        settings = await self._store.settings(user_id)
        project_ids = await self._store.exported_projects(user_id)
        if settings.grant_id is None or (not project_ids and not settings.journals):
            return ExportResult("off")
        grant = await self._grants.get(user_id, settings.grant_id)
        if grant is None or grant.access != "read_write":
            return await self._finish(user_id, settings.manifest, ExportResult("no_grant"))
        files = await self._sources.files(user_id, project_ids, journals=settings.journals, today=self._today())
        state = _Pass(grant, dict(settings.manifest))
        code = await self._write_all(state, files[:VAULT_EXPORT_MANIFEST_MAX])
        if code == "ok" and len(files) > VAULT_EXPORT_MANIFEST_MAX:
            code = "partial"
        return await self._finish(user_id, state.manifest, state.result(code))

    async def _finish(self, user_id: str, manifest: Mapping[str, str], result: ExportResult) -> ExportResult:
        await self._store.save_run(user_id, manifest, result)
        await self._events.publish(user_id, {"type": "vault_export_changed", "result": result.code,
                                             "written": result.written, "conflicts": result.conflicts})
        return result

    async def _write_all(self, state: _Pass, files: Sequence[ExportFile]) -> str:
        try:
            on_disk = await self._hashes(state, [f.path for f in files])
            for file in files:
                await self._one(state, file, on_disk.get(file.path))
        except _Stop as stop:
            return stop.code
        except DeskUnavailable:
            return "away"
        except MacFsError as exc:   # a stat the keeper refused outright: nothing more can be judged
            log.info("the vault export stopped: %s", exc.code)
            return "failed"
        return "failed" if state.failed and not state.written else "ok"

    async def _hashes(self, state: _Pass, paths: Sequence[str]) -> dict[str, str | None]:
        found: dict[str, str | None] = {}
        for start in range(0, len(paths), MAC_STAT_MAX_PATHS):
            chunk = paths[start:start + MAC_STAT_MAX_PATHS]
            stats = await self._step(self._files.stat(state.grant.id, state.actor, chunk))
            found.update({s.path: s.sha256 for s in stats})
        return found

    async def _one(self, state: _Pass, file: ExportFile, on_disk: str | None) -> None:
        decision = decide(file.text, state.manifest.get(file.path), on_disk)
        if decision.action == "conflict":
            state.conflicts += 1
            await self._conflict_copy(state, file)
            return
        if decision.action == "same":
            state.manifest[file.path] = decision.sha256
            return
        done = await self._put(state, file.path, file.text, decision.expected)
        if done:
            state.manifest[file.path] = decision.sha256
            state.written += 1

    async def _conflict_copy(self, state: _Pass, file: ExportFile) -> None:
        """The copy beside a file Roost may not overwrite; a copy someone edited is left alone too."""
        path = conflict_path(file.path)
        [stat] = await self._step(self._files.stat(state.grant.id, state.actor, [path]))
        decision = decide(file.text, state.manifest.get(path), stat.sha256)
        if decision.action == "conflict":
            return
        if decision.action == "same" or await self._put(state, path, file.text, decision.expected):
            state.manifest[path] = decision.sha256

    async def _put(self, state: _Pass, path: str, text: str, expected: str | None) -> bool:
        """Create or overwrite one file. ``False``: the keeper refused this one file (counted as failed)."""
        try:
            if expected is None:
                await self._step(self._files.create(state.ref(path), text, parents=True))
            else:
                await self._step(self._files.write(state.ref(path), text, expected))
        except MacFsError as exc:
            log.info("the vault export skipped a file: %s", exc.code)
            state.failed += 1
            return False
        return True

    @staticmethod
    async def _step(awaitable):
        """Run one keeper call; a refusal that ends the whole pass becomes ``_Stop``."""
        try:
            return await awaitable
        except MacFsError as exc:
            if exc.code in _STOP_CODES:
                raise _Stop(_STOP_CODES[exc.code]) from None
            raise
