"""File and folder names for the export, pure.

A name keeps the title's words but loses what a file name or a wikilink cannot hold (``/ \\ : * ? " < > |``,
``# ^ [ ]``, control characters), a leading dot or dash, and anything past ``VAULT_EXPORT_NAME_MAX_CHARS``.
A name the keeper's deny list would refuse (``id_rsa``, ``x.env``…) gets a ``Roost `` prefix. Two records
with the same name in one folder get `` (2)``, `` (3)``… in a fixed order, so a name never flips between
exports."""

from __future__ import annotations

import re
from typing import Iterable

from roost.constants import VAULT_EXPORT_NAME_MAX_CHARS
from roost.keeper.macfs.deny import is_denied_name

_UNSAFE = re.compile(r'[\\/:*?"<>|#^\[\]\x00-\x1f\x7f]+')
_SPACES = re.compile(r"\s+")
_UNTITLED = "Untitled"
_SAFE_PREFIX = "Roost "
_EXT = ".md"


def file_name(title: str) -> str:
    """A safe file or folder name (no extension) for ``title``; never empty."""
    cleaned = _SPACES.sub(" ", _UNSAFE.sub(" ", title)).strip().lstrip(".-").strip()
    cut = cleaned[:VAULT_EXPORT_NAME_MAX_CHARS].rstrip(" .") or _UNTITLED
    if is_denied_name(cut) or is_denied_name(cut + _EXT):
        cut = f"{_SAFE_PREFIX}{cut}"
    return cut


def unique_names(items: Iterable[tuple[str, str]]) -> dict[str, str]:
    """``(id, title)`` pairs, in a stable order, to ``{id: name}`` with no two names alike (case-blind)."""
    taken: set[str] = set()
    names: dict[str, str] = {}
    for item_id, title in items:
        base = file_name(title)
        name, n = base, 1
        while name.casefold() in taken:
            n += 1
            name = f"{base} ({n})"
        taken.add(name.casefold())
        names[item_id] = name
    return names
