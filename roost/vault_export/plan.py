"""What to do with one file, pure: the rule that the export never overwrites what it did not write.

``written`` is the hash Roost wrote last time (the manifest), ``on_disk`` the file's hash now (``None``: no
file there). A missing file is created; a file that already says the same is left alone; a file that is
still exactly what Roost wrote is overwritten (with that hash as the keeper's expected hash); anything else
(changed in Obsidian, or never Roost's) keeps its text and gets a ``<name>.conflict.md`` copy instead."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

Action = Literal["create", "same", "write", "conflict"]
CONFLICT_SUFFIX = ".conflict.md"
_EXT = ".md"


@dataclass(frozen=True)
class Decision:
    action: Action
    sha256: str            # the text's hash: what the manifest records once it is written
    expected: str | None   # for "write": the disk's hash the keeper must still find


def text_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def decide(text: str, written: str | None, on_disk: str | None) -> Decision:
    sha = text_sha(text)
    if on_disk is None:
        return Decision("create", sha, None)
    if on_disk == sha:
        return Decision("same", sha, None)
    if written is not None and on_disk == written:
        return Decision("write", sha, on_disk)
    return Decision("conflict", sha, None)


def conflict_path(path: str) -> str:
    """``Roost/Projects/X/Tasks/Dig.md`` -> ``Roost/Projects/X/Tasks/Dig.conflict.md``."""
    stem = path[:-len(_EXT)] if path.endswith(_EXT) else path
    return f"{stem}{CONFLICT_SUFFIX}"
