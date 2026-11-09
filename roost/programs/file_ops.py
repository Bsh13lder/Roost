"""The fixed file script ``write_file``, ``read_file``, ``list_files`` and Wipe workspace run inside the bot's
workspace container.

It is sent as ``python3 -I -c <script> <op> <path> [<base64 text>]``, every argument ``shlex``-quoted, so the
path and the text are plain arguments and never shell text. The script walks the path from ``/workspace`` one
part at a time with ``O_NOFOLLOW``: a symlink is never followed, so nothing outside the workspace is read or
written (and the container could reach nothing of the user's anyway). It answers on stdout (a file's text, or
a JSON listing) and stderr (JSON facts), and exits 3 with ``{"error": code}`` on stderr when it refuses.

``wipe`` (the owner's Wipe workspace, never a bot's tool) takes no path: it empties ``/workspace`` and the
scratch folders (``WORKSPACE_SCRATCH_DIRS``), removing a link itself and never what it points to.

The script stays Python 3.11-compatible: the workspace image is Debian bookworm's python3."""

from __future__ import annotations

import base64
import json
import shlex
from dataclasses import dataclass
from typing import Literal

from roost.constants import (
    PROGRAM_LIST_MAX_CHARS, PROGRAM_LIST_MAX_ENTRIES, PROGRAM_READ_MAX_CHARS, WORKSPACE_DIR, WORKSPACE_SCRATCH_DIRS,
)

FileOp = Literal["write", "read", "list", "wipe"]
ERROR_EXIT = 3

_SCRIPT = '''
import base64, errno, json, os, shutil, stat, sys
ROOT = "{root}"
SCRATCH = {scratch}
READ_MAX, LIST_MAX, LIST_CHARS = {read_max}, {list_max}, {list_chars}
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
def fail(code):
    sys.stderr.write(json.dumps({{"error": code}}))
    sys.exit(3)
def code_of(exc):
    if isinstance(exc, FileNotFoundError): return "not_found"
    if isinstance(exc, NotADirectoryError): return "not_dir"
    if isinstance(exc, IsADirectoryError): return "not_file"
    if isinstance(exc, PermissionError): return "denied"
    if getattr(exc, "errno", None) == errno.ELOOP: return "link"
    return "failed"
def is_link(fd, name):
    try:
        return stat.S_ISLNK(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode)
    except OSError:
        return False
def step(fd, name, make):
    if is_link(fd, name): fail("link")
    try:
        return os.open(name, DIR_FLAGS, dir_fd=fd)
    except FileNotFoundError:
        if not make: raise
        os.mkdir(name, 0o755, dir_fd=fd)
        return os.open(name, DIR_FLAGS, dir_fd=fd)
def walk(parts, make=False):
    fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY)
    for name in parts:
        nxt = step(fd, name, make)
        os.close(fd)
        fd = nxt
    return fd
def do_write(parts, data):
    fd = walk(parts[:-1], make=True)
    if is_link(fd, parts[-1]): fail("link")
    out = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644, dir_fd=fd)
    body = base64.b64decode(data)
    with os.fdopen(out, "wb") as f:
        f.write(body)
    sys.stderr.write(json.dumps({{"bytes": len(body)}}))
def do_read(parts):
    fd = walk(parts[:-1])
    if is_link(fd, parts[-1]): fail("link")
    f = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
    info = os.fstat(f)
    if not stat.S_ISREG(info.st_mode): fail("not_file")
    with os.fdopen(f, "rb") as h:
        raw = h.read(READ_MAX * 4 + 4)
    if b"\\x00" in raw: fail("binary")
    text = raw.decode("utf-8", "replace")
    cut = len(text) > READ_MAX or info.st_size > len(raw)
    sys.stdout.write(text[:READ_MAX])
    sys.stderr.write(json.dumps({{"size": info.st_size, "cut": cut}}))
def kind_of(mode):
    if stat.S_ISLNK(mode): return "link"
    if stat.S_ISDIR(mode): return "dir"
    return "file" if stat.S_ISREG(mode) else "other"
def do_list(parts):
    fd = walk(parts)
    entries, used, more = [], 2, False
    for name in sorted(os.listdir(fd)):
        mode = os.stat(name, dir_fd=fd, follow_symlinks=False)
        kind = kind_of(mode.st_mode)
        entry = {{"name": name, "kind": kind, "size": mode.st_size if kind == "file" else None}}
        used += len(json.dumps(entry)) + 2
        if len(entries) >= LIST_MAX or used > LIST_CHARS:
            more = True
            break
        entries.append(entry)
    sys.stdout.write(json.dumps({{"entries": entries, "more": more}}))
def empty(path):
    try:
        fd = os.open(path, DIR_FLAGS)
    except FileNotFoundError:
        return 0
    try:
        names = os.listdir(fd)
        for name in names:
            if stat.S_ISDIR(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode):
                shutil.rmtree(name, dir_fd=fd)
            else:
                os.unlink(name, dir_fd=fd)
        return len(names)
    finally:
        os.close(fd)
def do_wipe():
    removed = sum(empty(folder) for folder in [ROOT] + SCRATCH)
    sys.stderr.write(json.dumps({{"removed": removed}}))
def main():
    op, path = sys.argv[1], sys.argv[2]
    parts = [p for p in path.split("/") if p]
    if any(p in (".", "..") for p in parts) or (op not in ("list", "wipe") and not parts): fail("bad_path")
    if op == "wipe" and parts: fail("bad_path")
    try:
        if op == "write": do_write(parts, sys.argv[3])
        elif op == "read": do_read(parts)
        elif op == "list": do_list(parts)
        elif op == "wipe": do_wipe()
        else: fail("bad_op")
    except OSError as exc:
        fail(code_of(exc))
main()
'''


def file_ops_script(root: str = WORKSPACE_DIR, scratch: tuple[str, ...] = WORKSPACE_SCRATCH_DIRS) -> str:
    """The script with its fixed root and scratch folders (tests pass temp folders; the tools never do)."""
    return _SCRIPT.format(root=root, scratch=json.dumps(list(scratch)), read_max=PROGRAM_READ_MAX_CHARS,
                          list_max=PROGRAM_LIST_MAX_ENTRIES, list_chars=PROGRAM_LIST_MAX_CHARS)


def file_ops_argv(op: FileOp, path: str, text: str | None = None, *, root: str = WORKSPACE_DIR,
                  scratch: tuple[str, ...] = WORKSPACE_SCRATCH_DIRS) -> list[str]:
    argv = ["python3", "-I", "-c", file_ops_script(root, scratch), op, path]
    if op == "write":
        argv.append(base64.b64encode((text or "").encode("utf-8")).decode("ascii"))
    return argv


def file_ops_command(op: FileOp, path: str, text: str | None = None) -> str:
    """The one shell line the desk's ``sh -c`` runs: every argument quoted, so it parses back to the same argv."""
    return shlex.join(file_ops_argv(op, path, text))


@dataclass(frozen=True)
class ReadResult:
    text: str
    size: int
    cut: bool


@dataclass(frozen=True)
class ListEntry:
    name: str
    kind: str
    size: int | None


@dataclass(frozen=True)
class Listing:
    entries: tuple[ListEntry, ...]
    more: bool


def stderr_facts(stderr: str) -> dict:
    try:
        data = json.loads(stderr)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def error_code(stderr: str) -> str:
    """The script's refusal code, or ``failed`` when stderr is not its JSON."""
    code = stderr_facts(stderr).get("error")
    return code if isinstance(code, str) else "failed"


def parse_wipe(stderr: str) -> int:
    """How many entries a wipe removed (0 when stderr is not its JSON)."""
    removed = stderr_facts(stderr).get("removed")
    return removed if isinstance(removed, int) else 0


def parse_read(stdout: str, stderr: str) -> ReadResult:
    facts = stderr_facts(stderr)
    size = facts.get("size")
    return ReadResult(stdout, size if isinstance(size, int) else len(stdout.encode()), bool(facts.get("cut")))


def _entry(raw: object) -> ListEntry | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
        return None
    size = raw.get("size")
    return ListEntry(raw["name"], str(raw.get("kind", "other")), size if isinstance(size, int) else None)


def parse_listing(stdout: str) -> Listing:
    try:
        data = json.loads(stdout)
    except ValueError:
        return Listing((), False)
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        return Listing((), False)
    entries = tuple(e for e in (_entry(raw) for raw in data["entries"]) if e is not None)
    return Listing(entries, bool(data.get("more")))
