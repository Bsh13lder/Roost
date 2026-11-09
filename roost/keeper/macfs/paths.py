"""Symlink-free paths: a grant-relative path is split into parts and walked one part at a
time with ``openat`` (``os.open(part, ..., dir_fd=fd)``), ``O_NOFOLLOW`` on every step.

Nothing here ever builds a string path and hands it to the OS. A symlink anywhere, a hard
link, a FIFO, a socket or a device is refused. Errors carry a code, never a path or a name.
"""

from __future__ import annotations

import errno
import fcntl
import os
import stat
import unicodedata

from roost.constants import MAC_PATH_MAX_PARTS
from roost.keeper.macfs.deny import is_denied_name, is_denied_path
from roost.keeper.macfs.errors import MacFsError

__all__ = [
    "MacFsError", "split_rel", "open_dir", "open_file", "open_name", "resolved_path",
    "check_resolved", "is_dataless", "map_oserror", "open_dir_at",
]

_DATALESS_FLAG = 0x40000000  # SF_DATALESS: the file's bytes are in iCloud, not on this Mac
_NEW_DIR_MODE = 0o755
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
# O_NONBLOCK so opening a FIFO or a device never hangs; it is a no-op for a regular file.
_FILE_EXTRA = os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOCTTY | getattr(os, "O_CLOEXEC", 0)


def split_rel(path: str) -> tuple[str, ...]:
    """A grant-relative path as NFC parts. ``""`` is the grant root. Refuses (``bad_path``) a NUL,
    an empty, ``.`` or ``..`` part, a leading ``/`` or ``~`` and too many parts; refuses
    (``off_limits``) a dot part and a denied name."""
    if not isinstance(path, str) or "\0" in path:
        raise MacFsError("bad_path")
    path = unicodedata.normalize("NFC", path)
    if path == "":
        return ()
    if path[0] in "/~":
        raise MacFsError("bad_path")
    parts = tuple(path.split("/"))
    if len(parts) > MAC_PATH_MAX_PARTS or any(p in ("", ".", "..") for p in parts):
        raise MacFsError("bad_path")
    for part in parts:
        if part.startswith(".") or is_denied_name(part):
            raise MacFsError("off_limits")
    return parts


def map_oserror(exc: OSError) -> MacFsError:
    """The code for a failed ``open``: a link or a non-folder is ``off_limits``, a missing name
    ``not_found``, a refusal by macOS ``mac_said_no``, anything else ``bad_path``."""
    code = exc.errno
    if code in (errno.ELOOP, errno.ENOTDIR, errno.ENXIO, errno.EISDIR):
        return MacFsError("off_limits")
    if code == errno.ENOENT:
        return MacFsError("not_found")
    if code in (errno.EACCES, errno.EPERM):
        return MacFsError("mac_said_no")
    return MacFsError("bad_path")


def resolved_path(fd: int, fallback: str | None = None) -> str:
    """The path the kernel says ``fd`` is at: ``F_GETPATH`` on macOS, ``/proc`` on Linux,
    else ``fallback`` (the lexical join the caller built)."""
    getpath = getattr(fcntl, "F_GETPATH", None)
    if getpath is not None:
        raw = fcntl.fcntl(fd, getpath, b"\0" * 1024)
        return os.fsdecode(raw.split(b"\0", 1)[0])
    try:
        return os.readlink(f"/proc/self/fd/{fd}")
    except OSError:
        if fallback is None:
            raise MacFsError("bad_path") from None
        return fallback


def check_resolved(fd: int, home: str | None, fallback: str | None = None) -> None:
    """Judge the path the kernel resolved for ``fd`` with the deny list again (``off_limits``)."""
    if home is None:
        return
    if is_denied_path(resolved_path(fd, fallback), home):
        raise MacFsError("off_limits")


def is_dataless(st: os.stat_result) -> bool:
    """True for an iCloud file that is not downloaded (reading it would start a download)."""
    return bool(getattr(st, "st_flags", 0) & _DATALESS_FLAG)


def open_dir_at(dir_fd: int, part: str) -> int:
    try:
        return os.open(part, _DIR_FLAGS, dir_fd=dir_fd)
    except OSError as exc:
        raise map_oserror(exc) from None


def open_dir(root_fd: int, parts: tuple[str, ...], home: str | None = None) -> int:
    """Walk ``parts`` below ``root_fd``, one ``openat`` each, and return a new fd the caller closes."""
    fd = os.dup(root_fd)
    try:
        for part in parts:
            next_fd = open_dir_at(fd, part)
            os.close(fd)
            fd = next_fd
        check_resolved(fd, home)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _make_dir_at(dir_fd: int, part: str) -> int:
    """Open ``part`` below ``dir_fd``, making it first when it is missing (never through a link: ``mkdir``
    does not follow one, and the open that follows refuses one)."""
    try:
        return open_dir_at(dir_fd, part)
    except MacFsError as exc:
        if exc.code != "not_found":
            raise
    try:
        os.mkdir(part, _NEW_DIR_MODE, dir_fd=dir_fd)
    except FileExistsError:
        pass
    except OSError as exc:
        raise map_oserror(exc) from None
    return open_dir_at(dir_fd, part)


def open_dir_making(root_fd: int, parts: tuple[str, ...], home: str | None = None) -> int:
    """``open_dir``, making each missing folder on the way (the parts already passed ``split_rel``: no dot
    part, no denied name). The folder reached is judged again by the path the kernel resolved."""
    fd = os.dup(root_fd)
    try:
        for part in parts:
            next_fd = _make_dir_at(fd, part)
            os.close(fd)
            fd = next_fd
        check_resolved(fd, home)
    except BaseException:
        os.close(fd)
        raise
    return fd


def open_name(dir_fd: int, name: str, flags: int) -> int:
    """Open one regular file by name inside ``dir_fd``: no symlink, one link, not a FIFO/device."""
    try:
        fd = os.open(name, flags | _FILE_EXTRA, dir_fd=dir_fd)
    except OSError as exc:
        raise map_oserror(exc) from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise MacFsError("off_limits")
    except BaseException:
        os.close(fd)
        raise
    return fd


def open_file(root_fd: int, parts: tuple[str, ...], flags: int, home: str | None = None) -> int:
    """Walk to the folder of ``parts`` and open its last part as a regular file. The caller closes it."""
    if not parts:
        raise MacFsError("bad_path")
    dir_fd = open_dir(root_fd, parts[:-1], home)
    try:
        fd = open_name(dir_fd, parts[-1], flags)
    finally:
        os.close(dir_fd)
    try:
        check_resolved(fd, home)
    except BaseException:
        os.close(fd)
        raise
    return fd
