"""Writing operations: create, write, rename, trash and undo. Each runs in a worker thread with
the grant's root open. Every one needs a ``read_write`` grant, walks with ``openat`` (paths.py),
checks the file's hash (``changed`` + the current hash), saves a backup first, and never deletes
a user's file: trash is a move into a folder."""

from __future__ import annotations

import os
import stat
from datetime import datetime, timezone

from roost.keeper.macfs.atomic import (
    check_expected,
    check_ext,
    create_new,
    encode_text,
    read_current,
    replace_file,
    sha256_hex,
)
from roost.keeper.macfs.errors import MacFsError
from roost.keeper.macfs.grants import KeeperGrant
from roost.keeper.macfs.paths import map_oserror, open_dir, open_dir_at, open_dir_making, split_rel
from roost.constants import MAC_TRASH_DIR, OBSIDIAN_TRASH_DIR

_VAULT_DIR = ".obsidian"
_TRASH_STAMP = "%Y%m%dT%H%M%S%fZ"


def _need_write(grant: KeeperGrant) -> None:
    if grant.access != "read_write":
        raise MacFsError("read_only")


def _file_parts(path: str) -> tuple[str, ...]:
    parts = split_rel(path)
    if not parts:
        raise MacFsError("bad_path")
    check_ext(parts[-1])
    return parts


def _backup(mac, grant: KeeperGrant, parts: tuple[str, ...], old: bytes) -> str:
    rel = "/".join(parts)
    backup_id = mac.backups.save(grant.grant_id, rel, old)
    mac.backups.prune(grant.grant_id, rel)
    return backup_id


def _absent(dir_fd: int, name: str) -> None:
    try:
        os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise map_oserror(exc) from None
    raise MacFsError("exists")


def _has_dir(root_fd: int, name: str) -> bool:
    try:
        return stat.S_ISDIR(os.stat(name, dir_fd=root_fd, follow_symlinks=False).st_mode)
    except OSError:
        return False


def _open_trash(root_fd: int, *, create: bool) -> int:
    name = OBSIDIAN_TRASH_DIR if _has_dir(root_fd, _VAULT_DIR) else MAC_TRASH_DIR
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        except OSError as exc:
            raise map_oserror(exc) from None
    return open_dir_at(root_fd, name)


def create_file(mac, grant: KeeperGrant, root_fd: int, body) -> dict[str, object]:
    _need_write(grant)
    parts = _file_parts(body.path)
    data = encode_text(body.text)
    walk = open_dir_making if getattr(body, "parents", False) else open_dir
    dir_fd = walk(root_fd, parts[:-1], mac.home)
    try:
        create_new(dir_fd, parts[-1], data)
    finally:
        os.close(dir_fd)
    return {"sha256": sha256_hex(data), "size": len(data)}


def _replace(mac, grant: KeeperGrant, root_fd: int, parts: tuple[str, ...], data: bytes, expected: str) -> str:
    dir_fd = open_dir(root_fd, parts[:-1], mac.home)
    try:
        old, mode = read_current(dir_fd, parts[-1])
        check_expected(old, expected)
        backup_id = _backup(mac, grant, parts, old)
        replace_file(dir_fd, parts[-1], data, mode, expected)
    finally:
        os.close(dir_fd)
    return backup_id


def write_file(mac, grant: KeeperGrant, root_fd: int, body) -> dict[str, object]:
    _need_write(grant)
    parts = _file_parts(body.path)
    data = encode_text(body.text)
    backup_id = _replace(mac, grant, root_fd, parts, data, body.expected_sha256)
    return {"sha256": sha256_hex(data), "size": len(data), "backup_id": backup_id}


def _rename(mac, grant: KeeperGrant, root_fd: int, src: tuple[str, ...], dst: tuple[str, ...], expected: str) -> str:
    src_dir = open_dir(root_fd, src[:-1], mac.home)
    try:
        dst_dir = open_dir(root_fd, dst[:-1], mac.home)
        try:
            old, _mode = read_current(src_dir, src[-1])
            check_expected(old, expected)
            _absent(dst_dir, dst[-1])
            _backup(mac, grant, src, old)
            _move(src_dir, src[-1], dst_dir, dst[-1])
        finally:
            os.close(dst_dir)
    finally:
        os.close(src_dir)
    return sha256_hex(old)


def _move(src_dir: int, src_name: str, dst_dir: int, dst_name: str) -> None:
    """Move without ever replacing: ``link`` fails if the target exists (unlike ``rename``), then
    the source name is removed. The second link lives only for this call; if removing the source
    fails, the new name is removed again so nothing is left with two links."""
    try:
        os.link(src_name, dst_name, src_dir_fd=src_dir, dst_dir_fd=dst_dir, follow_symlinks=False)
    except FileExistsError:
        raise MacFsError("exists") from None
    except OSError as exc:
        raise map_oserror(exc) from None
    try:
        os.unlink(src_name, dir_fd=src_dir)
    except OSError as exc:
        try:
            os.unlink(dst_name, dir_fd=dst_dir)
        except OSError:
            pass
        raise map_oserror(exc) from None


def rename_file(mac, grant: KeeperGrant, root_fd: int, body) -> dict[str, object]:
    _need_write(grant)
    src, dst = _file_parts(body.path), _file_parts(body.new_path)
    return {"sha256": _rename(mac, grant, root_fd, src, dst, body.expected_sha256)}


def _trash(mac, grant: KeeperGrant, root_fd: int, parts: tuple[str, ...], expected: str) -> str:
    dir_fd = open_dir(root_fd, parts[:-1], mac.home)
    try:
        old, _mode = read_current(dir_fd, parts[-1])
        check_expected(old, expected)
        _backup(mac, grant, parts, old)
        trash_fd = _open_trash(root_fd, create=True)
        try:
            trash_name = f"{datetime.now(timezone.utc).strftime(_TRASH_STAMP)}-{parts[-1]}"
            _move(dir_fd, parts[-1], trash_fd, trash_name)
        finally:
            os.close(trash_fd)
    finally:
        os.close(dir_fd)
    return trash_name


def trash_file(mac, grant: KeeperGrant, root_fd: int, body) -> dict[str, object]:
    _need_write(grant)
    parts = _file_parts(body.path)
    return {"trash_name": _trash(mac, grant, root_fd, parts, body.expected_sha256)}


def _untrash(mac, grant: KeeperGrant, root_fd: int, trash_name: str, back_to: tuple[str, ...]) -> str:
    named = split_rel(trash_name)
    if len(named) != 1:
        raise MacFsError("bad_path")
    trash_fd = _open_trash(root_fd, create=False)
    try:
        dst_dir = open_dir(root_fd, back_to[:-1], mac.home)
        try:
            old, _mode = read_current(trash_fd, named[0])
            _absent(dst_dir, back_to[-1])
            _move(trash_fd, named[0], dst_dir, back_to[-1])
        finally:
            os.close(dst_dir)
    finally:
        os.close(trash_fd)
    return sha256_hex(old)


def undo(mac, grant: KeeperGrant, root_fd: int, body) -> dict[str, object]:
    _need_write(grant)
    request = body.root
    if request.kind == "content":
        parts = _file_parts(request.path)
        data = mac.backups.load(grant.grant_id, "/".join(parts), request.backup_id)
        _replace(mac, grant, root_fd, parts, data, request.expected_sha256)
        return {"sha256": sha256_hex(data)}
    if request.kind == "create":
        _trash(mac, grant, root_fd, _file_parts(request.path), request.expected_sha256)
        return {"sha256": None}
    if request.kind == "rename":
        src, dst = _file_parts(request.path), _file_parts(request.back_to)
        return {"sha256": _rename(mac, grant, root_fd, src, dst, request.expected_sha256)}
    return {"sha256": _untrash(mac, grant, root_fd, request.trash_name, _file_parts(request.back_to))}
