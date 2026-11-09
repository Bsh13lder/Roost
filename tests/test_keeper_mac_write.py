"""The keeper writes Mac files (Task 6; Review Focus b2, b4, b5): atomic, backed up, trashed, undone."""

from __future__ import annotations

import asyncio
import hashlib
import os
import stat
import subprocess
from pathlib import Path

import pytest

from keeper_mac_helpers import BOT_A, MacRig, build_rig
from roost.constants import MAC_READ_MAX_BYTES, MAC_TMP_INFIX
from roost.keeper.macfs import ops_write

WRITE_ROUTES = ("create", "write", "rename", "trash", "undo")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def rig(tmp_path: Path) -> MacRig:
    return build_rig(tmp_path)


def _code(response) -> str:
    return response.json()["detail"]["code"]


def test_write_routes_need_a_signature_and_a_strict_body(rig: MacRig) -> None:
    for route in WRITE_ROUTES:
        assert rig.call("POST", f"/mac/fs/{route}", {}, sign=False).status_code == 401
    assert rig.fs("create", {"path": "a.md", "text": "x", "mode": "w"}).status_code == 422
    assert rig.fs("write", {"path": "a.md", "text": "x"}).status_code == 422          # no expected_sha256
    assert rig.fs("write", {"path": "a.md", "text": "x", "expected_sha256": "nothex"}).status_code == 422
    assert rig.fs("undo", {"kind": "format", "path": "a.md"}).status_code == 422
    assert rig.fs("undo", {"kind": "trash", "trash_name": "x", "back_to": "a.md", "root": "/"}).status_code == 422


def test_create_refuses_existing_names_bad_extensions_and_dot_folders(rig: MacRig) -> None:
    made = rig.fs("create", {"path": "new.md", "text": "hello"})
    assert made.status_code == 200 and made.json() == {"sha256": sha("hello"), "size": 5}
    assert (rig.root / "new.md").read_text() == "hello"
    assert (rig.root / "new.md").stat().st_nlink == 1
    assert _code(rig.fs("create", {"path": "new.md", "text": "again"})) == "exists"
    assert (rig.root / "new.md").read_text() == "hello"
    (rig.root / "gone.md").symlink_to(rig.root / "nowhere")
    assert _code(rig.fs("create", {"path": "gone.md", "text": "x"})) == "exists"      # never through a link
    assert not (rig.root / "nowhere").exists()
    assert _code(rig.fs("create", {"path": "doc.pdf", "text": "x"})) == "bad_ext"
    assert _code(rig.fs("create", {"path": "noext", "text": "x"})) == "bad_ext"
    assert rig.fs("create", {"path": "UP.MD", "text": "x"}).status_code == 200
    assert rig.fs("create", {"path": "list.csv", "text": "a,b"}).status_code == 200
    assert _code(rig.fs("create", {"path": ".hid/x.md", "text": "x"})) == "off_limits"
    assert _code(rig.fs("create", {"path": ".hidden.md", "text": "x"})) == "off_limits"
    assert _code(rig.fs("create", {"path": "prod.env", "text": "x"})) == "off_limits"
    assert _code(rig.fs("create", {"path": "../x.md", "text": "x"})) == "bad_path"
    assert _code(rig.fs("create", {"path": "nodir/x.md", "text": "x"})) == "not_found"
    (rig.root / "real").mkdir()
    (rig.root / "link").symlink_to(rig.root / "real")
    assert _code(rig.fs("create", {"path": "link/x.md", "text": "x"})) == "off_limits"
    assert not (rig.root / "real" / "x.md").exists()
    assert _code(rig.fs("create", {"path": "big.md", "text": "é" * MAC_READ_MAX_BYTES})) == "too_big"
    assert not (rig.root / "big.md").exists()
    assert not [p for p in rig.root.iterdir() if MAC_TMP_INFIX in p.name]


def test_write_replaces_only_on_the_expected_hash_else_409_with_the_current_hash(rig: MacRig) -> None:
    (rig.root / "a.md").write_text("one")
    stale = rig.fs("write", {"path": "a.md", "text": "two", "expected_sha256": sha("zero")})
    assert stale.status_code == 409 and stale.json()["detail"] == {"code": "changed", "current_sha256": sha("one")}
    assert (rig.root / "a.md").read_text() == "one"
    done = rig.fs("write", {"path": "a.md", "text": "two", "expected_sha256": sha("one")}).json()
    assert done["sha256"] == sha("two") and done["size"] == 3 and done["backup_id"]
    assert (rig.root / "a.md").read_text() == "two"
    assert _code(rig.fs("write", {"path": "missing.md", "text": "x", "expected_sha256": sha("x")})) == "not_found"
    assert _code(rig.fs("write", {"path": "a.pdf", "text": "x", "expected_sha256": sha("x")})) == "bad_ext"
    assert _code(rig.fs("write", {"path": ".a.md", "text": "x", "expected_sha256": sha("x")})) == "off_limits"
    big = "é" * MAC_READ_MAX_BYTES
    assert _code(rig.fs("write", {"path": "a.md", "text": big, "expected_sha256": sha("two")})) == "too_big"
    (rig.root / "hard.md").write_text("x")
    os.link(rig.root / "hard.md", rig.root / "hard2.md")
    assert _code(rig.fs("write", {"path": "hard.md", "text": "y", "expected_sha256": sha("x")})) == "off_limits"


def test_a_write_is_atomic_and_keeps_the_old_mode(rig: MacRig, monkeypatch: pytest.MonkeyPatch) -> None:
    target = rig.root / "a.md"
    target.write_text("old bytes")
    target.chmod(0o640)
    expected = sha("old bytes")

    def crash(*args, **kwargs):
        raise OSError("crash between fsync and rename")

    with monkeypatch.context() as patch:
        patch.setattr(ops_write.os, "rename", crash)
        failed = rig.fs("write", {"path": "a.md", "text": "new bytes", "expected_sha256": expected})
    assert failed.status_code == 500
    assert target.read_text() == "old bytes"
    assert sorted(p.name for p in rig.root.iterdir()) == ["a.md"]          # no temp left behind
    ok = rig.fs("write", {"path": "a.md", "text": "new bytes", "expected_sha256": expected})
    assert ok.status_code == 200 and target.read_text() == "new bytes"
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert sorted(p.name for p in rig.root.iterdir()) == ["a.md"]


def test_a_file_changed_during_the_write_is_not_overwritten(rig: MacRig, monkeypatch: pytest.MonkeyPatch) -> None:
    target = rig.root / "a.md"
    target.write_text("old bytes")
    real_fchmod = os.fchmod

    def intruder(fd, mode):
        target.write_text("someone else edited this")        # between our read and our rename
        real_fchmod(fd, mode)

    monkeypatch.setattr(ops_write.os, "fchmod", intruder)
    response = rig.fs("write", {"path": "a.md", "text": "mine", "expected_sha256": sha("old bytes")})
    assert response.status_code == 409 and _code(response) == "changed"
    assert target.read_text() == "someone else edited this"
    assert sorted(p.name for p in rig.root.iterdir()) == ["a.md"]


def test_rename_stays_inside_the_grant_and_refuses_an_existing_target(rig: MacRig) -> None:
    (rig.root / "a.md").write_text("one")
    (rig.root / "taken.md").write_text("other")
    (rig.root / "sub").mkdir()
    base = {"path": "a.md", "expected_sha256": sha("one")}
    assert _code(rig.fs("rename", {**base, "new_path": "taken.md"})) == "exists"
    assert _code(rig.fs("rename", {**base, "new_path": "../out.md"})) == "bad_path"
    assert _code(rig.fs("rename", {**base, "new_path": "/tmp/out.md"})) == "bad_path"
    assert _code(rig.fs("rename", {**base, "new_path": "b.pdf"})) == "bad_ext"
    assert _code(rig.fs("rename", {**base, "new_path": ".b.md"})) == "off_limits"
    assert _code(rig.fs("rename", {**base, "new_path": "a.md"})) == "exists"
    assert _code(rig.fs("rename", {"path": "a.md", "new_path": "b.md", "expected_sha256": sha("x")})) == "changed"
    (rig.root / "link").symlink_to(rig.root / "sub")
    assert _code(rig.fs("rename", {**base, "new_path": "link/b.md"})) == "off_limits"
    assert (rig.root / "a.md").read_text() == "one"
    moved = rig.fs("rename", {**base, "new_path": "sub/b.md"})
    assert moved.status_code == 200 and moved.json() == {"sha256": sha("one")}
    assert not (rig.root / "a.md").exists() and (rig.root / "sub" / "b.md").read_text() == "one"
    assert (rig.root / "taken.md").read_text() == "other"


def test_trash_moves_into_the_vault_or_roost_trash_and_deletes_nothing(rig: MacRig) -> None:
    (rig.root / "a.md").write_text("one")
    assert _code(rig.fs("trash", {"path": "a.md", "expected_sha256": sha("zero")})) == "changed"
    trashed = rig.fs("trash", {"path": "a.md", "expected_sha256": sha("one")}).json()
    folder = rig.root / ".roost-trash"
    assert [p.name for p in folder.iterdir()] == [trashed["trash_name"]]
    assert trashed["trash_name"].endswith("Z-a.md") and (folder / trashed["trash_name"]).read_text() == "one"
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert not (rig.root / "a.md").exists()
    (rig.root / ".obsidian").mkdir()
    (rig.root / "b.md").write_text("two")
    vault = rig.fs("trash", {"path": "b.md", "expected_sha256": sha("two")}).json()
    assert (rig.root / ".trash" / vault["trash_name"]).read_text() == "two"
    assert _code(rig.fs("trash", {"path": ".roost-trash/x.md", "expected_sha256": sha("one")})) == "off_limits"
    assert _code(rig.fs("trash", {"path": "gone.md", "expected_sha256": sha("one")})) == "not_found"


def test_undo_restores_content_create_rename_and_trash_on_the_expected_hash(rig: MacRig) -> None:
    (rig.root / "a.md").write_text("one")
    done = rig.fs("write", {"path": "a.md", "text": "two", "expected_sha256": sha("one")}).json()
    content = {"kind": "content", "path": "a.md", "backup_id": done["backup_id"]}
    assert _code(rig.fs("undo", {**content, "expected_sha256": sha("someone else")})) == "changed"
    assert (rig.root / "a.md").read_text() == "two"
    assert rig.fs("undo", {**content, "expected_sha256": sha("two")}).json() == {"sha256": sha("one")}
    assert (rig.root / "a.md").read_text() == "one"
    assert rig.fs("create", {"path": "n.md", "text": "new"}).status_code == 200
    undo_create = rig.fs("undo", {"kind": "create", "path": "n.md", "expected_sha256": sha("new")})
    assert undo_create.status_code == 200 and undo_create.json() == {"sha256": None}
    assert not (rig.root / "n.md").exists() and len(list((rig.root / ".roost-trash").iterdir())) == 1
    rig.fs("rename", {"path": "a.md", "new_path": "b.md", "expected_sha256": sha("one")})
    back = {"kind": "rename", "path": "b.md", "back_to": "a.md", "expected_sha256": sha("one")}
    assert rig.fs("undo", back).status_code == 200
    assert (rig.root / "a.md").read_text() == "one" and not (rig.root / "b.md").exists()
    name = rig.fs("trash", {"path": "a.md", "expected_sha256": sha("one")}).json()["trash_name"]
    (rig.root / "a.md").write_text("in the way")
    assert _code(rig.fs("undo", {"kind": "trash", "trash_name": name, "back_to": "a.md"})) == "exists"
    (rig.root / "a.md").unlink()
    assert rig.fs("undo", {"kind": "trash", "trash_name": name, "back_to": "a.md"}).json() == {"sha256": sha("one")}
    assert (rig.root / "a.md").read_text() == "one"
    for crafted in ("../a.md", "x/y.md", "", "..", ".roost-trash/x", "/etc/passwd"):
        status = rig.fs("undo", {"kind": "trash", "trash_name": crafted, "back_to": "z.md"}).status_code
        assert status in (400, 403, 422), crafted
    assert _code(rig.fs("undo", {"kind": "trash", "trash_name": "20260101T000000000000Z-x.md", "back_to": "z.md"})) == "not_found"


def test_read_only_grant_refuses_every_write(tmp_path: Path) -> None:
    rig = build_rig(tmp_path, access="read")
    (rig.root / "a.md").write_text("one")
    bodies = {
        "create": {"path": "n.md", "text": "x"},
        "write": {"path": "a.md", "text": "x", "expected_sha256": sha("one")},
        "rename": {"path": "a.md", "new_path": "b.md", "expected_sha256": sha("one")},
        "trash": {"path": "a.md", "expected_sha256": sha("one")},
    }
    for route, body in bodies.items():
        response = rig.fs(route, body)
        assert response.status_code == 403 and _code(response) == "read_only", route
    undos = [
        {"kind": "content", "path": "a.md", "backup_id": "20261001T000000000000Z-abcdef01", "expected_sha256": sha("one")},
        {"kind": "create", "path": "a.md", "expected_sha256": sha("one")},
        {"kind": "rename", "path": "a.md", "back_to": "b.md", "expected_sha256": sha("one")},
        {"kind": "trash", "trash_name": "x.md", "back_to": "a.md"},
    ]
    for body in undos:
        assert _code(rig.fs("undo", body)) == "read_only"
    assert [p.name for p in rig.root.iterdir()] == ["a.md"] and (rig.root / "a.md").read_text() == "one"
    assert rig.fs("read", {"path": "a.md"}).status_code == 200


def test_no_subprocess_is_started_by_any_file_op(rig: MacRig, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("a file op started a process")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    (rig.root / "a.md").write_text("one")
    steps = [
        ("create", {"path": "n.md", "text": "x"}), ("list", {"path": ""}), ("find", {"name": "a"}),
        ("find", {"text": "one"}), ("read", {"path": "a.md"}), ("stat", {"paths": ["a.md"]}),
        ("write", {"path": "a.md", "text": "two", "expected_sha256": sha("one")}),
        ("rename", {"path": "a.md", "new_path": "b.md", "expected_sha256": sha("two")}),
        ("trash", {"path": "b.md", "expected_sha256": sha("two")}),
    ]
    for route, body in steps:
        assert rig.fs(route, body, bot_id=BOT_A).status_code == 200, route


def test_the_write_audit_lines_carry_ids_and_codes_only(rig: MacRig) -> None:
    (rig.root / "Secret Name.md").write_text("canary")
    rig.fs("write", {"path": "Secret Name.md", "text": "canary two", "expected_sha256": sha("canary")})
    rig.fs("create", {"path": "Secret Name.md", "text": "x"})
    lines = rig.audit_lines()
    assert {"mac_write", "mac_create"} <= {line["action"] for line in lines}
    raw = (rig.config.database_dir / "keeper-audit.log").read_text()
    assert "Secret" not in raw and "canary" not in raw
    for line in lines:
        assert set(line) <= {"action", "bot_id", "result", "ts", "grant_id", "size"}


def test_rename_never_replaces_a_file_that_appears_after_the_check(rig: MacRig, monkeypatch: pytest.MonkeyPatch) -> None:
    (rig.root / "a.md").write_text("one")
    real_absent = ops_write._absent

    def racing(dir_fd, name):
        real_absent(dir_fd, name)
        (rig.root / name).write_text("intruder")            # lands after the check, before the move

    monkeypatch.setattr(ops_write, "_absent", racing)
    response = rig.fs("rename", {"path": "a.md", "new_path": "b.md", "expected_sha256": sha("one")})
    assert response.status_code == 409 and _code(response) == "exists"
    assert (rig.root / "b.md").read_text() == "intruder" and (rig.root / "a.md").read_text() == "one"


def test_untrash_never_replaces_a_file_that_appears_after_the_check(rig: MacRig, monkeypatch: pytest.MonkeyPatch) -> None:
    (rig.root / "a.md").write_text("one")
    name = rig.fs("trash", {"path": "a.md", "expected_sha256": sha("one")}).json()["trash_name"]
    real_absent = ops_write._absent

    def racing(dir_fd, n):
        real_absent(dir_fd, n)
        (rig.root / n).write_text("intruder")

    monkeypatch.setattr(ops_write, "_absent", racing)
    response = rig.fs("undo", {"kind": "trash", "trash_name": name, "back_to": "a.md"})
    assert response.status_code == 409 and _code(response) == "exists"
    assert (rig.root / "a.md").read_text() == "intruder"
    assert (rig.root / ".roost-trash" / name).read_text() == "one"
