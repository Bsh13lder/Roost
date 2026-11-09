"""The keeper's signed Mac file API, reading side (Task 5; Review Focus b3, b4, b6)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from roost.constants import MAC_LIST_MAX_ENTRIES, MAC_READ_MAX_BYTES
from roost.keeper.macfs import ops_read
from roost.keeper.macfs.limits import OpsLimiter
from keeper_mac_helpers import BOT_A, BOT_B, GRANT_ID, MacRig, build_rig


@pytest.fixture
def rig(tmp_path: Path) -> MacRig:
    return build_rig(tmp_path)


FS_ROUTES = ("list", "find", "read", "stat")   # the write routes are covered in test_keeper_mac_write.py


def test_every_mac_route_needs_a_signature_and_a_strict_body(rig: MacRig) -> None:
    for route in ("/mac/check-folder", "/mac/pick-folder", *(f"/mac/fs/{r}" for r in FS_ROUTES)):
        assert rig.call("POST", route, {}, sign=False).status_code == 401, route
    assert rig.call("PUT", "/mac/grants", {"grants": []}, sign=False).status_code == 401
    # strict bodies: an unknown field such as root or argv is a 422, never ignored
    assert rig.fs("read", {"path": "a.md", "root": "/"}).status_code == 422
    assert rig.fs("list", {"path": "", "argv": ["/bin/sh"]}).status_code == 422
    assert rig.call("POST", "/mac/pick-folder", {"argv": ["/bin/sh"]}).status_code == 422
    assert rig.call("POST", "/mac/check-folder", {"path": str(rig.root), "x": 1}).status_code == 422
    assert rig.fs("read", {"path": "a.md"}, bot_id="not-a-uuid").status_code == 422
    body = rig.fs("read", {"path": "secret text", "root": "/"}).text
    assert "secret text" not in body          # a 422 never echoes the input


def test_put_grants_rechecks_every_root_and_holds_them_in_memory_only(rig: MacRig, tmp_path: Path) -> None:
    (rig.root / "a.md").write_text("hello")
    before = {p for p in rig.config.database_dir.rglob("*")}
    other = rig.home / "Docs"
    other.mkdir()
    ok = rig.push(rig.grant(), rig.grant(other, grant_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"))
    assert ok.status_code == 200 and ok.json() == {"count": 2}
    assert {p for p in rig.config.database_dir.rglob("*")} == before     # nothing was written
    bad = rig.push(rig.grant(), rig.grant(rig.home / "Library", grant_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc"))
    assert bad.status_code == 422
    assert bad.json()["detail"] == {"code": "bad_grant", "grant_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc"}
    assert rig.fs("read", {"path": "a.md"}).status_code == 200            # the old set stays
    assert rig.fs("read", {"path": "a.md"}, grant_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb").status_code == 404
    for root in (rig.home, tmp_path / "outside", "relative"):
        assert rig.push(rig.grant(Path(str(root)))).status_code == 422
    assert rig.push(rig.grant(), rig.grant()).status_code == 422         # a repeated id
    assert rig.push().status_code == 200                                  # an empty set revokes everything
    assert rig.fs("read", {"path": "a.md"}).json()["detail"] == {"code": "no_grant"}


def test_a_keeper_that_was_never_pushed_answers_grants_unset(tmp_path: Path) -> None:
    fresh = build_rig(tmp_path, push=False)
    response = fresh.fs("list", {"path": ""})
    assert response.status_code == 503 and response.json()["detail"] == {"code": "grants_unset"}


def test_check_folder_resolves_and_reports_a_vault(rig: MacRig) -> None:
    ok = rig.call("POST", "/mac/check-folder", {"path": str(rig.root)})
    assert ok.json() == {"resolved": str(rig.root), "is_vault": False}
    (rig.root / ".obsidian").mkdir()
    assert rig.call("POST", "/mac/check-folder", {"path": str(rig.root) + "/"}).json()["is_vault"] is True
    link = rig.home / "ViaLink"
    link.symlink_to(rig.root)
    assert rig.call("POST", "/mac/check-folder", {"path": str(link)}).json()["resolved"] == str(rig.root)
    for path, status, code in [
        (str(rig.home / "Library"), 403, "off_limits"), (str(rig.home), 403, "off_limits"),
        ("relative/dir", 400, "bad_path"), (str(rig.home / "Nope"), 404, "not_found"),
        (str(rig.root / ("x" * 5000)), 422, None),
    ]:
        response = rig.call("POST", "/mac/check-folder", {"path": path})
        assert response.status_code == status, path
        if code:
            assert response.json()["detail"] == {"code": code}
    (rig.home / "afile.md").write_text("x")
    assert rig.call("POST", "/mac/check-folder", {"path": str(rig.home / "afile.md")}).status_code == 400


def test_list_hides_dot_and_denied_entries_and_caps_at_500(rig: MacRig, tmp_path: Path) -> None:
    (rig.root / "a.md").write_text("12345")
    (rig.root / "sub").mkdir()
    (rig.root / ".hidden.md").write_text("x")
    (rig.root / ".obsidian").mkdir()
    (rig.root / "prod.env").write_text("SECRET=1")
    (rig.root / "id_rsa").write_text("k")
    (rig.root / "pipe").write_text("x")
    (rig.root / "link.md").symlink_to(rig.root / "a.md")
    (rig.root / "tab\tname\n.md").write_text("x")
    entries = rig.fs("list", {"path": ""}).json()
    names = {e["name"]: e for e in entries["entries"]}
    assert set(names) == {"a.md", "sub", "pipe", "tab name .md"} or set(names) == {"a.md", "sub", "pipe", "tabname.md"}
    assert names["a.md"]["kind"] == "file" and names["a.md"]["size"] == 5 and names["sub"]["kind"] == "folder"
    assert entries["truncated"] is False
    big = rig.root / "big"
    big.mkdir()
    for i in range(MAC_LIST_MAX_ENTRIES + 10):
        (big / f"f{i:04}.md").write_text("x")
    capped = rig.fs("list", {"path": "big"}).json()
    assert len(capped["entries"]) == MAC_LIST_MAX_ENTRIES and capped["truncated"] is True
    assert rig.fs("list", {"path": ".obsidian"}).status_code == 403
    assert rig.fs("list", {"path": "../x"}).status_code == 400
    assert rig.fs("list", {"path": "missing"}).status_code == 404


def test_read_returns_text_sha_mtime_and_refuses_binary_big_and_dataless(rig: MacRig, monkeypatch) -> None:
    data = "﻿hello é\n".encode()
    (rig.root / "a.md").write_bytes(data)
    got = rig.fs("read", {"path": "a.md"}).json()
    assert got["text"] == "hello é\n" and got["size"] == len(data) and isinstance(got["mtime"], int)
    assert got["sha256"] == hashlib.sha256(data).hexdigest()
    (rig.root / "bin.md").write_bytes(b"ab\0cd")
    (rig.root / "latin.md").write_bytes(b"caf\xe9")
    (rig.root / "big.md").write_bytes(b"x" * (MAC_READ_MAX_BYTES + 1))
    (rig.root / "ok.md").write_bytes(b"x" * MAC_READ_MAX_BYTES)
    assert rig.fs("read", {"path": "bin.md"}).json()["detail"] == {"code": "not_text"}
    assert rig.fs("read", {"path": "latin.md"}).json()["detail"] == {"code": "not_text"}
    assert rig.fs("read", {"path": "big.md"}).json()["detail"] == {"code": "too_big"}
    assert rig.fs("read", {"path": "ok.md"}).status_code == 200
    (rig.root / "icloud.md").write_text("x")
    monkeypatch.setattr(ops_read, "is_dataless", lambda st: True)
    dataless = rig.fs("read", {"path": "icloud.md"})
    assert dataless.status_code == 409 and dataless.json()["detail"] == {"code": "not_downloaded"}
    assert rig.fs("read", {"path": "x.env"}).status_code == 403
    assert rig.fs("read", {"path": "sub"}).status_code in (403, 404)


def test_stat_batches_up_to_50(rig: MacRig) -> None:
    (rig.root / "a.md").write_text("abc")
    files = rig.fs("stat", {"paths": ["a.md", "missing.md", "../x", "x.env"]}).json()["files"]
    assert [f["path"] for f in files] == ["a.md", "missing.md", "../x", "x.env"]
    assert files[0]["sha256"] == hashlib.sha256(b"abc").hexdigest() and files[0]["size"] == 3
    assert all(f["sha256"] is None for f in files[1:])
    assert rig.fs("stat", {"paths": [f"f{i}.md" for i in range(50)]}).status_code == 200
    assert rig.fs("stat", {"paths": [f"f{i}.md" for i in range(51)]}).status_code == 422


def test_ops_per_minute_cap_answers_429(rig: MacRig) -> None:
    rig.app.state.mac.limiter = OpsLimiter(limit=2)
    assert rig.fs("list", {"path": ""}).status_code == 200
    assert rig.fs("list", {"path": ""}).status_code == 200
    third = rig.fs("list", {"path": ""})
    assert third.status_code == 429 and third.json()["detail"] == {"code": "rate_limited"}
    assert rig.fs("list", {"path": ""}, bot_id=BOT_B).status_code == 200     # per bot


def test_the_audit_line_has_no_path_or_name(rig: MacRig) -> None:
    (rig.root / "Secret Plan.md").write_text("canary-text")
    rig.fs("read", {"path": "Secret Plan.md"})
    rig.fs("read", {"path": "../nope.md"})
    rig.fs("list", {"path": ""})
    rig.fs("find", {"name": "Secret", "path": ""})
    rig.fs("stat", {"paths": ["Secret Plan.md"]})
    rig.call("POST", "/mac/check-folder", {"path": str(rig.root)})
    lines = rig.audit_lines()
    assert {line["action"] for line in lines} >= {"mac_grants", "mac_read", "mac_list", "mac_find", "mac_stat", "mac_check"}
    allowed = {"action", "bot_id", "result", "ts", "grant_id", "size"}
    for line in lines:
        assert set(line) <= allowed
    raw = (rig.config.database_dir / "keeper-audit.log").read_text()
    for needle in ("Secret", "canary", "Notes", "nope", str(rig.home)):
        assert needle not in raw
    assert any(line["result"] == "bad_path" for line in lines)


def test_another_bots_grant_is_no_grant(rig: MacRig) -> None:
    (rig.root / "a.md").write_text("x")
    assert rig.push(rig.grant(bot_id=BOT_A)).status_code == 200
    assert rig.fs("read", {"path": "a.md"}, bot_id=BOT_A).status_code == 200
    other = rig.fs("read", {"path": "a.md"}, bot_id=BOT_B)
    assert other.status_code == 403 and other.json()["detail"] == {"code": "no_grant"}
    assert rig.fs("read", {"path": "a.md"}, grant_id="dddddddd-dddd-4ddd-8ddd-dddddddddddd").status_code == 403
    assert GRANT_ID  # the helper's id
