"""The gateway's seam to the keeper's Mac file API (Task 7; Review Focus b6): the real keeper app in process."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from keeper_mac_helpers import MacRig, build_rig
from mac_helpers import BOT_A, GRANT_ID, SwitchTransport, grant
from roost.desk import DeskUnavailable
from roost.desk.client import KeeperClient
from roost.keeper.app import create_app
from roost.keeper.macfs.errors import MacFsError
from roost.keeper.macfs.picker import FolderPicker
from roost.mac.files import KeeperMacFiles
from roost.mac.models import FileRef, UndoSpec


def _files(rig: MacRig, transport: httpx.AsyncBaseTransport | None = None) -> KeeperMacFiles:
    transport = transport or httpx.ASGITransport(app=rig.app)
    return KeeperMacFiles(rig.config, client=KeeperClient(rig.config, transport=transport))


def _ref(path: str) -> FileRef:
    return FileRef(GRANT_ID, BOT_A, path)


async def _error(awaitable) -> MacFsError:
    with pytest.raises(MacFsError) as err:
        await awaitable
    return err.value


async def test_the_client_maps_keeper_codes_to_mac_errors(tmp_path: Path) -> None:
    rig = build_rig(tmp_path, push=False)
    files = _files(rig)
    await files.push_grants((grant(str(rig.root)),))
    (rig.root / "a.md").write_text("one")
    (rig.root / "sub").mkdir()
    read = await files.read(_ref("a.md"))
    assert read.text == "one" and len(read.sha256) == 64
    assert [(e.name, e.kind) for e in (await files.list(_ref(""))).entries] == [("a.md", "file"), ("sub", "folder")]
    assert [h.path for h in (await files.find(GRANT_ID, BOT_A, name="a.md")).hits] == ["a.md"]
    stats = await files.stat(GRANT_ID, BOT_A, ("a.md", "zzz.md"))
    assert stats[0].sha256 == read.sha256 and stats[1].sha256 is None
    assert (await _error(files.read(_ref("zzz.md")))).code == "not_found"
    assert (await _error(files.read(_ref(".secret.md")))).code == "off_limits"
    assert (await _error(files.read(_ref("../x")))).code == "bad_path"
    changed = await _error(files.write(_ref("a.md"), "two", "0" * 64))
    assert changed.code == "changed" and changed.current_sha256 == read.sha256
    assert (await _error(files.create(_ref("a.md"), "x"))).code == "exists"
    created = await files.create(_ref("b.md"), "bee")
    written = await files.write(_ref("b.md"), "bee two", created.sha256)
    assert written.backup_id and (rig.root / "b.md").read_text() == "bee two"
    renamed = await files.rename(_ref("b.md"), "c.md", written.sha256)
    assert renamed == written.sha256
    trashed = await files.trash(_ref("c.md"), written.sha256)
    assert (rig.root / ".roost-trash" / trashed.trash_name).exists()
    restored = await files.undo(GRANT_ID, BOT_A, UndoSpec(kind="trash", trash_name=trashed.trash_name, back_to="c.md"))
    assert restored == written.sha256 and (rig.root / "c.md").read_text() == "bee two"
    await files.push_grants((grant(str(rig.root), access="read"),))
    assert (await _error(files.create(_ref("d.md"), "x"))).code == "read_only"
    await files.push_grants(())
    assert (await _error(files.read(_ref("a.md")))).code == "no_grant"


async def test_check_and_pick_go_through_the_keeper(tmp_path: Path) -> None:
    rig = build_rig(tmp_path, push=False)
    files = _files(rig)
    checked = await files.check_folder(str(rig.root))
    assert checked.resolved == str(rig.root) and checked.is_vault is False
    assert (await _error(files.check_folder(str(rig.home / "Library")))).code == "off_limits"

    async def cancel(argv, timeout):
        return 1, b""

    rig.app.state.mac.picker = FolderPicker(cancel, home=str(rig.home))
    assert await files.pick_folder() is None

    async def pick(argv, timeout):
        return 0, (str(rig.root) + "/\n").encode()

    rig.app.state.mac.picker = FolderPicker(pick, home=str(rig.home))
    assert await files.pick_folder() == str(rig.root)

    async def hang(argv, timeout):
        raise TimeoutError

    rig.app.state.mac.picker = FolderPicker(hang, home=str(rig.home))
    assert (await _error(files.pick_folder())).code == "pick_failed"


async def test_a_lost_keeper_gets_the_grants_again(tmp_path: Path) -> None:
    rig = build_rig(tmp_path, push=False)
    switch = SwitchTransport(httpx.ASGITransport(app=rig.app))
    files = _files(rig, switch)
    await files.push_grants((grant(str(rig.root)),))
    (rig.root / "a.md").write_text("one")
    assert (await files.read(_ref("a.md"))).text == "one"
    fresh = create_app(rig.config)                        # the keeper restarted: it holds no grants
    switch.current = httpx.ASGITransport(app=fresh)
    assert (await files.read(_ref("a.md"))).text == "one"   # grants_unset, push, retry once
    assert fresh.state.mac.registry.lookup(GRANT_ID, BOT_A).root == str(rig.root)


async def test_a_deleted_folder_does_not_block_a_revoke(tmp_path: Path) -> None:
    rig = build_rig(tmp_path, push=False)
    files = _files(rig)
    gone, kept = rig.home / "Gone", rig.home / "Kept"
    gone.mkdir()
    kept.mkdir()
    (kept / "k.md").write_text("k")
    second = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    await files.push_grants((grant(str(gone)), grant(str(kept), grant_id=second)))
    gone.rmdir()
    await files.push_grants((grant(str(gone)), grant(str(kept), grant_id=second)))   # the keeper refuses the set
    assert (await files.read(FileRef(second, BOT_A, "k.md"))).text == "k"
    assert (await _error(files.read(_ref("k.md")))).code == "no_grant"


async def test_an_unreachable_keeper_is_desk_unavailable(tmp_path: Path) -> None:
    rig = build_rig(tmp_path, push=False)

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    files = _files(rig, httpx.MockTransport(refuse))
    with pytest.raises(DeskUnavailable):
        await files.push_grants((grant(str(rig.root)),))
    with pytest.raises(DeskUnavailable):
        await files.read(_ref("a.md"))
    with pytest.raises(DeskUnavailable):
        await files.check_folder(str(rig.root))
    unsigned = _files(rig, httpx.MockTransport(lambda request: httpx.Response(401, json={"detail": "nope"})))
    with pytest.raises(DeskUnavailable):
        await unsigned.read(_ref("a.md"))
