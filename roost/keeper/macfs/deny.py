"""The deny list: pure rules, no I/O, importable by the gateway and the fake.

A path is judged lexically here. The keeper judges the same rule again on the path the
kernel resolved (``paths.check_resolved``), so a trick that fools one pass meets the other.
"""

from __future__ import annotations

import posixpath
from fnmatch import fnmatchcase

from roost.constants import (
    MAC_DENY_HOME_DIRS,
    MAC_DENY_HOME_PATHS,
    MAC_DENY_NAME_GLOBS,
)
from roost.keeper.macfs.errors import MacFsError

_DENY_GLOBS_FOLDED = tuple(glob.casefold() for glob in MAC_DENY_NAME_GLOBS)
_DENY_HOME_DIRS_FOLDED = frozenset(name.casefold() for name in MAC_DENY_HOME_DIRS)
_DENY_HOME_PATHS_FOLDED = tuple(tuple(p.casefold().split("/")) for p in MAC_DENY_HOME_PATHS)


def is_denied_name(name: str) -> bool:
    """True when ``name`` matches a secret-looking pattern (``*.env``, ``id_*``, ``*.pem`` ...), case-folded."""
    folded = name.casefold()
    return any(fnmatchcase(folded, glob) for glob in _DENY_GLOBS_FOLDED)


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _home_parts(path: str, home: str) -> tuple[str, ...] | None:
    """The parts of ``path`` below ``home``, or ``None`` when it is not inside it."""
    if not _under(path, home):
        return None
    rel = path[len(home):].strip("/")
    return tuple(rel.split("/")) if rel else ()


def _denied_inside_home(parts: tuple[str, ...]) -> bool:
    if not parts:
        return True  # the home folder itself
    folded = tuple(part.casefold() for part in parts)
    if folded[0].startswith(".") or folded[0] in _DENY_HOME_DIRS_FOLDED:
        return True
    if any(folded[: len(denied)] == denied for denied in _DENY_HOME_PATHS_FOLDED):
        return True
    return any(is_denied_name(part) for part in parts)


def is_denied_path(abs_path: str, home: str) -> bool:
    """True when ``abs_path`` may never be granted or touched.

    Denied: anything not absolute or outside ``home``; ``home`` itself; the system roots and
    everything outside it; every top-level dot entry of ``home``; ``~/Library``, ``~/Roost``
    and the other denied home folders; the denied home paths; any part with a denied name."""
    if not abs_path.startswith("/") or "\0" in abs_path:
        return True
    path = posixpath.normpath(abs_path)
    if path.startswith("//"):
        path = "/" + path.lstrip("/")
    home = posixpath.normpath(home)
    parts = _home_parts(path, home)
    if parts is None:
        # Outside the home folder. That covers every MAC_DENY_ROOTS entry (/System, /etc, /private ...).
        # Inside the home, the system roots are not consulted: a test home may live under /private/var.
        return True
    return _denied_inside_home(parts)


def check_grant_root(resolved: str, home: str) -> None:
    """Refuse a folder that may not be granted (``off_limits``): the home itself, anything denied."""
    if is_denied_path(resolved, home):
        raise MacFsError("off_limits")
