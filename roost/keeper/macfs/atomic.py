"""The atomic file steps shared by the write operations: temp file in the same folder, fsync,
the old file's mode, a last hash check, then one ``rename`` (``openat``-relative), and a
no-clobber create (temp file plus ``link``). The only thing ever unlinked is our own temp file."""

from __future__ import annotations

import hashlib
import os
import secrets
import stat

from roost.constants import MAC_READ_MAX_BYTES, MAC_TMP_INFIX, MAC_WRITE_EXTS
from roost.keeper.macfs.errors import MacFsError
from roost.keeper.macfs.ops_read import read_bytes
from roost.keeper.macfs.paths import map_oserror, open_name

_TMP_FLAGS = os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
_NEW_FILE_MODE = 0o666   # the umask makes it the usual 0644
_TMP_SUFFIX_BYTES = 4


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_ext(name: str) -> None:
    if os.path.splitext(name)[1].casefold() not in MAC_WRITE_EXTS:
        raise MacFsError("bad_ext")


def encode_text(text: str) -> bytes:
    data = text.encode("utf-8")
    if len(data) > MAC_READ_MAX_BYTES:
        raise MacFsError("too_big")
    return data


def read_current(dir_fd: int, name: str) -> tuple[bytes, int]:
    """The file's bytes and permission bits (``not_found``, ``off_limits``, ``too_big`` ... as in a read)."""
    fd = open_name(dir_fd, name, os.O_RDONLY)
    try:
        return read_bytes(fd), stat.S_IMODE(os.fstat(fd).st_mode)
    finally:
        os.close(fd)


def check_expected(data: bytes, expected_sha256: str) -> None:
    current = sha256_hex(data)
    if current != expected_sha256:
        raise MacFsError("changed", current_sha256=current)


def _tmp_name(name: str) -> str:
    return f".{name}{MAC_TMP_INFIX}{secrets.token_hex(_TMP_SUFFIX_BYTES)}"


def _write_tmp(dir_fd: int, tmp: str, data: bytes, create_mode: int, final_mode: int | None = None) -> None:
    try:
        fd = os.open(tmp, _TMP_FLAGS, create_mode, dir_fd=dir_fd)
    except OSError as exc:
        raise map_oserror(exc) from None
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
        if final_mode is not None:
            os.fchmod(fd, final_mode)
    finally:
        os.close(fd)


def _unlink_quietly(dir_fd: int, name: str) -> None:
    try:
        os.unlink(name, dir_fd=dir_fd)
    except FileNotFoundError:
        pass


def replace_file(dir_fd: int, name: str, data: bytes, old_mode: int, expected_sha256: str) -> None:
    """Replace ``name`` with ``data`` atomically, only if it still has ``expected_sha256``."""
    tmp = _tmp_name(name)
    try:
        _write_tmp(dir_fd, tmp, data, 0o600, old_mode)
        current, _mode = read_current(dir_fd, name)       # still the file the user saw?
        check_expected(current, expected_sha256)
        os.rename(tmp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        os.fsync(dir_fd)
    except BaseException:
        _unlink_quietly(dir_fd, tmp)
        raise


def create_new(dir_fd: int, name: str, data: bytes) -> None:
    """Create ``name`` holding ``data`` and never replace anything: temp file, then ``link``."""
    tmp = _tmp_name(name)
    try:
        _write_tmp(dir_fd, tmp, data, _NEW_FILE_MODE)
        try:
            os.link(tmp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        except FileExistsError:
            raise MacFsError("exists") from None
        os.fsync(dir_fd)
    finally:
        _unlink_quietly(dir_fd, tmp)
