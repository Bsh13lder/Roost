"""The folder picker (Task 5; Review Focus b5): one fixed argv, no user text, cancel grants nothing."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from roost.constants import MAC_PICK_ARGV, MAC_PICK_TIMEOUT_S
from roost.keeper.macfs.errors import MacFsError
from roost.keeper.macfs.picker import FolderPicker, FolderPickError
from keeper_mac_helpers import MacRig, build_rig


class _Runner:
    def __init__(self, code: int = 0, out: bytes = b"", error: BaseException | None = None) -> None:
        self.calls: list[tuple[tuple[str, ...], float]] = []
        self._result, self._error = (code, out), error

    async def __call__(self, argv, timeout_s):
        self.calls.append((tuple(argv), timeout_s))
        if self._error is not None:
            raise self._error
        return self._result


@pytest.fixture
def rig(tmp_path: Path) -> MacRig:
    return build_rig(tmp_path)


async def test_the_picker_runs_one_fixed_argv_and_cancel_grants_nothing(rig: MacRig) -> None:
    runner = _Runner(0, (str(rig.root) + "/\n").encode())
    picker = FolderPicker(runner, home=str(rig.home))
    assert await picker.pick() == str(rig.root)
    assert runner.calls == [(tuple(MAC_PICK_ARGV), MAC_PICK_TIMEOUT_S)]
    cancelled = _Runner(1, b"")
    assert await FolderPicker(cancelled, home=str(rig.home)).pick() is None
    assert cancelled.calls == [(tuple(MAC_PICK_ARGV), MAC_PICK_TIMEOUT_S)]


async def test_a_picked_denied_folder_is_refused(rig: MacRig) -> None:
    for picked in (rig.home / "Library", rig.home, Path("/etc")):
        picker = FolderPicker(_Runner(0, (str(picked) + "/\n").encode()), home=str(rig.home))
        with pytest.raises(MacFsError) as err:
            await picker.pick()
        assert err.value.code == "off_limits"
    with pytest.raises(MacFsError):
        await FolderPicker(_Runner(0, b"\n"), home=str(rig.home)).pick()


async def test_a_picker_timeout_is_a_clean_error(rig: MacRig) -> None:
    for error in (asyncio.TimeoutError(), OSError("no osascript")):
        with pytest.raises(FolderPickError):
            await FolderPicker(_Runner(error=error), home=str(rig.home)).pick()
    with pytest.raises(FolderPickError):
        await FolderPicker(_Runner(2, b""), home=str(rig.home)).pick()


def test_the_pick_route_answers_the_path_or_null(rig: MacRig) -> None:
    rig.app.state.mac.picker = FolderPicker(_Runner(0, (str(rig.root) + "/\n").encode()), home=str(rig.home))
    assert rig.call("POST", "/mac/pick-folder", {}).json() == {"path": str(rig.root)}
    rig.app.state.mac.picker = FolderPicker(_Runner(1, b""), home=str(rig.home))
    assert rig.call("POST", "/mac/pick-folder", {}).json() == {"path": None}
    rig.app.state.mac.picker = FolderPicker(_Runner(error=asyncio.TimeoutError()), home=str(rig.home))
    failed = rig.call("POST", "/mac/pick-folder", {})
    assert failed.status_code == 503 and failed.json()["detail"] == {"code": "pick_failed"}
    rig.app.state.mac.picker = FolderPicker(_Runner(0, (str(rig.home / "Library") + "\n").encode()), home=str(rig.home))
    assert rig.call("POST", "/mac/pick-folder", {}).status_code == 403
    assert [line["action"] for line in rig.audit_lines()].count("mac_pick") == 4


async def test_the_real_runner_has_no_shell() -> None:
    import inspect

    from roost.keeper.macfs import picker

    source = inspect.getsource(picker)
    assert "shell=True" not in source and "create_subprocess_shell" not in source and "os.system" not in source
