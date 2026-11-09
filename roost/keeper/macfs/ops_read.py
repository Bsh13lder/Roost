"""Reading operations: check a folder, list, read, stat. Each runs in a worker thread with the
grant's root already open; paths are walked with ``openat`` (paths.py), never joined into strings."""

from __future__ import annotations

import hashlib
import os
import stat
import unicodedata

from roost.constants import MAC_LIST_MAX_ENTRIES, MAC_NAME_MAX_CHARS, MAC_READ_MAX_BYTES
from roost.keeper.macfs.deny import check_grant_root, is_denied_name
from roost.keeper.macfs.errors import MacFsError
from roost.keeper.macfs.grants import KeeperGrant
from roost.keeper.macfs.paths import is_dataless, map_oserror, open_dir, open_file, split_rel

_VAULT_DIR = ".obsidian"
_BOM = "﻿"


class BadGrant(Exception):
    def __init__(self, grant_id: str) -> None:
        super().__init__("bad_grant")
        self.grant_id = grant_id


def clean_name(name: str) -> str:
    """A name as shown to the model: control characters stripped, length capped."""
    kept = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")
    return kept[:MAC_NAME_MAX_CHARS]


def check_folder(home: str, path: str) -> dict[str, object]:
    """Resolve a folder the user picked and apply the deny list to what it resolves to."""
    if not path or "\0" in path or not path.startswith("/"):
        raise MacFsError("bad_path")
    resolved = os.path.realpath(path)
    check_grant_root(resolved, home)
    try:
        st = os.lstat(resolved)
    except OSError as exc:
        raise map_oserror(exc) from None
    if not stat.S_ISDIR(st.st_mode):
        raise MacFsError("bad_path")
    return {"resolved": resolved, "is_vault": _is_vault(resolved)}


def _is_vault(resolved: str) -> bool:
    try:
        return stat.S_ISDIR(os.lstat(os.path.join(resolved, _VAULT_DIR)).st_mode)
    except OSError:
        return False


def build_grants(home: str, items: list) -> tuple[KeeperGrant, ...]:
    """Re-check every pushed root; one bad root (or a repeated id) refuses the whole set."""
    seen: set[str] = set()
    grants: list[KeeperGrant] = []
    for item in items:
        if item.grant_id in seen:
            raise BadGrant(item.grant_id)
        seen.add(item.grant_id)
        try:
            resolved = str(check_folder(home, item.root)["resolved"])
            st = os.stat(resolved)
        except (MacFsError, OSError):
            raise BadGrant(item.grant_id) from None
        grants.append(KeeperGrant(item.grant_id, resolved, item.access, item.bot_id, st.st_dev, st.st_ino))
    return tuple(grants)


def list_folder(mac, grant: KeeperGrant, root_fd: int, body) -> dict[str, object]:
    dir_fd = open_dir(root_fd, split_rel(body.path), mac.home)
    try:
        listed = _scan(dir_fd)
    finally:
        os.close(dir_fd)
    return {"entries": listed[:MAC_LIST_MAX_ENTRIES], "truncated": len(listed) > MAC_LIST_MAX_ENTRIES}


def _scan(dir_fd: int) -> list[dict[str, object]]:
    found: list[tuple[str, dict[str, object]]] = []
    with os.scandir(dir_fd) as it:
        for entry in it:
            name = entry.name
            if name.startswith(".") or is_denied_name(name) or entry.is_symlink():
                continue
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISDIR(st.st_mode):
                kind = "folder"
            elif stat.S_ISREG(st.st_mode) and st.st_nlink == 1:
                kind = "file"
            else:
                continue
            found.append((name, {"name": clean_name(name), "kind": kind,
                                 "size": 0 if kind == "folder" else st.st_size, "mtime": int(st.st_mtime)}))
    found.sort(key=lambda item: item[0])
    return [entry for _name, entry in found]


def _read_limited(fd: int, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= limit:
        chunk = os.read(fd, min(1 << 20, limit + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


def read_bytes(fd: int) -> bytes:
    """Whole file, at most ``MAC_READ_MAX_BYTES``; a dataless file is refused before any read."""
    st = os.fstat(fd)
    if is_dataless(st):
        raise MacFsError("not_downloaded")
    if st.st_size > MAC_READ_MAX_BYTES:
        raise MacFsError("too_big")
    data = _read_limited(fd, MAC_READ_MAX_BYTES)
    if len(data) > MAC_READ_MAX_BYTES:
        raise MacFsError("too_big")
    return data


def decode_text(data: bytes) -> str:
    if b"\0" in data:
        raise MacFsError("not_text")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise MacFsError("not_text") from None
    return text[1:] if text.startswith(_BOM) else text


def read_file(mac, grant: KeeperGrant, root_fd: int, body) -> dict[str, object]:
    fd = open_file(root_fd, split_rel(body.path), os.O_RDONLY, mac.home)
    try:
        st = os.fstat(fd)
        data = read_bytes(fd)
    finally:
        os.close(fd)
    return {"text": decode_text(data), "sha256": hashlib.sha256(data).hexdigest(),
            "mtime": int(st.st_mtime), "size": len(data)}


def stat_files(mac, grant: KeeperGrant, root_fd: int, body) -> dict[str, object]:
    return {"files": [_stat_one(mac, root_fd, path) for path in body.paths]}


def _stat_one(mac, root_fd: int, path: str) -> dict[str, object]:
    missing = {"path": path, "sha256": None, "mtime": 0, "size": 0}
    try:
        fd = open_file(root_fd, split_rel(path), os.O_RDONLY, mac.home)
    except MacFsError:
        return missing
    try:
        st = os.fstat(fd)
        try:
            sha = hashlib.sha256(read_bytes(fd)).hexdigest()
        except MacFsError:
            sha = None
        return {"path": path, "sha256": sha, "mtime": int(st.st_mtime), "size": st.st_size}
    finally:
        os.close(fd)
