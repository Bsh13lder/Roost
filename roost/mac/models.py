"""Plain values the Mac seam passes around (frozen; a changed copy is a new object)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Access = Literal["read", "read_write"]
ReadPolicy = Literal["ask_each", "ask_session"]
UndoKind = Literal["content", "create", "rename", "trash"]


@dataclass(frozen=True)
class Grant:
    """A folder the user shared. ``bot_id`` ``None`` means every bot. ``path`` is resolved and absolute."""

    id: str
    user_id: str
    bot_id: str | None
    path: str
    label: str
    access: Access
    read_policy: ReadPolicy
    is_vault: bool
    created_at: str
    revoked_at: str | None


@dataclass(frozen=True)
class GrantDraft:
    bot_id: str | None
    path: str
    label: str
    access: Access
    read_policy: ReadPolicy
    is_vault: bool


@dataclass(frozen=True)
class FileRef:
    grant_id: str
    bot_id: str
    path: str   # relative to the grant's folder; "" is the folder itself


@dataclass(frozen=True)
class FolderCheck:
    resolved: str
    is_vault: bool


@dataclass(frozen=True)
class Entry:
    name: str
    kind: Literal["file", "folder"]
    size: int
    mtime: int


@dataclass(frozen=True)
class ListResult:
    entries: tuple[Entry, ...]
    truncated: bool


@dataclass(frozen=True)
class FindHit:
    path: str
    size: int
    mtime: int
    snippets: tuple[str, ...]


@dataclass(frozen=True)
class FindResult:
    hits: tuple[FindHit, ...]
    truncated: bool


@dataclass(frozen=True)
class FileText:
    text: str
    sha256: str
    mtime: int
    size: int


@dataclass(frozen=True)
class FileStat:
    path: str
    sha256: str | None
    mtime: int
    size: int


@dataclass(frozen=True)
class WriteResult:
    sha256: str
    size: int
    backup_id: str | None


@dataclass(frozen=True)
class TrashResult:
    trash_name: str


@dataclass(frozen=True)
class UndoSpec:
    """What to undo: ``content`` (path, backup_id, expected_sha256), ``create`` (path, expected_sha256),
    ``rename`` (path, back_to, expected_sha256) or ``trash`` (trash_name, back_to)."""

    kind: UndoKind
    path: str | None = None
    backup_id: str | None = None
    back_to: str | None = None
    trash_name: str | None = None
    expected_sha256: str | None = None


@dataclass(frozen=True)
class FolderLine:
    """A folder as the bot's instructions list it."""

    label: str
    access: Access
    read_policy: ReadPolicy


@dataclass(frozen=True)
class FileMark:
    """What Roost last knew of a file it wrote: its hash, who wrote it, and whether that run was tainted."""

    sha256: str
    bot_id: str | None
    written_tainted: bool
    updated_at: str
