"""The keeper's find (Task 5; Review Focus b2, b4, b6): walked with openat, capped, stopped by a revoke."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from roost.keeper.macfs import find as find_module
from roost.keeper.macfs.find import FindQuery, find
from roost.keeper.macfs.grants import GrantRegistry, KeeperGrant
from roost.constants import MAC_FIND_SNIPPET_CHARS, MAC_FIND_SNIPPETS


@pytest.fixture
def setup(tmp_path: Path):
    home = tmp_path.resolve() / "home"
    root = home / "Notes"
    root.mkdir(parents=True)
    st = root.stat()
    grant = KeeperGrant("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", str(root), "read", None, st.st_dev, st.st_ino)
    registry = GrantRegistry(str(home))
    registry.replace((grant,))
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    yield home, root, grant, registry, fd
    os.close(fd)


def _run(setup, query: FindQuery, **kwargs):
    home, _root, grant, registry, fd = setup
    return find(grant, fd, query, lambda: registry.generation, home=str(home), **kwargs)


def test_find_by_name_and_text_caps_hits_snippets_and_time(setup, monkeypatch: pytest.MonkeyPatch) -> None:
    _home, root, *_ = setup
    for i in range(10):
        (root / f"plan{i}.md").write_text("budget " * 50 + "needle " * 20)
    (root / "other.txt").write_text("nothing here")
    (root / "sub").mkdir()
    (root / "sub" / "deep.md").write_text("A Needle in a haystack")
    (root / ".hidden.md").write_text("needle")
    (root / "prod.env").write_text("needle")
    by_name = _run(setup, FindQuery(name="PLAN"))
    assert len(by_name.hits) == 10 and by_name.truncated is False
    assert all(h["path"].startswith("plan") for h in by_name.hits)
    by_glob = _run(setup, FindQuery(name="*.txt"))
    assert [h["path"] for h in by_glob.hits] == ["other.txt"]
    by_text = _run(setup, FindQuery(text="needle"))
    assert "sub/deep.md" in {h["path"] for h in by_text.hits}
    assert not {h["path"] for h in by_text.hits} & {".hidden.md", "prod.env"}
    for hit in by_text.hits:
        assert 1 <= len(hit["snippets"]) <= MAC_FIND_SNIPPETS
        assert all(len(s) <= MAC_FIND_SNIPPET_CHARS for s in hit["snippets"])
    monkeypatch.setattr(find_module, "MAC_FIND_MAX_HITS", 3)
    capped = _run(setup, FindQuery(name="plan"))
    assert len(capped.hits) == 3 and capped.truncated is True
    monkeypatch.setattr(find_module, "MAC_FIND_MAX_HITS", 200)
    ticks = iter(range(10_000))
    slow = _run(setup, FindQuery(name="plan"), clock=lambda: float(next(ticks)))       # one second per look
    assert slow.truncated is True and len(slow.hits) < 10
    monkeypatch.setattr(find_module, "MAC_FIND_MAX_ENTRIES", 3)
    few = _run(setup, FindQuery(name="plan"))
    assert few.truncated is True and len(few.hits) <= 3


def test_find_text_budgets_skip_big_and_binary_files(setup, monkeypatch: pytest.MonkeyPatch) -> None:
    _home, root, *_ = setup
    (root / "bin.md").write_bytes(b"needle\0")
    (root / "a.md").write_text("needle")
    (root / "b.md").write_text("needle")
    assert [h["path"] for h in _run(setup, FindQuery(text="needle")).hits] == ["a.md", "b.md"]
    monkeypatch.setattr(find_module, "MAC_FIND_TEXT_FILE_MAX_BYTES", 5)
    assert _run(setup, FindQuery(text="needle")).hits == ()
    monkeypatch.setattr(find_module, "MAC_FIND_TEXT_FILE_MAX_BYTES", 1_000_000)
    monkeypatch.setattr(find_module, "MAC_FIND_TEXT_TOTAL_MAX_BYTES", 7)
    assert len(_run(setup, FindQuery(text="needle")).hits) == 1


def test_find_never_follows_a_symlinked_folder(setup, tmp_path: Path) -> None:
    _home, root, *_ = setup
    (root / "real").mkdir()
    (root / "real" / "x.md").write_text("inside")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "y.md").write_text("inside")
    (root / "link").symlink_to(outside)
    (root / "filelink.md").symlink_to(outside / "y.md")
    by_name = _run(setup, FindQuery(name=".md"))
    assert {h["path"] for h in by_name.hits} == {"real/x.md"}
    assert {h["path"] for h in _run(setup, FindQuery(text="inside")).hits} == {"real/x.md"}
    start = _run(setup, FindQuery(name=".md", path_parts=("real",)))
    assert {h["path"] for h in start.hits} == {"real/x.md"}


def test_a_revoke_mid_walk_stops_the_walk(setup) -> None:
    _home, root, _grant, registry, _fd = setup
    for i in range(20):
        (root / f"f{i:02}.md").write_text("x")
    seen: list[str] = []

    def hook(rel: str) -> None:
        seen.append(rel)
        if len(seen) == 2:
            registry.replace(())          # the user revokes while the walk runs

    result = _run(setup, FindQuery(name="f"), on_file=hook)
    assert result.truncated is True and len(seen) <= 3 and len(result.hits) <= 3


def test_find_never_walks_into_multi_part_denied_paths(tmp_path: Path) -> None:
    home = tmp_path.resolve() / "home"
    root = home / "Desktop"
    denied = root / "Code_Projects" / "lazyclaw" / "data"
    denied.mkdir(parents=True)
    (denied / "notes.md").write_text("password hunter2")
    (denied / "deep").mkdir()
    (denied / "deep" / "x.md").write_text("password again")
    ok = root / "Code_Projects" / "other"
    ok.mkdir()
    (ok / "fine.md").write_text("password fine")
    st = root.stat()
    grant = KeeperGrant("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", str(root), "read", None, st.st_dev, st.st_ino)
    registry = GrantRegistry(str(home))
    registry.replace((grant,))
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    seen: list[str] = []
    try:
        for query in (FindQuery(text="password"), FindQuery(name="*")):
            result = find(grant, fd, query, lambda: registry.generation, home=str(home), on_file=seen.append)
            paths = {h["path"] for h in result.hits}
            assert "Code_Projects/other/fine.md" in paths
            assert not any("lazyclaw" in p for p in paths)
            assert all(h["snippets"] == [] or "hunter" not in " ".join(h["snippets"]) for h in result.hits)
    finally:
        os.close(fd)
    assert not any("lazyclaw" in p for p in seen)
