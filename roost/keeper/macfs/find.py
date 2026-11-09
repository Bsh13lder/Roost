"""Find by name and by words inside text files. The walk is our own ``openat`` walk (one
``O_NOFOLLOW`` open per folder, from the grant's fd), so a swapped link can't send it elsewhere.
It skips dot and denied entries, links and odd files; it stops at the entry, hit, byte and time
caps, and the moment the grant registry changes (a revoke)."""

from __future__ import annotations

import os
import re
import stat
import time
import unicodedata
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Callable

from roost.constants import (
    MAC_FIND_MAX_ENTRIES,
    MAC_FIND_MAX_HITS,
    MAC_FIND_MAX_SECONDS,
    MAC_FIND_SNIPPET_CHARS,
    MAC_FIND_SNIPPETS,
    MAC_FIND_TEXT_FILE_MAX_BYTES,
    MAC_FIND_TEXT_TOTAL_MAX_BYTES,
    MAC_PATH_MAX_PARTS,
)
from roost.keeper.macfs.deny import is_denied_name, is_denied_path
from roost.keeper.macfs.errors import MacFsError
from roost.keeper.macfs.grants import KeeperGrant
from roost.keeper.macfs.paths import check_resolved, is_dataless, open_dir, open_dir_at, open_name

_GLOB_CHARS = "*?["
_CONTEXT_CHARS = 60


@dataclass(frozen=True)
class FindQuery:
    name: str | None = None
    text: str | None = None
    path_parts: tuple[str, ...] = ()


@dataclass(frozen=True)
class FindResult:
    hits: tuple[dict[str, object], ...]
    truncated: bool


def _plain(name: str) -> bool:
    return not any(unicodedata.category(ch)[0] == "C" for ch in name)


def name_matches(folded: str, query: str) -> bool:
    wanted = query.casefold()
    if any(ch in wanted for ch in _GLOB_CHARS):
        return fnmatchcase(folded, wanted)
    return all(term in folded for term in wanted.split())


def snippets(text: str, query: str) -> list[str]:
    found: list[str] = []
    last_end = -1
    for match in re.finditer(re.escape(query), text, re.IGNORECASE):
        if match.start() < last_end:
            continue
        start = max(0, match.start() - _CONTEXT_CHARS)
        end = min(len(text), match.end() + _CONTEXT_CHARS)
        window = "".join(ch if unicodedata.category(ch)[0] != "C" else " " for ch in text[start:end])
        found.append(" ".join(window.split())[:MAC_FIND_SNIPPET_CHARS])
        last_end = end
        if len(found) >= MAC_FIND_SNIPPETS:
            break
    return found


class _Walk:
    def __init__(self, query: FindQuery, generation_now: Callable[[], int],
                 clock: Callable[[], float], on_file: Callable[[str], None] | None,
                 root: str = "", home: str | None = None) -> None:
        self.root, self.home = root, home
        self.query, self.generation_now, self.clock, self.on_file = query, generation_now, clock, on_file
        self.generation = generation_now()
        self.started = clock()
        self.entries = 0
        self.text_bytes = 0
        self.hits: list[dict[str, object]] = []
        self.truncated = False

    def denied(self, rel: tuple[str, ...], name: str) -> bool:
        """True when the full path (grant root + rel + name) hits the multi-part deny rules."""
        if self.home is None:
            return False
        return is_denied_path("/".join((self.root.rstrip("/"), *rel, name)), self.home)

    def stop(self) -> bool:
        if (
            self.generation_now() != self.generation
            or self.clock() - self.started > MAC_FIND_MAX_SECONDS
            or self.entries >= MAC_FIND_MAX_ENTRIES
        ):
            self.truncated = True
        return self.truncated

    def walk(self, dir_fd: int, rel: tuple[str, ...]) -> None:
        with os.scandir(dir_fd) as it:
            entries = sorted(((e.name, e) for e in it), key=lambda item: item[0])
            for name, entry in entries:
                if self.stop():
                    return
                self.entries += 1
                if name.startswith(".") or is_denied_name(name) or not _plain(name) or entry.is_symlink():
                    continue
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if stat.S_ISDIR(st.st_mode):
                    self.descend(dir_fd, rel, name)
                elif stat.S_ISREG(st.st_mode) and st.st_nlink == 1:
                    self.file(dir_fd, rel, name, st)

    def descend(self, dir_fd: int, rel: tuple[str, ...], name: str) -> None:
        if len(rel) + 1 >= MAC_PATH_MAX_PARTS or self.denied(rel, name):
            return
        try:
            child = open_dir_at(dir_fd, name)
        except MacFsError:
            return
        try:
            try:
                check_resolved(child, self.home)
            except MacFsError:
                return
            self.walk(child, (*rel, name))
        finally:
            os.close(child)

    def file(self, dir_fd: int, rel: tuple[str, ...], name: str, st: os.stat_result) -> None:
        if self.denied(rel, name):
            return
        path = "/".join((*rel, name))
        if self.on_file is not None:
            self.on_file(path)
        if self.query.name is not None and not name_matches(name.casefold(), self.query.name):
            return
        snippets: list[str] = []
        if self.query.text is not None:
            found = self.search_text(dir_fd, name, st)
            if not found:
                return
            snippets = found
        if len(self.hits) >= MAC_FIND_MAX_HITS:
            self.truncated = True
            return
        self.hits.append({"path": path, "size": st.st_size, "mtime": int(st.st_mtime), "snippets": snippets})

    def search_text(self, dir_fd: int, name: str, st: os.stat_result) -> list[str]:
        if st.st_size > MAC_FIND_TEXT_FILE_MAX_BYTES or is_dataless(st):
            return []
        if self.text_bytes + st.st_size > MAC_FIND_TEXT_TOTAL_MAX_BYTES:
            self.truncated = True
            return []
        try:
            fd = open_name(dir_fd, name, os.O_RDONLY)
        except MacFsError:
            return []
        try:
            data = os.read(fd, MAC_FIND_TEXT_FILE_MAX_BYTES + 1)
        finally:
            os.close(fd)
        self.text_bytes += len(data)
        if len(data) > MAC_FIND_TEXT_FILE_MAX_BYTES or b"\0" in data:
            return []
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return []
        return snippets(text, self.query.text or "")


def find(
    grant: KeeperGrant, root_fd: int, query: FindQuery, generation_now: Callable[[], int], *,
    home: str | None = None, clock: Callable[[], float] = time.monotonic,
    on_file: Callable[[str], None] | None = None,
) -> FindResult:
    """Walk below ``query.path_parts``; ``generation_now`` is the registry's generation, read per entry."""
    start_fd = open_dir(root_fd, query.path_parts, home)
    walk = _Walk(query, generation_now, clock, on_file, grant.root, home)
    try:
        walk.walk(start_fd, query.path_parts)
    finally:
        os.close(start_fd)
    return FindResult(tuple(walk.hits), walk.truncated)
