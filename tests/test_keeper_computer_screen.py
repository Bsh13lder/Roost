"""Full computer, Step 1: the keeper's input route answers `front` and `browsers`, runs `open <app>`, and sends
`--screen` acts (no window). Over TestClient with a fake input runner: nothing here starts Docker or xdotool."""

from __future__ import annotations

import pytest

from roost.keeper.computer_input import (
    BrowsersAction,
    ClickAction,
    FrontAction,
    OpenAction,
    TypeAction,
    build_input_argv,
)
from pathlib import Path

from fastapi.testclient import TestClient

from roost.config import RoostConfig
from roost.keeper.app import create_app
from roost.keeper.computer_room import ComputerRoom
from roost.keeper.computers import ComputerManager
from roost.keeper.workspaces import _RunOutcome

from test_keeper_computer_input import (
    _SECRET, BOT, CLICK, SECRET_TEXT, TYPE, WINDOW, DockerFake, FakeNetworks, InputFake, _audit, _post, _start,
)


@pytest.fixture
def config(tmp_path: Path) -> RoostConfig:
    return RoostConfig(server_secret="x" * 32, database_dir=tmp_path / "data", desks_dir=tmp_path / "desks",
                       keeper_secret=_SECRET)


@pytest.fixture
def runner() -> InputFake:
    return InputFake()


@pytest.fixture
def client(config, runner) -> TestClient:
    docker = DockerFake()
    app = create_app(config)
    app.state.computers = ComputerManager(config, FakeNetworks(), runner=docker)
    app.state.room = ComputerRoom(app.state.computers, runner=docker)
    app.state.input_runner = runner
    return TestClient(app)

PREFIX = ["docker", "exec", "-i", "--user", "10002:10002", f"roost-computer-{BOT}", "/usr/local/bin/roost-input"]
PATH = f"/desks/{BOT}/computer/input"


def _send(client, body: dict):
    return _post(client, PATH, body)


def test_query_and_open_argv_have_no_window():
    assert build_input_argv(BOT, FrontAction(verb="front"), None)[7:] == ["front"]
    assert build_input_argv(BOT, BrowsersAction(verb="browsers"), None)[7:] == ["browsers"]
    assert build_input_argv(BOT, OpenAction(verb="open", app="geany"), None)[7:] == ["open", "geany"]
    assert build_input_argv(BOT, ClickAction(verb="click", x=1, y=2), None, screen=True)[7:] == [
        "click", "1", "2", "1", "--screen"]
    assert build_input_argv(BOT, TypeAction(verb="type", text="x"), None, screen=True)[7:] == ["type", "--screen"]
    with pytest.raises(ValueError):
        build_input_argv(BOT, ClickAction(verb="click", x=1, y=2), None)


def test_front_answers_brave_with_its_rect(client, runner):
    _start(client)
    runner.answer = _RunOutcome(0, b"brave 0 40 1280 760\n", b"", False)
    response = _send(client, {"action": {"verb": "front"}})
    assert response.status_code == 200
    assert response.json() == {"front": "brave", "window": [0, 40, 1280, 760]}
    assert runner.calls[0][0] == [*PREFIX, "front"] and runner.calls[0][1] is None


def test_front_answers_other(client, runner):
    _start(client)
    runner.answer = _RunOutcome(0, b"other\n", b"", False)
    assert _send(client, {"action": {"verb": "front"}}).json() == {"front": "other", "window": None}


@pytest.mark.parametrize("out", [b"brave 0 40\n", b"Brave 0 0 10 10\n", b"other\nmore\n", b"brave a b c d\n",
                                 b"brave 0 0 0 10\n", b"brave 0 0 99999 10\n", b"title of a page\n", b""])
def test_a_strange_front_answer_is_a_failure(client, runner, out):
    _start(client)
    runner.answer = _RunOutcome(0, out, b"", False)
    response = _send(client, {"action": {"verb": "front"}})
    assert response.status_code == 500 and response.json() == {"detail": "input failed"}


def test_browsers_answers_rects_only(client, runner):
    _start(client)
    runner.answer = _RunOutcome(0, b"0 40 1280 760\n200 100 800 600\n", b"", False)
    assert _send(client, {"action": {"verb": "browsers"}}).json() == {
        "windows": [[0, 40, 1280, 760], [200, 100, 800, 600]]}
    runner.answer = _RunOutcome(0, b"", b"", False)
    assert _send(client, {"action": {"verb": "browsers"}}).json() == {"windows": []}
    runner.answer = _RunOutcome(0, b"".join(b"0 0 10 10\n" for _ in range(17)), b"", False)
    assert _send(client, {"action": {"verb": "browsers"}}).status_code == 500


def test_open_runs_and_audits_the_verb_and_app_only(client, runner, config):
    _start(client)
    response = _send(client, {"action": {"verb": "open", "app": "files"}})
    assert response.status_code == 200 and response.json() == {"done": True}
    assert runner.calls[-1][0] == [*PREFIX, "open", "files"]
    entry = _audit(config)[-1]
    assert entry["action"] == "computer_input" and entry["verb"] == "open" and entry["app"] == "files"
    assert set(entry) == {"action", "bot_id", "result", "ts", "verb", "app"}


def test_open_no_window_is_409(client, runner):
    _start(client)
    runner.answer = _RunOutcome(3, b"", b"no_window\n", False)
    response = _send(client, {"action": {"verb": "open", "app": "geany"}})
    assert response.status_code == 409 and response.json() == {"detail": "no_window"}


def test_a_screen_act_sends_no_window_and_text_on_stdin_only(client, runner, config):
    _start(client)
    response = _send(client, {"action": TYPE, "screen": True})
    assert response.status_code == 200
    argv, stdin, _ = runner.calls[-1]
    assert argv == [*PREFIX, "type", "--screen"] and stdin == SECRET_TEXT.encode()
    assert "hunter2" not in (config.database_dir / "keeper-audit.log").read_text()


def test_in_browser_is_409(client, runner):
    _start(client)
    runner.answer = _RunOutcome(3, b"", b"in_browser\n", False)
    response = _send(client, {"action": CLICK, "screen": True})
    assert response.status_code == 409 and response.json() == {"detail": "in_browser"}


@pytest.mark.parametrize("body", [
    {"action": CLICK, "screen": True, "window": WINDOW},
    {"action": {"verb": "front"}, "window": WINDOW},
    {"action": {"verb": "front"}, "screen": True},
    {"action": {"verb": "open", "app": "files"}, "window": WINDOW},
    {"action": {"verb": "open", "app": "Files"}},
    {"action": {"verb": "open", "app": "../sh"}},
    {"action": {"verb": "open", "app": "a"}},
    {"action": {"verb": "open", "app": "x" * 70}},
    {"action": {"verb": "open"}},
    {"action": {"verb": "front", "x": 1}},
    {"action": {"verb": "browsers", "all": True}},
    {"action": CLICK, "screen": "yes"},
])
def test_bad_shapes_are_422(client, runner, body):
    _start(client)
    assert _send(client, body).status_code == 422
    assert runner.calls == []


def test_open_while_you_hold_control_is_refused(client, runner):
    _start(client)
    response = _send(client, {"action": {"verb": "open", "app": "terminal"}, "held": True})
    assert response.status_code == 409 and response.json() == {"detail": "held"}
    assert runner.calls == []


def test_front_never_wakes_a_sleeping_computer(client, runner):
    response = _send(client, {"action": {"verb": "front"}})
    assert response.status_code == 409 and response.json() == {"detail": "asleep"}
    assert runner.calls == []
