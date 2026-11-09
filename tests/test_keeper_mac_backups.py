"""Backups before every change (Task 6; Review Focus b2, b4)."""

from __future__ import annotations

import hashlib
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from keeper_mac_helpers import GRANT_ID, MacRig, build_rig
from roost.constants import MAC_BACKUPS_KEEP
from roost.keeper.macfs.backups import Backups
from roost.keeper.macfs.errors import MacFsError

KEY = b"k" * 32


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_every_change_saves_a_backup_first_outside_the_grant(tmp_path: Path) -> None:
    rig: MacRig = build_rig(tmp_path)
    (rig.root / "a.md").write_text("version one")
    old_sha = hashlib.sha256(b"version one").hexdigest()
    written = rig.fs("write", {"path": "a.md", "text": "version two", "expected_sha256": old_sha}).json()
    backups = rig.config.mac_backups_dir
    assert rig.root not in backups.parents and backups not in rig.root.parents
    files = [p for p in backups.rglob("*") if p.is_file()]
    assert len(files) == 1 and files[0].name == written["backup_id"] and files[0].read_bytes() == b"version one"
    assert _mode(files[0]) == 0o600
    for folder in (backups, backups / GRANT_ID, files[0].parent):
        assert _mode(folder) == 0o700
    assert "a.md" not in str(files[0])          # the folder name is an HMAC of the path
    rig.fs("rename", {"path": "a.md", "new_path": "b.md", "expected_sha256": hashlib.sha256(b"version two").hexdigest()})
    rig.fs("trash", {"path": "b.md", "expected_sha256": hashlib.sha256(b"version two").hexdigest()})
    assert len([p for p in backups.rglob("*") if p.is_file()]) == 3       # write, rename and trash each saved one


def test_backups_keep_20_and_drop_after_30_days(tmp_path: Path) -> None:
    clock = _Clock()
    backups = Backups(tmp_path / "b", KEY, now=clock)
    ids = []
    for i in range(MAC_BACKUPS_KEEP + 5):
        clock.now += timedelta(seconds=1)
        ids.append(backups.save(GRANT_ID, "a.md", f"v{i}".encode()))
    backups.prune(GRANT_ID, "a.md")
    folder = next((tmp_path / "b" / GRANT_ID).iterdir())
    assert sorted(p.name for p in folder.iterdir()) == sorted(ids[-MAC_BACKUPS_KEEP:])
    assert backups.load(GRANT_ID, "a.md", ids[-1]) == f"v{MAC_BACKUPS_KEEP + 4}".encode()
    clock.now += timedelta(days=31)
    newest = backups.save(GRANT_ID, "a.md", b"fresh")
    backups.prune(GRANT_ID, "a.md")
    assert [p.name for p in folder.iterdir()] == [newest]
    other = backups.save(GRANT_ID, "other.md", b"x")          # another file has its own folder
    assert backups.load(GRANT_ID, "other.md", other) == b"x"


@pytest.mark.parametrize("bad", ["", "../../etc/passwd", "x", "20261001T000000000000Z-zzzzzzzz",
                                 "20261001T000000000000Z-abcdef01/../x", "20261001T000000000000Z-abcdef01\0"])
def test_a_crafted_backup_id_is_refused(tmp_path: Path, bad: str) -> None:
    backups = Backups(tmp_path / "b", KEY)
    with pytest.raises(MacFsError) as err:
        backups.load(GRANT_ID, "a.md", bad)
    assert err.value.code == "bad_path"
    with pytest.raises(MacFsError) as missing:
        backups.load(GRANT_ID, "a.md", "20261001T000000000000Z-abcdef01")
    assert missing.value.code == "not_found"
    with pytest.raises(MacFsError):
        backups.load("../..", "a.md", "20261001T000000000000Z-abcdef01")


def test_a_crafted_backup_id_is_a_422_at_the_route(tmp_path: Path) -> None:
    rig = build_rig(tmp_path)
    (rig.root / "a.md").write_text("x")
    body = {"kind": "content", "path": "a.md", "backup_id": "../../etc/passwd", "expected_sha256": "0" * 64}
    assert rig.fs("undo", body).status_code == 422
    assert os.path.exists(rig.root / "a.md")
