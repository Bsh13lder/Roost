"""Backups of Mac files, kept outside every grant (``<mac_backups_dir>/<grant_id>/<hmac of the path>/``).

A copy of the old bytes is saved before every change (write, rename, trash, undo of content).
Folders are 0700, files 0600. The folder name is an HMAC of the relative path, so a listing of
the backups folder shows no file names. These are Roost's own files, so pruning them is the
one place the keeper deletes anything: the user's files are never deleted."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from roost.constants import MAC_BACKUPS_KEEP, MAC_BACKUPS_MAX_DAYS
from roost.keeper.macfs.errors import MacFsError

BACKUP_ID_PATTERN = r"^\d{8}T\d{12}Z-[0-9a-f]{8}$"
_ID_RE = re.compile(BACKUP_ID_PATTERN)
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_STAMP = "%Y%m%dT%H%M%S%f"
_STAMP_LEN = 21
_FOLDER_HEX_CHARS = 32


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Backups:
    def __init__(self, base: Path, key: bytes, now: Callable[[], datetime] = _utc_now) -> None:
        self._base = base
        self._key = key
        self._now = now

    def _folder(self, grant_id: str, rel_path: str) -> Path:
        if not _UUID_RE.match(grant_id):
            raise MacFsError("bad_path")
        digest = hmac.new(self._key, unicodedata.normalize("NFC", rel_path).encode(), hashlib.sha256).hexdigest()
        return self._base / grant_id / digest[:_FOLDER_HEX_CHARS]

    def _make_private(self, folder: Path) -> None:
        self._base.mkdir(parents=True, exist_ok=True)
        for level in (self._base, folder.parent, folder):
            try:
                os.mkdir(level, 0o700)
            except FileExistsError:
                pass
            os.chmod(level, 0o700)

    def save(self, grant_id: str, rel_path: str, data: bytes) -> str:
        folder = self._folder(grant_id, rel_path)
        self._make_private(folder)
        backup_id = f"{self._now().astimezone(timezone.utc).strftime(_STAMP)}Z-{secrets.token_hex(4)}"
        fd = os.open(folder / backup_id, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            raise
        return backup_id

    def load(self, grant_id: str, rel_path: str, backup_id: str) -> bytes:
        if not _ID_RE.match(backup_id):
            raise MacFsError("bad_path")
        path = self._folder(grant_id, rel_path) / backup_id
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            raise MacFsError("not_found") from None
        with os.fdopen(fd, "rb") as handle:
            return handle.read()

    def prune(self, grant_id: str, rel_path: str) -> None:
        """Keep the newest ``MAC_BACKUPS_KEEP`` and drop anything older than ``MAC_BACKUPS_MAX_DAYS``."""
        folder = self._folder(grant_id, rel_path)
        try:
            ids = sorted(name for name in os.listdir(folder) if _ID_RE.match(name))
        except FileNotFoundError:
            return
        cutoff = self._now().astimezone(timezone.utc) - timedelta(days=MAC_BACKUPS_MAX_DAYS)
        keep = set(ids[-MAC_BACKUPS_KEEP:])
        for name in ids:
            stamp = datetime.strptime(name[:_STAMP_LEN], _STAMP).replace(tzinfo=timezone.utc)
            if name not in keep or stamp < cutoff:
                try:
                    os.unlink(folder / name)
                except FileNotFoundError:
                    pass
