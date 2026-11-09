"""``FakeMacFiles``: the Mac in memory, for tests and the E2E (``ROOST_DESK=fake``).

It follows the keeper's rules and codes: the same pure deny list, the same path rules
(``split_rel``), ``exists`` / ``changed`` / ``read_only`` / ``not_text`` / ``bad_ext`` and the rest.
It never touches the disk. ``tree`` maps a path below ``home`` (``"Notes/Tasks.md"``) to its text;
a key ending in ``/`` is an empty folder. Every change builds a new dict.

Test hooks: ``fail`` makes every call raise ``DeskUnavailable``; ``grants`` and ``pushes`` show what
was pushed; ``replace_tree`` swaps the files."""

from __future__ import annotations

import hashlib
import posixpath
from pathlib import Path
from typing import Mapping, Sequence

from pydantic import RootModel, ValidationError

from roost.constants import (
    MAC_LIST_MAX_ENTRIES, MAC_NAME_MAX_CHARS, MAC_READ_MAX_BYTES, MAC_TRASH_DIR, MAC_WRITE_EXTS, OBSIDIAN_TRASH_DIR,
)
from roost.desk import DeskUnavailable
from roost.keeper.macfs.deny import check_grant_root, is_denied_name
from roost.keeper.macfs.errors import MacFsError
from roost.keeper.macfs.find import name_matches, snippets
from roost.keeper.macfs.paths import split_rel
from roost.mac.models import (
    Entry, FileRef, FileStat, FileText, FindHit, FindResult, FolderCheck, Grant, ListResult, TrashResult,
    UndoSpec, WriteResult,
)

_BASE_MTIME = 1_700_000_000


class _Tree(RootModel[dict[str, str]]):
    pass


def load_fake_tree(path: Path) -> dict[str, str]:
    """Read and validate a fake tree file: a JSON object of relative path -> text."""
    try:
        tree = _Tree.model_validate_json(Path(path).read_text(encoding="utf-8")).root
    except (OSError, ValidationError) as exc:
        raise ValueError(f"The fake Mac tree {path} can't be read: {type(exc).__name__}.") from None
    for key in tree:
        try:
            split_rel(key.rstrip("/"))
        except MacFsError:
            raise ValueError("The fake Mac tree holds a path that is not allowed.") from None
    return dict(tree)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _hidden(name: str) -> bool:
    return name.startswith(".") or is_denied_name(name)


class FakeMacFiles:
    def __init__(self, tree: Mapping[str, str], home: str) -> None:
        self._home = posixpath.normpath(home)
        self._tree: dict[str, str] = dict(tree)
        self._versions: dict[str, int] = {}
        self._backups: dict[str, tuple[str, str]] = {}
        self._counter = 0
        self._grants: dict[str, Grant] | None = None
        self.fail = False
        self.pushes = 0

    # --- test hooks ---------------------------------------------------------------------------
    @property
    def grants(self) -> tuple[Grant, ...]:
        return tuple((self._grants or {}).values())

    def replace_tree(self, tree: Mapping[str, str]) -> None:
        self._tree = dict(tree)

    # --- plumbing -----------------------------------------------------------------------------
    def _away(self) -> None:
        if self.fail:
            raise DeskUnavailable("the fake keeper is away")

    def _grant(self, grant_id: str, bot_id: str, *, write: bool = False) -> tuple[Grant, str]:
        self._away()
        if self._grants is None:
            raise MacFsError("grants_unset")
        grant = self._grants.get(grant_id)
        if grant is None or (grant.bot_id is not None and grant.bot_id != bot_id):
            raise MacFsError("no_grant")
        if write and grant.access != "read_write":
            raise MacFsError("read_only")
        return grant, posixpath.relpath(grant.path, self._home)

    def _is_folder(self, key: str) -> bool:
        return any(k == key + "/" or k.startswith(key + "/") for k in self._tree)

    def _is_file(self, key: str) -> bool:
        return key in self._tree and not key.endswith("/")

    def _touch(self, key: str) -> None:
        self._counter += 1
        self._versions[key] = self._counter

    def _put(self, key: str, text: str) -> None:
        self._tree = {**self._tree, key: text}
        self._touch(key)

    def _drop(self, key: str) -> None:
        self._tree = {k: v for k, v in self._tree.items() if k != key}

    def _file_key(self, root: str, path: str, *, ext: bool = False) -> tuple[str, tuple[str, ...]]:
        parts = split_rel(path)
        if not parts:
            raise MacFsError("bad_path")
        if ext and posixpath.splitext(parts[-1])[1].casefold() not in MAC_WRITE_EXTS:
            raise MacFsError("bad_ext")
        return "/".join((root, *parts)), parts

    def _need_parent(self, root: str, parts: tuple[str, ...]) -> None:
        parent = "/".join((root, *parts[:-1]))
        if parts[:-1] and not self._is_folder(parent):
            raise MacFsError("not_found")

    def _current(self, key: str) -> str:
        if self._is_folder(key) and not self._is_file(key):
            raise MacFsError("off_limits")
        if not self._is_file(key):
            raise MacFsError("not_found")
        text = self._tree[key]
        if "\0" in text:
            raise MacFsError("not_text")
        if len(text.encode()) > MAC_READ_MAX_BYTES:
            raise MacFsError("too_big")
        return text

    def _mtime(self, key: str) -> int:
        return _BASE_MTIME + self._versions.get(key, 0)

    def _expect(self, text: str, expected: str) -> None:
        if _sha(text) != expected:
            raise MacFsError("changed", current_sha256=_sha(text))

    def _backup(self, grant: Grant, rel: str, text: str) -> str:
        self._counter += 1
        backup_id = f"fake-backup-{self._counter}"
        self._backups = {**self._backups, backup_id: (f"{grant.id}:{rel}", text)}
        return backup_id

    def _trash_dir(self, root: str) -> str:
        return f"{root}/{OBSIDIAN_TRASH_DIR if self._is_folder(root + '/.obsidian') else MAC_TRASH_DIR}"

    # --- the seam -----------------------------------------------------------------------------
    async def push_grants(self, grants: Sequence[Grant]) -> None:
        self._away()
        self._grants = {g.id: g for g in grants}
        self.pushes += 1

    async def check_folder(self, path: str) -> FolderCheck:
        self._away()
        if not path or "\0" in path or not path.startswith("/"):
            raise MacFsError("bad_path")
        resolved = posixpath.normpath(path)
        check_grant_root(resolved, self._home)
        key = posixpath.relpath(resolved, self._home)
        if not self._is_folder(key):
            raise MacFsError("not_found")
        return FolderCheck(resolved, self._is_folder(key + "/.obsidian"))

    async def pick_folder(self) -> str | None:
        self._away()
        tops = sorted({k.split("/", 1)[0] for k in self._tree if "/" in k and not _hidden(k.split("/", 1)[0])})
        return f"{self._home}/{tops[0]}" if tops else None

    async def list(self, ref: FileRef) -> ListResult:
        _grant, root = self._grant(ref.grant_id, ref.bot_id)
        parts = split_rel(ref.path)
        base = "/".join((root, *parts))
        if parts and not self._is_folder(base):
            raise MacFsError("not_found")
        seen: dict[str, Entry] = {}
        for key, text in self._tree.items():
            if not key.startswith(base + "/"):
                continue
            head, _, rest = key[len(base) + 1:].partition("/")
            if not head or _hidden(head) or head in seen:
                continue
            child = f"{base}/{head}"
            seen[head] = (Entry(head[:MAC_NAME_MAX_CHARS], "folder", 0, 0) if rest
                          else Entry(head[:MAC_NAME_MAX_CHARS], "file", len(text.encode()), self._mtime(child)))
        entries = tuple(seen[name] for name in sorted(seen))
        return ListResult(entries[:MAC_LIST_MAX_ENTRIES], len(entries) > MAC_LIST_MAX_ENTRIES)

    async def find(self, grant_id: str, bot_id: str, *, name: str | None = None, text: str | None = None,
                   path: str = "") -> FindResult:
        _grant, root = self._grant(grant_id, bot_id)
        parts = split_rel(path)
        base = "/".join((root, *parts))
        hits: list[FindHit] = []
        for key in sorted(self._tree):
            rel = key[len(base) + 1:]
            if key.endswith("/") or not key.startswith(base + "/") or any(_hidden(p) for p in rel.split("/")):
                continue
            body = self._tree[key]
            if name is not None and not name_matches(rel.rsplit("/", 1)[-1].casefold(), name):
                continue
            found: list[str] = []
            if text is not None:
                found = snippets(body, text) if "\0" not in body else []
                if not found:
                    continue
            hits.append(FindHit("/".join((*parts, rel)), len(body.encode()), self._mtime(key), tuple(found)))
        return FindResult(tuple(hits), False)

    async def read(self, ref: FileRef) -> FileText:
        _grant, root = self._grant(ref.grant_id, ref.bot_id)
        key, _parts = self._file_key(root, ref.path)
        body = self._current(key)
        return FileText(body, _sha(body), self._mtime(key), len(body.encode()))

    async def stat(self, grant_id: str, bot_id: str, paths: Sequence[str]) -> tuple[FileStat, ...]:
        _grant, root = self._grant(grant_id, bot_id)
        out: list[FileStat] = []
        for path in paths:
            try:
                key, _parts = self._file_key(root, path)
                body = self._current(key)
                out.append(FileStat(path, _sha(body), self._mtime(key), len(body.encode())))
            except MacFsError:
                out.append(FileStat(path, None, 0, 0))
        return tuple(out)

    async def create(self, ref: FileRef, text: str, *, parents: bool = False) -> WriteResult:
        _grant, root = self._grant(ref.grant_id, ref.bot_id, write=True)
        key, parts = self._file_key(root, ref.path, ext=True)
        if len(text.encode()) > MAC_READ_MAX_BYTES:
            raise MacFsError("too_big")
        if not parents:
            self._need_parent(root, parts)
        elif any(self._is_file("/".join((root, *parts[:n]))) for n in range(1, len(parts))):
            raise MacFsError("off_limits")   # a file where a folder must go
        if key in self._tree or self._is_folder(key):
            raise MacFsError("exists")
        self._put(key, text)
        return WriteResult(_sha(text), len(text.encode()), None)

    async def write(self, ref: FileRef, text: str, expected_sha256: str) -> WriteResult:
        grant, root = self._grant(ref.grant_id, ref.bot_id, write=True)
        key, parts = self._file_key(root, ref.path, ext=True)
        if len(text.encode()) > MAC_READ_MAX_BYTES:
            raise MacFsError("too_big")
        old = self._current(key)
        self._expect(old, expected_sha256)
        backup_id = self._backup(grant, "/".join(parts), old)
        self._put(key, text)
        return WriteResult(_sha(text), len(text.encode()), backup_id)

    def _move(self, grant: Grant, root: str, src: str, dst: str, expected: str) -> str:
        src_key, src_parts = self._file_key(root, src, ext=True)
        dst_key, dst_parts = self._file_key(root, dst, ext=True)
        old = self._current(src_key)
        self._expect(old, expected)
        self._need_parent(root, dst_parts)
        if dst_key in self._tree or self._is_folder(dst_key):
            raise MacFsError("exists")
        self._backup(grant, "/".join(src_parts), old)
        self._drop(src_key)
        self._put(dst_key, old)
        return _sha(old)

    async def rename(self, ref: FileRef, new_path: str, expected_sha256: str) -> str:
        grant, root = self._grant(ref.grant_id, ref.bot_id, write=True)
        return self._move(grant, root, ref.path, new_path, expected_sha256)

    def _trash(self, grant: Grant, root: str, path: str, expected: str) -> str:
        key, parts = self._file_key(root, path, ext=True)
        old = self._current(key)
        self._expect(old, expected)
        self._backup(grant, "/".join(parts), old)
        self._counter += 1
        trash_name = f"20261022T{self._counter:012d}Z-{parts[-1]}"
        self._drop(key)
        self._put(f"{self._trash_dir(root)}/{trash_name}", old)
        return trash_name

    async def trash(self, ref: FileRef, expected_sha256: str) -> TrashResult:
        grant, root = self._grant(ref.grant_id, ref.bot_id, write=True)
        return TrashResult(self._trash(grant, root, ref.path, expected_sha256))

    async def undo(self, grant_id: str, bot_id: str, spec: UndoSpec) -> str | None:
        grant, root = self._grant(grant_id, bot_id, write=True)
        if spec.kind == "create":
            self._trash(grant, root, spec.path or "", spec.expected_sha256 or "")
            return None
        if spec.kind == "rename":
            return self._move(grant, root, spec.path or "", spec.back_to or "", spec.expected_sha256 or "")
        if spec.kind == "content":
            return self._undo_content(grant, root, spec)
        named = split_rel(spec.trash_name or "")
        if len(named) != 1:
            raise MacFsError("bad_path")
        source = f"{self._trash_dir(root)}/{named[0]}"
        dst_key, dst_parts = self._file_key(root, spec.back_to or "", ext=True)
        body = self._current(source)
        self._need_parent(root, dst_parts)
        if dst_key in self._tree or self._is_folder(dst_key):
            raise MacFsError("exists")
        self._drop(source)
        self._put(dst_key, body)
        return _sha(body)

    def _undo_content(self, grant: Grant, root: str, spec: UndoSpec) -> str:
        key, parts = self._file_key(root, spec.path or "", ext=True)
        saved = self._backups.get(spec.backup_id or "")
        if saved is None or saved[0] != f"{grant.id}:{'/'.join(parts)}":
            raise MacFsError("not_found")
        old = self._current(key)
        self._expect(old, spec.expected_sha256 or "")
        self._backup(grant, "/".join(parts), old)
        self._put(key, saved[1])
        return _sha(saved[1])
