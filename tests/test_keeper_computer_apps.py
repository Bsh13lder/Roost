"""The keeper's apps route (docs/plans/2026-10-22-roost-install-app.md §4): signed, strict, names checked again,
one fixed argv run as root inside that bot's computer only, never on a computer that is not running.

Over TestClient with a fake docker runner and a fake apps runner: nothing here starts Docker or apt."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from roost.apps.constants import APPS_PER_BOT_MAX, keeper_timeout_s
from roost.config import RoostConfig
from roost.desk.signing import signed_headers
from roost.keeper.app import create_app
from roost.keeper.computer_apps import build_apps_argv
from roost.keeper.computer_room import ComputerRoom
from roost.keeper.computers import ComputerManager
from roost.keeper.workspaces import _RunOutcome

_SECRET = "k" * 32
BOT = str(uuid.uuid4())


class DockerFake:
    async def __call__(self, argv, timeout_s) -> _RunOutcome:
        argv = list(argv)
        if argv[1] == "info":
            return _RunOutcome(0, f"{8000 * 1024 * 1024}\n".encode(), b"", False)
        if argv[1] == "stats":
            return _RunOutcome(0, b"2000MiB / 8GiB\n", b"", False)
        return _RunOutcome(0, b"", b"", False)


class FakeNetworks:
    async def ensure_egress(self) -> None: ...
    async def ensure_bot_network(self, bot_id: str) -> None: ...
    async def remove_bot_network(self, bot_id: str) -> None: ...


class AptFake:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], float]] = []
        self.answer = _RunOutcome(0, b"", b"", False)

    async def __call__(self, argv, timeout_s) -> _RunOutcome:
        self.calls.append((list(argv), timeout_s))
        return self.answer


@pytest.fixture
def config(tmp_path: Path) -> RoostConfig:
    return RoostConfig(server_secret="x" * 32, database_dir=tmp_path / "data", desks_dir=tmp_path / "desks",
                       keeper_secret=_SECRET)


@pytest.fixture
def apt() -> AptFake:
    return AptFake()


@pytest.fixture
def client(config, apt) -> TestClient:
    app = create_app(config)
    docker = DockerFake()
    app.state.computers = ComputerManager(config, FakeNetworks(), runner=docker)
    app.state.room = ComputerRoom(app.state.computers, runner=docker)
    app.state.apps_runner = apt
    return TestClient(app)


def _post(client: TestClient, path: str, payload: dict | bytes, *, sign: bool = True):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    headers = signed_headers(_SECRET, "POST", path, body) if sign else {}
    return client.post(path, headers=headers, content=body)


def _apps(client, verb, packages, *, bot_id=BOT, sign=True):
    return _post(client, f"/desks/{bot_id}/computer/apps", {"verb": verb, "packages": packages}, sign=sign)


def _start(client, bot_id=BOT):
    return _post(client, f"/desks/{bot_id}/computer/start", {"busy": []})


def _audit(config) -> list[dict]:
    path = config.database_dir / "keeper-audit.log"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_unsigned_is_refused(client, apt):
    _start(client)
    assert _apps(client, "install", ["gimp"], sign=False).status_code == 401
    assert apt.calls == []


def test_a_bad_bot_id_is_400(client, apt):
    assert _apps(client, "install", ["gimp"], bot_id="nope").status_code == 400
    assert apt.calls == []


@pytest.mark.parametrize("body", [
    {"verb": "install", "packages": ["gimp", "vlc"]}, {"verb": "install", "packages": []},
    {"verb": "purge", "packages": ["gimp"]}, {"verb": "install", "packages": ["gimp; reboot"]},
    {"verb": "install", "packages": ["https://x.org/a.deb"]}, {"verb": "install", "packages": ["sudo"]},
    {"verb": "ensure", "packages": ["gimp", "firefox-esr"]}, {"verb": "install", "packages": ["gimp"], "x": 1},
    {"verb": "ensure", "packages": [f"pkg{i}" for i in range(APPS_PER_BOT_MAX + 1)]},
    {"verb": "install", "packages": "gimp"},
])
def test_a_bad_or_denied_body_is_422(client, apt, body):
    _start(client)
    assert _post(client, f"/desks/{BOT}/computer/apps", body).status_code == 422
    assert apt.calls == []


def test_never_on_a_computer_that_is_not_running(client, apt):
    response = _apps(client, "install", ["gimp"])
    assert (response.status_code, response.json()["detail"]) == (409, "asleep")
    assert apt.calls == []


def test_the_argv_is_one_fixed_root_exec_in_that_computer(client, apt, config):
    _start(client)
    response = _apps(client, "install", ["gimp"])
    assert response.status_code == 200 and response.json() == {"done": True}
    [(argv, timeout_s)] = apt.calls
    assert argv == ["docker", "exec", "--user", "0:0", f"roost-computer-{BOT}", "/usr/local/bin/roost-apt",
                    "install", "gimp"]
    assert timeout_s == keeper_timeout_s("install")
    entry = _audit(config)[-1]
    assert (entry["action"], entry["verb"], entry["result"]) == ("computer_apps", "install", "ok")
    assert "gimp" not in (config.database_dir / "keeper-audit.log").read_text()


def test_describe_returns_debians_line(client, apt):
    _start(client)
    apt.answer = _RunOutcome(0, json.dumps({"package": "gimp", "version": "2.10",
                                            "description": "GNU Image Manipulation Program"}).encode(), b"", False)
    body = _apps(client, "describe", ["gimp"]).json()
    assert body == {"done": True, "package": "gimp", "version": "2.10", "description": "GNU Image Manipulation Program"}


def test_a_refusal_word_is_409_and_anything_else_500(client, apt):
    _start(client)
    apt.answer = _RunOutcome(3, b"", b"not_debian\n", False)
    response = _apps(client, "install", ["gimp"])
    assert (response.status_code, response.json()["detail"]) == (409, "not_debian")
    apt.answer = _RunOutcome(3, b"", b"E: some apt text\n", False)
    response = _apps(client, "install", ["gimp"])
    assert (response.status_code, response.json()["detail"]) == (500, "apps failed")
    apt.answer = _RunOutcome(-1, b"", b"", True)
    assert _apps(client, "remove", ["gimp"]).status_code == 500


def test_ensure_takes_the_whole_list(client, apt):
    _start(client)
    assert _apps(client, "ensure", ["gimp", "vlc"]).status_code == 200
    assert apt.calls[0][0][-3:] == ["ensure", "gimp", "vlc"]


def test_build_argv_refuses_a_bad_id():
    with pytest.raises(ValueError):
        build_apps_argv("roost-x", "install", ("gimp",))


def test_a_fresh_start_says_so_once(client):
    assert _start(client).json()["fresh"] is True
    assert _start(client).json()["fresh"] is False
    assert _post(client, f"/desks/{BOT}/computer/stop", {}).status_code == 200
    assert _start(client).json()["fresh"] is False     # a stopped computer keeps its container, and its apps
