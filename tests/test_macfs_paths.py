"""Symlink-free paths (Task 4; Review Focus b1, b2): every tree is built under tmp_path."""

from __future__ import annotations

import errno
import os
import stat
import unicodedata
from pathlib import Path

import pytest

from roost.keeper.macfs import paths
from roost.keeper.macfs.paths import MacFsError, open_dir, open_file, split_rel


@pytest.fixture
def tree(tmp_path: Path):
    home = tmp_path.resolve() / "home"
    root = home / "Notes"
    root.mkdir(parents=True)
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        yield home, root, root_fd
    finally:
        os.close(root_fd)


def _code(call) -> str:
    with pytest.raises(MacFsError) as err:
        call()
    return err.value.code


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("../x", "bad_path"), ("a/../b", "bad_path"), ("..", "bad_path"), (".", "bad_path"),
        ("/abs/path", "bad_path"), ("~/x", "bad_path"), ("~", "bad_path"), ("a\0b", "bad_path"),
        ("a//b", "bad_path"), ("a/", "bad_path"), ("a/./b", "bad_path"),
        ("/".join(["d"] * 33), "bad_path"),
        (".hidden", "off_limits"), ("a/.hidden/b", "off_limits"), ("x.env", "off_limits"), ("a/id_rsa", "off_limits"),
    ],
)
def test_relative_paths_refuse_dotdot_nul_absolute_tilde_empty_and_too_deep(path: str, code: str) -> None:
    assert _code(lambda: split_rel(path)) == code


def test_split_rel_keeps_good_paths() -> None:
    assert split_rel("") == ()
    assert split_rel("a/b/c.md") == ("a", "b", "c.md")
    assert split_rel("/".join(["d"] * 32)) == ("d",) * 32


def test_nfc_lookalikes_resolve_to_one_name(tree) -> None:
    _home, root, root_fd = tree
    nfc, nfd = unicodedata.normalize("NFC", "café.md"), unicodedata.normalize("NFD", "café.md")
    assert nfc != nfd
    (root / nfc).write_text("one file")
    assert split_rel(nfc) == split_rel(nfd) == (nfc,)
    for spelling in (nfc, nfd):
        fd = open_file(root_fd, split_rel(spelling), os.O_RDONLY)
        assert os.read(fd, 100) == b"one file"
        os.close(fd)


def test_a_symlink_anywhere_in_the_path_is_refused(tree, tmp_path: Path) -> None:
    _home, root, root_fd = tree
    (root / "real").mkdir()
    (root / "real" / "f.md").write_text("x")
    (root / "link").symlink_to(root / "real")                       # a mid-path folder link
    (root / "file-link.md").symlink_to(root / "real" / "f.md")      # a final file link
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("no")
    (root / "out").symlink_to(outside)                              # a link pointing outside the grant
    (root / "out-file.md").symlink_to(outside / "secret.md")
    assert _code(lambda: open_file(root_fd, split_rel("link/f.md"), os.O_RDONLY)) == "off_limits"
    assert _code(lambda: open_file(root_fd, split_rel("file-link.md"), os.O_RDONLY)) == "off_limits"
    assert _code(lambda: open_dir(root_fd, split_rel("link"))) == "off_limits"
    assert _code(lambda: open_dir(root_fd, split_rel("out"))) == "off_limits"
    assert _code(lambda: open_file(root_fd, split_rel("out/secret.md"), os.O_RDONLY)) == "off_limits"
    assert _code(lambda: open_file(root_fd, split_rel("out-file.md"), os.O_RDONLY)) == "off_limits"
    ok = open_file(root_fd, split_rel("real/f.md"), os.O_RDONLY)
    os.close(ok)


def test_hard_links_fifos_and_devices_are_refused(tree, monkeypatch: pytest.MonkeyPatch) -> None:
    _home, root, root_fd = tree
    (root / "a.md").write_text("x")
    os.link(root / "a.md", root / "b.md")
    assert _code(lambda: open_file(root_fd, split_rel("a.md"), os.O_RDONLY)) == "off_limits"
    assert _code(lambda: open_file(root_fd, split_rel("b.md"), os.O_RDONLY)) == "off_limits"
    os.mkfifo(root / "pipe.md")
    assert _code(lambda: open_file(root_fd, split_rel("pipe.md"), os.O_RDONLY)) == "off_limits"   # and never hangs
    (root / "plain.md").write_text("x")
    real_fstat = os.fstat

    def device_fstat(fd: int) -> os.stat_result:
        st = real_fstat(fd)
        return os.stat_result((stat.S_IFCHR | 0o600, st.st_ino, st.st_dev, 1, st.st_uid, st.st_gid, 0, 0, 0, 0))

    monkeypatch.setattr(paths.os, "fstat", device_fstat)
    assert _code(lambda: open_file(root_fd, split_rel("plain.md"), os.O_RDONLY)) == "off_limits"


def test_permission_errors_become_mac_said_no(tree, monkeypatch: pytest.MonkeyPatch) -> None:
    _home, root, root_fd = tree
    assert _code(lambda: open_file(root_fd, split_rel("missing.md"), os.O_RDONLY)) == "not_found"
    assert _code(lambda: open_dir(root_fd, split_rel("missing"))) == "not_found"
    (root / "locked").mkdir()
    (root / "locked" / "f.md").write_text("x")
    (root / "locked").chmod(0)
    try:
        assert _code(lambda: open_file(root_fd, split_rel("locked/f.md"), os.O_RDONLY)) == "mac_said_no"
    finally:
        (root / "locked").chmod(0o700)
    real_open = os.open

    def eperm(path, flags, *args, **kwargs):
        if kwargs.get("dir_fd") is not None:
            raise OSError(errno.EPERM, "Operation not permitted")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(paths.os, "open", eperm)
    assert _code(lambda: open_dir(root_fd, ("x",))) == "mac_said_no"


def test_a_resolved_path_in_a_denied_place_is_refused(tree) -> None:
    home, root, root_fd = tree
    (root / "ok").mkdir()
    fd = open_dir(root_fd, ("ok",), home=str(home))
    os.close(fd)
    other_home = str(home.parent / "elsewhere")          # the folder is outside this home: denied
    assert _code(lambda: open_dir(root_fd, ("ok",), home=other_home)) == "off_limits"


def test_dataless_flag() -> None:
    class St:
        st_flags = 0x40000000

    assert paths.is_dataless(St())          # type: ignore[arg-type]
    assert not paths.is_dataless(os.stat("/"))
