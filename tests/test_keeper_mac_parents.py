"""create with ``parents``: the keeper makes missing folders inside the grant, never through a link or a dot name
(obsidian track: the vault export writes under <grant>/Roost/...)."""

from __future__ import annotations

from pathlib import Path

import pytest

from keeper_mac_helpers import MacRig, build_rig
from roost.mac.fake_files import FakeMacFiles
from roost.mac.models import FileRef, Grant
from roost.keeper.macfs.errors import MacFsError

BOT = "11111111-1111-4111-8111-111111111111"
GRANT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


@pytest.fixture
def rig(tmp_path: Path) -> MacRig:
    return build_rig(tmp_path)


def _code(response) -> str:
    return response.json()["detail"]["code"]


def test_without_parents_a_missing_folder_is_not_found(rig: MacRig) -> None:
    assert _code(rig.fs("create", {"path": "Roost/Projects/a.md", "text": "x"})) == "not_found"
    assert not (rig.root / "Roost").exists()


def test_with_parents_the_folders_are_made_and_the_file_written(rig: MacRig) -> None:
    made = rig.fs("create", {"path": "Roost/Projects/Garden/Garden.md", "text": "hi", "parents": True})
    assert made.status_code == 200
    assert (rig.root / "Roost" / "Projects" / "Garden" / "Garden.md").read_text() == "hi"
    again = rig.fs("create", {"path": "Roost/Projects/Garden/Tasks/a.md", "text": "x", "parents": True})
    assert again.status_code == 200 and (rig.root / "Roost/Projects/Garden/Tasks/a.md").exists()


def test_parents_never_make_a_dot_or_denied_folder_or_follow_a_link(rig: MacRig, tmp_path: Path) -> None:
    assert _code(rig.fs("create", {"path": ".obsidian/x.md", "text": "x", "parents": True})) == "off_limits"
    assert _code(rig.fs("create", {"path": "id_rsa/x.md", "text": "x", "parents": True})) == "off_limits"
    outside = tmp_path / "outside"
    outside.mkdir()
    (rig.root / "Roost").symlink_to(outside)
    assert _code(rig.fs("create", {"path": "Roost/x.md", "text": "x", "parents": True})) == "off_limits"
    assert list(outside.iterdir()) == []


def test_parents_need_a_read_write_grant(tmp_path: Path) -> None:
    rig = build_rig(tmp_path, access="read")
    assert _code(rig.fs("create", {"path": "Roost/x.md", "text": "x", "parents": True})) == "read_only"
    assert not (rig.root / "Roost").exists()


async def test_the_fake_follows_the_same_rule() -> None:
    fake = FakeMacFiles({"Notes/": ""}, "/Users/me")
    await fake.push_grants([Grant(GRANT, "u", None, "/Users/me/Notes", "Notes", "read_write", "ask_each", False,
                                  "t", None)])
    ref = FileRef(GRANT, BOT, "Roost/Projects/a.md")
    with pytest.raises(MacFsError):
        await fake.create(ref, "x")
    made = await fake.create(ref, "x", parents=True)
    assert made.size == 1 and (await fake.read(ref)).text == "x"
    with pytest.raises(MacFsError):
        await fake.create(FileRef(GRANT, BOT, ".obsidian/a.md"), "x", parents=True)


async def test_the_gateway_seam_sends_parents_to_the_keeper(rig: MacRig) -> None:
    import httpx

    from roost.desk.client import KeeperClient
    from roost.mac.files import KeeperMacFiles

    files = KeeperMacFiles(rig.config, client=KeeperClient(rig.config, transport=httpx.ASGITransport(app=rig.app)))
    await files.push_grants((Grant(GRANT, "u", None, str(rig.root), "Notes", "read_write", "ask_each", False,
                                   "t", None),))
    with pytest.raises(MacFsError):
        await files.create(FileRef(GRANT, BOT, "Deep/a.md"), "x")
    await files.create(FileRef(GRANT, BOT, "Deep/a.md"), "x", parents=True)
    assert (rig.root / "Deep" / "a.md").read_text() == "x"
