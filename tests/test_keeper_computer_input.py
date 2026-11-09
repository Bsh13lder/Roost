"""C3 Task 4: the keeper's computer input route (security review b).

Over TestClient with a fake docker runner and a fake input runner: nothing here starts Docker or xdotool."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from roost.computer_use.timing import keeper_input_timeout_s
from roost.config import RoostConfig
from roost.constants import CU_INPUT_MAX_PER_SECOND, CU_INPUT_TIMEOUT_S, CU_KEYS, CU_TYPE_MAX_CHARS
from roost.desk.signing import signed_headers
from roost.keeper.app import create_app
from roost.keeper.computer_input import (
    ClickAction,
    InputRateLimiter,
    KeyAction,
    MoveAction,
    ScrollAction,
    TypeAction,
    WindowRect,
    build_input_argv,
    input_stdin,
    run_input,
)
from roost.keeper.computer_room import ComputerRoom
from roost.keeper.computers import ComputerManager
from roost.keeper.workspaces import _RunOutcome

_SECRET = "k" * 32
BOT = str(uuid.uuid4())
SECRET_TEXT = "hunter2 secret"


class DockerFake:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def __call__(self, argv, timeout_s) -> _RunOutcome:
        argv = list(argv)
        self.calls.append(argv)
        if argv[1] == "info":
            return _RunOutcome(0, f"{8000 * 1024 * 1024}\n".encode(), b"", False)
        if argv[1] == "stats":
            return _RunOutcome(0, b"2000MiB / 8GiB\n", b"", False)
        return _RunOutcome(0, b"", b"", False)


class FakeNetworks:
    async def ensure_egress(self) -> None: ...
    async def ensure_bot_network(self, bot_id: str) -> None: ...
    async def remove_bot_network(self, bot_id: str) -> None: ...


class InputFake:
    """Stands in for ``docker exec -i ... roost-input``: records argv, stdin and timeout."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], bytes | None, float]] = []
        self.answer = _RunOutcome(0, b"", b"", False)

    async def __call__(self, argv, stdin, timeout_s) -> _RunOutcome:
        self.calls.append((list(argv), stdin, timeout_s))
        return self.answer


@pytest.fixture
def config(tmp_path: Path) -> RoostConfig:
    return RoostConfig(server_secret="x" * 32, database_dir=tmp_path / "data", desks_dir=tmp_path / "desks",
                       keeper_secret=_SECRET)


@pytest.fixture
def docker() -> DockerFake:
    return DockerFake()


@pytest.fixture
def runner() -> InputFake:
    return InputFake()


@pytest.fixture
def client(config, docker, runner) -> TestClient:
    app = create_app(config)
    app.state.computers = ComputerManager(config, FakeNetworks(), runner=docker)
    app.state.room = ComputerRoom(app.state.computers, runner=docker)
    app.state.input_runner = runner
    return TestClient(app)


def _post(client: TestClient, path: str, payload: dict | bytes = b"{}", *, sign: bool = True):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    headers = signed_headers(_SECRET, "POST", path, body) if sign else {}
    return client.post(path, headers=headers, content=body)


WINDOW = {"left": 0, "top": 0, "width": 1280, "height": 800}
WINDOW_ARGV = ["--window", "0", "0", "1280", "800"]


def _input(client: TestClient, action: dict, *, bot_id: str = BOT, held: bool = False, sign: bool = True, **extra):
    body = {"action": action, "held": held, "window": WINDOW, **extra}
    return _post(client, f"/desks/{bot_id}/computer/input", body, sign=sign)


def _start(client: TestClient, bot_id: str = BOT) -> None:
    assert _post(client, f"/desks/{bot_id}/computer/start", {"busy": []}).status_code == 200


def _audit(config: RoostConfig) -> list[dict]:
    path = config.database_dir / "keeper-audit.log"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


CLICK = {"verb": "click", "x": 100, "y": 200}
TYPE = {"verb": "type", "text": SECRET_TEXT}


def test_unsigned_is_refused(client, runner):
    _start(client)
    assert _input(client, CLICK, sign=False).status_code == 401
    assert runner.calls == []


def test_a_bad_bot_id_is_400(client, runner):
    assert _input(client, CLICK, bot_id="not-a-uuid").status_code == 400
    assert _input(client, CLICK, bot_id=str(uuid.uuid1())).status_code == 400
    assert runner.calls == []


def test_the_argv_is_fixed_and_has_no_text(client, runner, config, caplog):
    _start(client)
    with caplog.at_level(logging.DEBUG):
        response = _input(client, TYPE)
    assert response.status_code == 200 and response.json() == {"done": True}
    [(argv, stdin, timeout_s)] = runner.calls
    prefix = ["docker", "exec", "-i", "--user", "10002:10002", f"roost-computer-{BOT}", "/usr/local/bin/roost-input"]
    assert argv == [*prefix, "type", *WINDOW_ARGV]
    assert stdin == SECRET_TEXT.encode("utf-8")
    assert timeout_s == keeper_input_timeout_s(len(SECRET_TEXT)) > CU_INPUT_TIMEOUT_S
    assert not any("hunter2" in part for part in argv)
    assert "hunter2" not in (config.database_dir / "keeper-audit.log").read_text()
    assert "hunter2" not in caplog.text and "hunter2" not in response.text


def test_each_verb_builds_its_own_fixed_argv():
    rect = WindowRect(left=-40, top=30, width=800, height=600)
    tail = lambda action: build_input_argv(BOT, action, rect)[7:]  # noqa: E731
    win = ["--window", "-40", "30", "800", "600"]
    assert tail(ClickAction(verb="click", x=1, y=2, count=2)) == ["click", "1", "2", "2", *win]
    assert tail(MoveAction(verb="move", x=1279, y=799)) == ["move", "1279", "799", *win]
    assert tail(KeyAction(verb="key", key="Return")) == ["key", "Return", *win]
    assert tail(TypeAction(verb="type", text="x y")) == ["type", *win]
    assert tail(ScrollAction(verb="scroll", x=5, y=6, notches=-3)) == ["scroll", "5", "6", "-3", *win]
    assert input_stdin(TypeAction(verb="type", text="héllo")) == "héllo".encode("utf-8")
    assert input_stdin(ClickAction(verb="click", x=1, y=2)) is None


def test_a_bad_bot_id_builds_no_argv():
    with pytest.raises(ValueError):
        build_input_argv("roost-workspace-x", ClickAction(verb="click", x=1, y=2),
                         WindowRect(left=0, top=0, width=10, height=10))


@pytest.mark.parametrize("payload", [
    {"action": CLICK, "held": False, "shell": "rm -rf /", "window": WINDOW},
    {"action": {**CLICK, "button": 3}, "window": WINDOW},
    {"action": {"verb": "click", "x": 1280, "y": 0}, "window": WINDOW},
    {"action": {"verb": "click", "x": 0, "y": 800}, "window": WINDOW},
    {"action": {"verb": "click", "x": -1, "y": 0}, "window": WINDOW},
    {"action": {"verb": "click", "x": "10", "y": 0}, "window": WINDOW},
    {"action": {"verb": "click", "x": 1, "y": 1, "count": 3}, "window": WINDOW},
    {"action": {"verb": "scroll", "x": 1, "y": 1, "notches": 0}, "window": WINDOW},
    {"action": {"verb": "scroll", "x": 1, "y": 1, "notches": 11}, "window": WINDOW},
    {"action": {"verb": "type", "text": ""}, "window": WINDOW},
    {"action": {"verb": "type", "text": "x" * (CU_TYPE_MAX_CHARS + 1)}, "window": WINDOW},
    {"action": {"verb": "type", "text": "line\nbreak"}, "window": WINDOW},
    {"action": {"verb": "exec", "argv": ["sh"]}, "window": WINDOW},
    {"action": CLICK},
    {"action": CLICK, "window": {**WINDOW, "width": 0}},
    {"action": CLICK, "window": {**WINDOW, "left": 99999}},
    {"action": CLICK, "window": {**WINDOW, "id": 4}},
    {},
])
def test_extra_fields_are_422(client, runner, payload):
    _start(client)
    response = _post(client, f"/desks/{BOT}/computer/input", payload)
    assert response.status_code == 422
    assert runner.calls == []


def test_a_422_never_echoes_the_text(client):
    _start(client)
    response = _input(client, {"verb": "type", "text": SECRET_TEXT + "\n"})
    assert response.status_code == 422 and "hunter2" not in response.text


@pytest.mark.parametrize("key", ["ctrl+l", "Control_L", "super", "F12", "Enter", "alt+F4", "Return Return"])
def test_keys_must_be_listed_keysyms(client, runner, key):
    _start(client)
    assert _input(client, {"verb": "key", "key": key}).status_code == 422
    assert runner.calls == []


def test_every_listed_keysym_is_accepted(client, runner):
    _start(client)
    client.app.state.input_limiter = InputRateLimiter(max_per_second=100)
    for keysym in CU_KEYS.values():
        assert _input(client, {"verb": "key", "key": keysym}).status_code == 200
    assert [call[0][8] for call in runner.calls] == list(CU_KEYS.values())


def test_asleep_is_409_and_never_starts(client, runner, docker):
    response = _input(client, CLICK)
    assert (response.status_code, response.json()) == (409, {"detail": "asleep"})
    _start(client)
    assert _post(client, f"/desks/{BOT}/computer/pause").status_code == 200
    docker.calls.clear()
    response = _input(client, CLICK)
    assert (response.status_code, response.json()) == (409, {"detail": "asleep"})
    assert not [c for c in docker.calls if c[1] in ("unpause", "start", "run")]
    assert runner.calls == []
    assert client.app.state.computers.state(BOT) == "paused"


def test_held_is_409(client, runner):
    _start(client)
    response = _input(client, CLICK, held=True)
    assert (response.status_code, response.json()) == (409, {"detail": "held"})
    assert runner.calls == []


@pytest.mark.parametrize("word", ["not_chromium", "outside"])
def test_not_chromium_maps_to_409(client, runner, word):
    _start(client)
    runner.answer = _RunOutcome(3, b"", f"{word}\n".encode(), False)
    response = _input(client, CLICK)
    assert (response.status_code, response.json()) == (409, {"detail": word})


@pytest.mark.parametrize("outcome", [
    _RunOutcome(4, b"", b"input failed\n", False),
    _RunOutcome(3, b"", b"something else\n", False),
    _RunOutcome(2, b"", b"bad arguments\n", False),
    _RunOutcome(-1, b"", b"", True),
    _RunOutcome(1, b"", b"Error: No such container", False),
])
def test_other_failures_are_a_plain_500(client, runner, outcome):
    _start(client)
    runner.answer = outcome
    response = _input(client, CLICK)
    assert (response.status_code, response.json()) == (500, {"detail": "input failed"})


def test_a_runner_that_cannot_start_is_a_plain_500(client, runner):
    _start(client)

    async def broken(argv, stdin, timeout_s):
        raise OSError("docker not found")

    client.app.state.input_runner = broken
    response = _input(client, CLICK)
    assert (response.status_code, response.json()) == (500, {"detail": "input failed"})


def test_too_fast_is_429(client, runner):
    _start(client)
    answers = [_input(client, CLICK).status_code for _ in range(CU_INPUT_MAX_PER_SECOND + 1)]
    assert answers[:-1] == [200] * CU_INPUT_MAX_PER_SECOND
    assert answers[-1] == 429
    assert _input(client, CLICK).json() == {"detail": "too_fast"}
    assert len(runner.calls) == CU_INPUT_MAX_PER_SECOND


def test_the_rate_window_slides():
    now = [0.0]
    limiter = InputRateLimiter(max_per_second=2, clock=lambda: now[0])
    assert limiter.allow(BOT) and limiter.allow(BOT) and not limiter.allow(BOT)
    assert limiter.allow(str(uuid.uuid4()))
    now[0] = 1.01
    assert limiter.allow(BOT)


def test_input_touches_the_computer(client):
    _start(client)
    manager = client.app.state.computers
    before = manager.last_used(BOT)
    assert _input(client, CLICK).status_code == 200
    assert manager.last_used(BOT) >= before


def test_the_audit_has_the_verb_only(client, runner, config):
    _start(client)
    _input(client, TYPE)
    _input(client, CLICK, held=True)
    runner.answer = _RunOutcome(3, b"", b"not_chromium\n", False)
    _input(client, {"verb": "key", "key": "Return"})
    rows = [row for row in _audit(config) if row["action"] == "computer_input"]
    assert [(row["verb"], row["result"]) for row in rows] == [("type", "ok"), ("click", "held"), ("key", "not_chromium")]
    for row in rows:
        assert set(row) == {"action", "bot_id", "verb", "result", "ts"}
        assert row["bot_id"] == BOT


def test_the_exec_targets_the_computer_never_the_workspace(client, runner):
    _start(client)
    _input(client, CLICK)
    [(argv, stdin, _)] = runner.calls
    assert argv[:7] == ["docker", "exec", "-i", "--user", "10002:10002", f"roost-computer-{BOT}",
                       "/usr/local/bin/roost-input"]
    assert stdin is None
    assert not any("workspace" in part or "privileged" in part or part == "-e" for part in argv)


async def test_the_real_runner_writes_stdin_and_never_uses_a_shell():
    done = await run_input(["/bin/cat"], SECRET_TEXT.encode(), 5.0)
    assert (done.returncode, done.stdout, done.timed_out) == (0, SECRET_TEXT.encode(), False)
    closed = await run_input(["/bin/cat"], None, 5.0)
    assert (closed.returncode, closed.stdout) == (0, b"")


async def test_the_real_runner_kills_a_slow_input():
    done = await run_input(["/bin/sleep", "5"], None, 0.1)
    assert done.timed_out and done.returncode == -1
