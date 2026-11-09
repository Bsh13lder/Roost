"""FakeMacFiles follows the keeper's rules, in memory (Task 7; Design meets code 19)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from mac_helpers import BOT_A, grant
from roost.config import load_config
from roost.keeper.macfs.errors import MacFsError
from roost.mac.fake_files import FakeMacFiles, load_fake_tree
from roost.mac.files import KeeperMacFiles, make_mac_files
from roost.mac.models import FileRef, UndoSpec

TREE = {
    "Notes/Tasks.md": "- one\n", "Notes/prod.env": "SECRET=1", "Notes/.hidden.md": "x",
    "Notes/bin.md": "a\0b", "Notes/sub/deep.md": "needle here", "Docs/a.md": "doc",
}


@pytest.fixture
def home(tmp_path: Path) -> str:
    return str(tmp_path / "home")


async def _fake(home: str, access: str = "read_write") -> FakeMacFiles:
    files = FakeMacFiles(TREE, home)
    await files.push_grants((grant(f"{home}/Notes", access=access),))
    return files


def _ref(path: str, bot_id: str = BOT_A) -> FileRef:
    return FileRef("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", bot_id, path)


async def _code(awaitable) -> str:
    with pytest.raises(MacFsError) as err:
        await awaitable
    return err.value.code


async def test_the_fake_follows_the_same_rules(home: str) -> None:
    files = await _fake(home)
    text = await files.read(_ref("Tasks.md"))
    assert text.text == "- one\n" and len(text.sha256) == 64
    assert await _code(files.read(_ref("bin.md"))) == "not_text"
    assert await _code(files.read(_ref("prod.env"))) == "off_limits"
    assert await _code(files.read(_ref(".hidden.md"))) == "off_limits"
    assert await _code(files.read(_ref("../x"))) == "bad_path"
    assert await _code(files.read(_ref("missing.md"))) == "not_found"
    listing = await files.list(_ref(""))
    assert [e.name for e in listing.entries] == ["Tasks.md", "bin.md", "sub"]
    hits = await files.find(_ref("").grant_id, BOT_A, text="NEEDLE")
    assert [h.path for h in hits.hits] == ["sub/deep.md"]
    assert await _code(files.create(_ref("Tasks.md"), "x")) == "exists"
    assert await _code(files.create(_ref("a.pdf"), "x")) == "bad_ext"
    assert (await files.create(_ref("new.md"), "hello")).size == 5
    stale = None
    try:
        await files.write(_ref("Tasks.md"), "x", "0" * 64)
    except MacFsError as exc:
        stale = exc
    assert stale is not None and stale.code == "changed" and stale.current_sha256 == text.sha256
    written = await files.write(_ref("Tasks.md"), "- two\n", text.sha256)
    assert written.backup_id is not None and (await files.read(_ref("Tasks.md"))).text == "- two\n"
    assert await _code(files.rename(_ref("Tasks.md"), "new.md", written.sha256)) == "exists"
    await files.rename(_ref("Tasks.md"), "Renamed.md", written.sha256)
    trashed = await files.trash(_ref("Renamed.md"), written.sha256)
    assert await _code(files.read(_ref("Renamed.md"))) == "not_found"
    await files.undo(_ref("").grant_id, BOT_A, UndoSpec(kind="trash", trash_name=trashed.trash_name, back_to="Back.md"))
    assert (await files.read(_ref("Back.md"))).text == "- two\n"
    content = await files.write(_ref("Back.md"), "- three\n", (await files.read(_ref("Back.md"))).sha256)
    await files.undo(_ref("").grant_id, BOT_A, UndoSpec(
        kind="content", path="Back.md", backup_id=content.backup_id, expected_sha256=content.sha256))
    assert (await files.read(_ref("Back.md"))).text == "- two\n"


async def test_the_fake_refuses_like_the_keeper_on_grants_and_access(home: str) -> None:
    fresh = FakeMacFiles(TREE, home)
    assert await _code(fresh.list(_ref(""))) == "grants_unset"
    read_only = await _fake(home, access="read")
    assert await _code(read_only.create(_ref("n.md"), "x")) == "read_only"
    assert await _code(read_only.trash(_ref("Tasks.md"), "0" * 64)) == "read_only"
    other_bot = await _fake(home)
    assert await _code(other_bot.list(FileRef("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", BOT_A, ""))) == "no_grant"
    await other_bot.push_grants(())
    assert await _code(other_bot.list(_ref(""))) == "no_grant"
    assert await _code(FakeMacFiles(TREE, home).check_folder(f"{home}/Library")) == "off_limits"
    assert await _code(FakeMacFiles(TREE, home).check_folder(f"{home}/Nope")) == "not_found"
    assert await _code(FakeMacFiles(TREE, home).check_folder("relative")) == "bad_path"
    checked = await FakeMacFiles(TREE, home).check_folder(f"{home}/Notes")
    assert checked.resolved == f"{home}/Notes" and checked.is_vault is False
    assert await FakeMacFiles(TREE, home).pick_folder() == f"{home}/Docs"
    assert await FakeMacFiles({}, home).pick_folder() is None


def test_fake_tree_is_refused_outside_fake_mode(tmp_path: Path) -> None:
    tree_file = tmp_path / "tree.json"
    tree_file.write_text(json.dumps({"Notes/a.md": "x"}))
    env = {"ROOST_DATA_DIR": str(tmp_path / "d"), "ROOST_DESKS_DIR": str(tmp_path / "k"),
           "ROOST_MAC_HOME": str(tmp_path / "h"), "ROOST_FAKE_MAC_TREE": str(tree_file)}
    with pytest.raises(ValueError):
        load_config({**env, "ROOST_DESK": "keeper"})
    config = load_config({**env, "ROOST_DESK": "fake"})
    assert config.fake_mac_tree == tree_file
    made = make_mac_files(config)
    assert isinstance(made, FakeMacFiles)
    assert isinstance(make_mac_files(replace(config, desk_mode="keeper", fake_mac_tree=None)), KeeperMacFiles)


def test_load_fake_tree_validates_the_file(tmp_path: Path) -> None:
    for bad in ("[1, 2]", '{"a.md": 5}', "not json", '{"/abs.md": "x"}', '{"../x.md": "y"}'):
        path = tmp_path / "bad.json"
        path.write_text(bad)
        with pytest.raises(ValueError):
            load_fake_tree(path)
    with pytest.raises(ValueError):
        load_fake_tree(tmp_path / "missing.json")
    good = tmp_path / "good.json"
    good.write_text('{"Notes/a.md": "x", "Empty/": ""}')
    assert load_fake_tree(good) == {"Notes/a.md": "x", "Empty/": ""}
