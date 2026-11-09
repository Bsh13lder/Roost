"""C3 Task 5: a Linux desk sends clicks, keys and typing to its computer's screen through the keeper.

The keeper's real app runs in-process through ``httpx.ASGITransport`` with fake docker and input runners.
Nothing here starts docker, xdotool or a real keeper."""

from __future__ import annotations

import uuid

import httpx
import pytest

from roost.config import RoostConfig
from roost.desk import DeskAsleep, DeskUnavailable, InputRefusedByComputer, ScreenInput
from roost.desk.client import KeeperDesk, input_body, input_timeout_s
from roost.desk.fake import FakeDesk
from roost.keeper.app import create_app as create_keeper
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
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], bytes | None]] = []
        self.answer = _RunOutcome(0, b"", b"", False)

    async def __call__(self, argv, stdin, timeout_s) -> _RunOutcome:
        self.calls.append((list(argv), stdin))
        return self.answer


@pytest.fixture
def config(tmp_path) -> RoostConfig:
    return RoostConfig(server_secret="x" * 32, database_dir=tmp_path / "data", desks_dir=tmp_path / "desks",
                       keeper_secret=_SECRET)


@pytest.fixture
def docker() -> DockerFake:
    return DockerFake()


@pytest.fixture
def runner() -> InputFake:
    return InputFake()


@pytest.fixture
def keeper_app(config, docker, runner):
    app = create_keeper(config)
    app.state.computers = ComputerManager(config, FakeNetworks(), runner=docker)
    app.state.room = ComputerRoom(app.state.computers, runner=docker)
    app.state.input_runner = runner
    return app


def _desk(config, keeper_app, computer="linux") -> KeeperDesk:
    return KeeperDesk(config, BOT, computer=computer, transport=httpx.ASGITransport(app=keeper_app))


WIN = (0, 0, 1280, 800)                          # the bot's window as the desk read it (CDP bounds)
CLICK = ScreenInput(window=WIN, verb="click", x=102, y=137)


def test_the_body_carries_only_the_verb_s_fields():
    assert input_body(CLICK, held=False) == {"action": {"verb": "click", "x": 102, "y": 137, "count": 1},
                                             "held": False,
                                             "window": {"left": 0, "top": 0, "width": 1280, "height": 800}}
    assert input_body(ScreenInput(window=WIN, verb="move", x=1, y=2), held=True)["action"] == {"verb": "move", "x": 1, "y": 2}
    assert input_body(ScreenInput(window=WIN, verb="key", key="Return"), held=False)["action"] == {"verb": "key", "key": "Return"}
    assert input_body(ScreenInput(window=WIN, verb="type", text="hi"), held=False)["action"] == {"verb": "type", "text": "hi"}
    assert input_body(ScreenInput(window=WIN, verb="scroll", x=3, y=4, notches=-2), held=False)["action"] == {
        "verb": "scroll", "x": 3, "y": 4, "notches": -2}


async def test_a_linux_desk_clicks_and_types_through_the_keeper(config, keeper_app, runner):
    await keeper_app.state.room.admit(BOT, frozenset())
    desk = _desk(config, keeper_app)
    await desk.send_input(CLICK)
    await desk.send_input(ScreenInput(window=WIN, verb="type", text=SECRET_TEXT))
    window = ["--window", "0", "0", "1280", "800"]
    assert [argv[7:] for argv, _ in runner.calls] == [["click", "102", "137", "1", *window], ["type", *window]]
    assert runner.calls[1][1] == SECRET_TEXT.encode()


async def test_mac_brave_desk_refuses_input(config, keeper_app, runner):
    desk = _desk(config, keeper_app, computer="mac_brave")
    with pytest.raises(DeskUnavailable):
        await desk.send_input(CLICK)
    assert runner.calls == []
    assert desk.page() is None


async def test_asleep_raises_desk_asleep_and_never_starts(config, keeper_app, docker, runner):
    desk = _desk(config, keeper_app)
    with pytest.raises(DeskAsleep):
        await desk.send_input(CLICK)
    assert keeper_app.state.computers.state(BOT) == "absent"
    await keeper_app.state.room.admit(BOT, frozenset())
    await keeper_app.state.computers.pause(BOT)
    docker.calls.clear()
    with pytest.raises(DeskAsleep):
        await desk.send_input(CLICK)
    assert not any(argv[1] in ("run", "start", "unpause") for argv in docker.calls)
    assert runner.calls == []


@pytest.mark.parametrize(("stderr", "word"), [(b"not_chromium\n", "not_chromium"), (b"outside\n", "outside")])
async def test_the_computer_s_refusals_are_input_refused(config, keeper_app, runner, stderr, word):
    await keeper_app.state.room.admit(BOT, frozenset())
    runner.answer = _RunOutcome(3, b"", stderr, False)
    with pytest.raises(InputRefusedByComputer) as caught:
        await _desk(config, keeper_app).send_input(CLICK)
    assert caught.value.word == word


async def test_held_is_input_refused(config, keeper_app, runner):
    await keeper_app.state.room.admit(BOT, frozenset())
    with pytest.raises(InputRefusedByComputer) as caught:
        await _desk(config, keeper_app).send_input(CLICK, held=True)
    assert caught.value.word == "held"
    assert runner.calls == []


async def test_a_failed_input_is_unavailable_and_never_carries_the_text(config, keeper_app, runner):
    await keeper_app.state.room.admit(BOT, frozenset())
    runner.answer = _RunOutcome(4, b"", b"input failed\n", False)
    with pytest.raises(DeskUnavailable) as caught:
        await _desk(config, keeper_app).send_input(ScreenInput(window=WIN, verb="type", text=SECRET_TEXT))
    assert "hunter2" not in str(caught.value)


async def test_a_refused_body_never_carries_the_text(config, keeper_app):
    await keeper_app.state.room.admit(BOT, frozenset())
    with pytest.raises(DeskUnavailable) as caught:
        await _desk(config, keeper_app).send_input(ScreenInput(window=WIN, verb="type", text=SECRET_TEXT + "\n"))
    assert "hunter2" not in str(caught.value)


async def test_an_unreachable_keeper_is_unavailable(config):
    def refuse(request):
        raise httpx.ConnectError("refused")

    desk = KeeperDesk(config, BOT, computer="linux", transport=httpx.MockTransport(refuse))
    with pytest.raises(DeskUnavailable):
        await desk.send_input(CLICK)


async def test_fake_desk_records_input_without_text():
    desk = FakeDesk(BOT, computer="linux")
    with pytest.raises(DeskAsleep):
        await desk.send_input(CLICK)
    await desk.start_browser()
    await desk.send_input(CLICK)
    await desk.send_input(ScreenInput(window=WIN, verb="type", text=SECRET_TEXT))
    await desk.send_input(ScreenInput(window=WIN, verb="key", key="Return"))
    assert desk.inputs == (("click", 102, 137), ("type", 0, 0), ("key", 0, 0))
    assert desk.typed_lengths == (len(SECRET_TEXT),)
    assert "hunter2" not in repr(vars(desk))
    assert desk.page() is None
    with pytest.raises(InputRefusedByComputer):
        await desk.send_input(CLICK, held=True)
    assert len(desk.inputs) == 3


async def test_fake_mac_brave_desk_refuses_input():
    desk = FakeDesk(BOT)
    await desk.start_browser()
    with pytest.raises(DeskUnavailable):
        await desk.send_input(CLICK)
    assert desk.inputs == ()


# -- security review (b) after Task 10 ------------------------------------------------------------------------


async def test_an_input_without_the_bot_s_window_is_never_sent(config, keeper_app, runner):
    await keeper_app.state.room.admit(BOT, frozenset())
    with pytest.raises(ValueError):
        await _desk(config, keeper_app).send_input(ScreenInput(verb="click", x=1, y=2))
    assert runner.calls == []
    fake = FakeDesk(BOT, computer="linux")
    await fake.start_browser()
    with pytest.raises(ValueError):
        await fake.send_input(ScreenInput(verb="click", x=1, y=2))
    assert fake.inputs == ()


async def test_the_window_rides_to_roost_input(config, keeper_app, runner):
    await keeper_app.state.room.admit(BOT, frozenset())
    await _desk(config, keeper_app).send_input(ScreenInput(window=(-40, 30, 800, 600), verb="key", key="Tab"))
    [(argv, _stdin)] = runner.calls
    assert argv[7:] == ["key", "Tab", "--window", "-40", "30", "800", "600"]


def test_the_desk_waits_longer_than_the_keeper_for_long_typing():
    from roost.computer_use.timing import desk_input_timeout_s, keeper_input_timeout_s

    assert desk_input_timeout_s(2000) > keeper_input_timeout_s(2000) > 2000 * 0.035
    assert input_timeout_s(ScreenInput(window=WIN, verb="type", text="x" * 2000)) == desk_input_timeout_s(2000)
    assert input_timeout_s(CLICK) >= desk_input_timeout_s(0)
