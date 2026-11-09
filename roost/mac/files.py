"""The gateway's seam to the Mac: ``MacFiles`` is what the rest of Roost calls, ``KeeperMacFiles``
sends it to the keeper (``KeeperClient.mac``), and ``make_mac_files`` picks the fake in fake mode.

Every failure is a ``MacFsError`` (a coded refusal) or ``DeskUnavailable`` (the keeper is away).
A keeper that answers ``grants_unset`` (it restarted and forgot the grants) gets the last pushed
set again, and the call is retried once."""

from __future__ import annotations

import logging
from typing import Any, Callable, Protocol, Sequence

from roost.config import RoostConfig
from roost.desk import DeskUnavailable
from roost.desk.client import KeeperClient
from roost.constants import MAC_PICK_REQUEST_TIMEOUT_S
from roost.keeper.macfs.errors import MacFsError
from roost.mac.models import (
    Entry, FileRef, FileStat, FileText, FindHit, FindResult, FolderCheck, Grant, ListResult, TrashResult,
    UndoSpec, WriteResult,
)

log = logging.getLogger(__name__)


class MacFiles(Protocol):
    async def push_grants(self, grants: Sequence[Grant]) -> None: ...
    async def check_folder(self, path: str) -> FolderCheck: ...
    async def pick_folder(self) -> str | None: ...
    async def list(self, ref: FileRef) -> ListResult: ...
    async def find(self, grant_id: str, bot_id: str, *, name: str | None = None, text: str | None = None,
                   path: str = "") -> FindResult: ...
    async def read(self, ref: FileRef) -> FileText: ...
    async def stat(self, grant_id: str, bot_id: str, paths: Sequence[str]) -> tuple[FileStat, ...]: ...
    async def create(self, ref: FileRef, text: str, *, parents: bool = False) -> WriteResult: ...
    async def write(self, ref: FileRef, text: str, expected_sha256: str) -> WriteResult: ...
    async def rename(self, ref: FileRef, new_path: str, expected_sha256: str) -> str: ...
    async def trash(self, ref: FileRef, expected_sha256: str) -> TrashResult: ...
    async def undo(self, grant_id: str, bot_id: str, spec: UndoSpec) -> str | None: ...


def _grant_payload(grant: Grant) -> dict[str, Any]:
    return {"grant_id": grant.id, "root": grant.path, "access": grant.access, "bot_id": grant.bot_id}


def _fs(ref_or_ids: Any, **fields: Any) -> dict[str, Any]:
    grant_id, bot_id = ref_or_ids.grant_id, ref_or_ids.bot_id
    return {"grant_id": grant_id, "bot_id": bot_id, **fields}


def _shaped(build: Callable[[], Any]) -> Any:
    """Build a result from the keeper's answer; an answer of the wrong shape is a keeper problem."""
    try:
        return build()
    except (KeyError, TypeError, ValueError):
        raise DeskUnavailable("the keeper's Mac answer had an unexpected shape") from None


class KeeperMacFiles:
    def __init__(self, config: RoostConfig, client: KeeperClient | None = None) -> None:
        self._client = client if client is not None else KeeperClient(config)
        self._last: tuple[Grant, ...] = ()   # what the keeper must hold; re-pushed when it forgets

    async def push_grants(self, grants: Sequence[Grant]) -> None:
        """Replace the keeper's grants. A folder that has gone away makes the keeper refuse the whole
        set (``bad_grant``); that grant is left out, so one dead folder never keeps a revoke from landing."""
        self._last = tuple(grants)
        remaining = list(grants)
        for _ in range(len(remaining) + 1):
            try:
                await self._client.mac("/mac/grants", {"grants": [_grant_payload(g) for g in remaining]}, method="PUT")
                return
            except MacFsError as exc:
                if exc.code != "bad_grant" or exc.grant_id is None:
                    raise
                log.info("the keeper refused a grant's folder; leaving it out of the push")
                remaining = [g for g in remaining if g.id != exc.grant_id]

    async def _call(self, route: str, payload: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        kwargs = {} if timeout is None else {"timeout": timeout}
        try:
            return await self._client.mac(route, payload, **kwargs)
        except MacFsError as exc:
            if exc.code != "grants_unset":
                raise
        await self.push_grants(self._last)
        return await self._client.mac(route, payload, **kwargs)

    async def check_folder(self, path: str) -> FolderCheck:
        out = await self._call("/mac/check-folder", {"path": path})
        return _shaped(lambda: FolderCheck(out["resolved"], bool(out["is_vault"])))

    async def pick_folder(self) -> str | None:
        out = await self._call("/mac/pick-folder", {}, timeout=MAC_PICK_REQUEST_TIMEOUT_S)
        return _shaped(lambda: out["path"])

    async def list(self, ref: FileRef) -> ListResult:
        out = await self._call("/mac/fs/list", _fs(ref, path=ref.path))
        return _shaped(lambda: ListResult(
            tuple(Entry(e["name"], e["kind"], e["size"], e["mtime"]) for e in out["entries"]), bool(out["truncated"])))

    async def find(self, grant_id: str, bot_id: str, *, name: str | None = None, text: str | None = None,
                   path: str = "") -> FindResult:
        fields = {key: value for key, value in (("name", name), ("text", text)) if value is not None}
        out = await self._call("/mac/fs/find", {"grant_id": grant_id, "bot_id": bot_id, "path": path, **fields})
        return _shaped(lambda: FindResult(
            tuple(FindHit(h["path"], h["size"], h["mtime"], tuple(h["snippets"])) for h in out["hits"]),
            bool(out["truncated"])))

    async def read(self, ref: FileRef) -> FileText:
        out = await self._call("/mac/fs/read", _fs(ref, path=ref.path))
        return _shaped(lambda: FileText(out["text"], out["sha256"], out["mtime"], out["size"]))

    async def stat(self, grant_id: str, bot_id: str, paths: Sequence[str]) -> tuple[FileStat, ...]:
        out = await self._call("/mac/fs/stat", {"grant_id": grant_id, "bot_id": bot_id, "paths": list(paths)})
        return _shaped(lambda: tuple(FileStat(f["path"], f["sha256"], f["mtime"], f["size"]) for f in out["files"]))

    async def create(self, ref: FileRef, text: str, *, parents: bool = False) -> WriteResult:
        extra = {"parents": True} if parents else {}
        out = await self._call("/mac/fs/create", _fs(ref, path=ref.path, text=text, **extra))
        return _shaped(lambda: WriteResult(out["sha256"], out["size"], None))

    async def write(self, ref: FileRef, text: str, expected_sha256: str) -> WriteResult:
        out = await self._call("/mac/fs/write", _fs(ref, path=ref.path, text=text, expected_sha256=expected_sha256))
        return _shaped(lambda: WriteResult(out["sha256"], out["size"], out["backup_id"]))

    async def rename(self, ref: FileRef, new_path: str, expected_sha256: str) -> str:
        out = await self._call(
            "/mac/fs/rename", _fs(ref, path=ref.path, new_path=new_path, expected_sha256=expected_sha256))
        return _shaped(lambda: out["sha256"])

    async def trash(self, ref: FileRef, expected_sha256: str) -> TrashResult:
        out = await self._call("/mac/fs/trash", _fs(ref, path=ref.path, expected_sha256=expected_sha256))
        return _shaped(lambda: TrashResult(out["trash_name"]))

    async def undo(self, grant_id: str, bot_id: str, spec: UndoSpec) -> str | None:
        fields = {key: value for key, value in (
            ("path", spec.path), ("backup_id", spec.backup_id), ("back_to", spec.back_to),
            ("trash_name", spec.trash_name), ("expected_sha256", spec.expected_sha256)) if value is not None}
        out = await self._call("/mac/fs/undo", {"grant_id": grant_id, "bot_id": bot_id, "kind": spec.kind, **fields})
        return _shaped(lambda: out["sha256"])


def make_mac_files(config: RoostConfig) -> MacFiles:
    """The fake in fake mode (every test and E2E run), the keeper otherwise."""
    if config.desk_mode == "fake":
        from roost.mac.fake_files import FakeMacFiles, load_fake_tree

        tree = load_fake_tree(config.fake_mac_tree) if config.fake_mac_tree is not None else {}
        return FakeMacFiles(tree, str(config.mac_home.resolve()))
    return KeeperMacFiles(config)


