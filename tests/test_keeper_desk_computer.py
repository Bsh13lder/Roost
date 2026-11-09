"""The gateway's desk on a bot's Linux computer (Computers 2.0, C1, Task 7).

The keeper's real app runs in-process through ``httpx.ASGITransport`` with a fake docker runner; the CDP socket is
faked by ``connect_page``. Nothing here starts docker, Brave or a real keeper.
"""

from __future__ import annotations

import json
from dataclasses import replace
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from roost.config import RoostConfig, load_config
from roost.constants import COMPUTER_ROOM_POLL_S, COMPUTER_ROOM_WAIT_S, COMPUTERS_BUSY_TEXT
from roost.desk import DeskAsleep, DeskBusy, DeskFactory, DeskStatus, PageText
from roost.desk.client import KeeperDesk
from roost.desk.fake import FakeDesk
from roost.keeper.browsers import BraveLauncher
from roost.desk.stuck import detect_block
from roost.gateway.app import create_app as create_gateway
from roost.gateway.auth import register_user
from roost.keeper.app import create_app as create_keeper
from roost.keeper.computer_room import ComputerRoom
from roost.keeper.computers import ComputerManager
from roost.keeper.workspaces import _RunOutcome

_SECRET = "k" * 32
BOT = str(uuid.uuid4())
OTHER = str(uuid.uuid4())
WAITING_LINE = "Waiting for a free computer"


class DockerFake:
    """Answers every docker call, boots at once, reports plenty of memory."""

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


class RecordingPage:
    def __init__(self, page: PageText) -> None:
        self.page = page
        self.closed = False

    async def open_page(self, url: str, *, reuse_tab: bool = False) -> PageText:
        self.reuse_tab = reuse_tab
        return self.page

    async def read_page(self) -> PageText:
        return self.page

    async def current_url(self) -> str:
        return self.page.url

    async def close(self) -> None:
        self.closed = True


class Connector:
    """A ``connect_page`` that records where the desk connected."""

    def __init__(self, page: PageText | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.page = page or PageText(url="https://example.com/", title="Example", text="hello", truncated=False)

    async def __call__(self, relay_url: str, token: str) -> RecordingPage:
        self.calls.append((relay_url, token))
        return RecordingPage(self.page)


class _FakeSpawner:
    """Stands in for ``os.posix_spawn`` so no real Brave window opens."""

    def __init__(self) -> None:
        self._next_pid = 5000

    def __call__(self, path, argv, env, *, file_actions):
        self._next_pid += 1
        return self._next_pid


@pytest.fixture
def config(tmp_path) -> RoostConfig:
    return RoostConfig(server_secret="x" * 32, database_dir=tmp_path / "data", desks_dir=tmp_path / "desks",
                       keeper_secret=_SECRET)


@pytest.fixture
def docker() -> DockerFake:
    return DockerFake()


@pytest.fixture
def keeper_app(config, docker):
    app = create_keeper(config)
    app.state.launcher = BraveLauncher(config, spawner=_FakeSpawner())  # never the real Brave app
    app.state.computers = ComputerManager(config, FakeNetworks(), runner=docker)
    app.state.room = ComputerRoom(app.state.computers, runner=docker)
    return app


@pytest.fixture
def transport(keeper_app) -> httpx.ASGITransport:
    return httpx.ASGITransport(app=keeper_app)


def _linux(config, transport, **kwargs) -> KeeperDesk:
    return KeeperDesk(config, BOT, computer="linux", transport=transport, **kwargs)


async def test_a_linux_bot_opens_pages_through_the_computer_relay(config, transport, keeper_app):
    connector = Connector()
    desk = _linux(config, transport, connect_page=connector)

    page = await desk.open_page("https://example.com/")

    assert page.title == "Example"
    url, token = connector.calls[0]
    assert url.endswith(f"/desks/{BOT}/computer/cdp")
    assert token == keeper_app.state.computers.handle(BOT).cdp_token


async def test_read_page_and_the_stuck_detector_run_unchanged_on_the_computer(config, transport):
    wall = PageText(url="https://shop.example/login", title="Sign in", text="Sign in", truncated=False,
                    status=200, password_field=True)
    desk = _linux(config, transport, connect_page=Connector(wall))

    page = await desk.read_page()

    assert page == wall
    assert detect_block(page) is not None


async def test_a_screenshot_never_wakes_a_paused_computer(config, transport, keeper_app, docker):
    desk = _linux(config, transport, connect_page=Connector())
    with pytest.raises(DeskAsleep):
        await desk.screenshot()                      # never started: asleep
    assert keeper_app.state.computers.state(BOT) == "absent"
    assert not any(argv[1] in ("run", "start", "unpause") for argv in docker.calls)

    await keeper_app.state.room.admit(BOT, frozenset())
    await keeper_app.state.computers.pause(BOT)
    docker.calls.clear()
    with pytest.raises(DeskAsleep):
        await desk.screenshot()                      # paused: still asleep
    assert keeper_app.state.computers.state(BOT) == "paused"
    assert not any(argv[1] in ("start", "unpause", "run") for argv in docker.calls)


def _room_transport(no_room_times: int, bodies: list[dict]):
    """A keeper that says no_room ``no_room_times`` times, then starts the computer."""
    left = {"n": no_room_times}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/computer/start"):
            bodies.append(json.loads(request.content or b"{}"))
            if left["n"] > 0:
                left["n"] -= 1
                return httpx.Response(409, json={"detail": "no_room"})
            return httpx.Response(200, json={"computer": "running", "cdp_token": "c" * 20, "vnc_token": "v" * 20})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def test_waits_for_a_free_computer_then_says_so(config):
    bodies: list[dict] = []
    slept: list[float] = []
    waits: list[int] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    async def on_wait() -> None:
        waits.append(1)

    desk = KeeperDesk(config, BOT, computer="linux", transport=_room_transport(2, bodies), connect_page=Connector(),
                      busy=lambda: frozenset({OTHER}), on_wait=on_wait, sleep=sleep)

    page = await desk.open_page("https://example.com/")

    assert page.title == "Example"
    assert slept == [COMPUTER_ROOM_POLL_S, COMPUTER_ROOM_POLL_S]
    assert waits == [1]                                # the line is said once, not on every poll
    assert all(body == {"busy": [OTHER]} for body in bodies) and len(bodies) == 3


async def test_gives_up_with_desk_busy_after_the_bounded_wait(config):
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    desk = KeeperDesk(config, BOT, computer="linux", transport=_room_transport(10_000, []), connect_page=Connector(),
                      sleep=sleep)

    with pytest.raises(DeskBusy):
        await desk.start_browser()

    assert sum(slept) == COMPUTER_ROOM_WAIT_S


async def test_wake_if_room_never_waits(config):
    slept: list[float] = []
    waits: list[int] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    async def on_wait() -> None:
        waits.append(1)

    bodies: list[dict] = []
    busy = KeeperDesk(config, BOT, computer="linux", transport=_room_transport(1, bodies), connect_page=Connector(),
                      busy=lambda: frozenset({OTHER}), on_wait=on_wait, sleep=sleep)
    assert await busy.wake_if_room() is False
    assert await busy.wake_if_room() is True          # the keeper had room the second time
    assert slept == [] and waits == [] and bodies == [{"busy": [OTHER]}, {"busy": [OTHER]}]
    mac = KeeperDesk(config, BOT, transport=_room_transport(10, []), connect_page=Connector())
    assert await mac.wake_if_room() is True


def test_the_busy_text_is_plain():
    assert COMPUTERS_BUSY_TEXT == "All computers are busy right now. Try again in a few minutes."


async def test_a_mac_brave_bot_still_uses_brave_routes(config, transport, keeper_app):
    connector = Connector()
    desk = KeeperDesk(config, BOT, transport=transport, connect_page=connector)

    await desk.open_page("https://example.com/")

    assert connector.calls[0][0].endswith(f"/desks/{BOT}/cdp")
    assert keeper_app.state.computers.state(BOT) == "absent"


@pytest.mark.parametrize(("state", "browser"), [("running", "running"), ("paused", "stopped"),
                                                ("stopped", "stopped"), ("absent", "stopped")])
async def test_status_says_paused_is_asleep(config, state, browser):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"browser": "stopped", "workspace": "absent", "computer": state})

    desk = KeeperDesk(config, BOT, computer="linux", transport=httpx.MockTransport(handler))

    assert await desk.status() == DeskStatus(browser=browser, workspace="absent", computer="linux", state=state)


async def test_stop_browser_stops_the_computer_and_closes_the_page(config, transport, keeper_app):
    connector = Connector()
    desk = _linux(config, transport, connect_page=connector)
    await desk.open_page("https://example.com/")

    status = await desk.stop_browser()

    assert status.state == "stopped" and status.browser == "stopped"
    assert keeper_app.state.computers.state(BOT) == "stopped"


# -- the factory, the routes and the runner ---------------------------------------------------------------


def test_the_factory_keeps_one_desk_per_bot_and_kind(config):
    desks = DeskFactory(replace(config, desk_mode="fake"))
    linux, mac = desks.for_bot(BOT, "linux"), desks.for_bot(BOT, "mac_brave")
    assert linux is not mac and linux is desks.for_bot(BOT, "linux")
    assert isinstance(linux, FakeDesk) and linux.computer == "linux" and mac.computer == "mac_brave"
    desks.forget(BOT)
    assert desks.for_bot(BOT, "linux") is not linux and desks.for_bot(BOT, "mac_brave") is not mac


O = {"Origin": "http://127.0.0.1:18800"}
AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}


def _signed_in(client: TestClient, name: str = "alice") -> TestClient:
    client.post("/api/auth/register", json={"username": name, "password": "pw-123456"}, headers=O)
    return client


def _new_bot(client: TestClient, computer: str = "linux") -> str:
    made = client.post("/api/bots", json={"name": "Scout", "job": "read", "instructions": "", "avatar": AVATAR},
                       headers=O).json()["id"]
    assert client.patch(f"/api/bots/{made}", json={"computer": computer}, headers=O).status_code == 200
    return made


def test_the_desk_route_reports_the_computer_and_its_state():
    c = _signed_in(TestClient(create_gateway()))
    bot_id = _new_bot(c)
    body = c.get(f"/api/bots/{bot_id}/desk").json()
    assert body == {"browser": "stopped", "workspace": "absent", "computer": "linux", "state": "stopped"}
    c.post(f"/api/bots/{bot_id}/desk/browser/start", headers=O)
    assert c.get(f"/api/bots/{bot_id}/desk").json()["browser"] == "running"
    assert c.app.state.desks.for_bot(bot_id, "linux").browser_state == "running"
    assert c.app.state.desks.for_bot(bot_id, "mac_brave").browser_state == "stopped"


def test_a_busy_room_is_a_409_with_a_plain_sentence():
    c = _signed_in(TestClient(create_gateway()))
    bot_id = _new_bot(c)
    c.app.state.desks.for_bot(bot_id, "linux").force_busy = True
    r = c.post(f"/api/bots/{bot_id}/desk/browser/start", headers=O)
    assert (r.status_code, r.json()["detail"]) == (409, COMPUTERS_BUSY_TEXT)


def test_retire_removes_both_kinds():
    c = _signed_in(TestClient(create_gateway()))
    c.post("/api/bots", json={"name": "Main", "job": "j", "instructions": "", "avatar": AVATAR}, headers=O)
    bot_id = _new_bot(c)
    linux, mac = c.app.state.desks.for_bot(bot_id, "linux"), c.app.state.desks.for_bot(bot_id, "mac_brave")
    assert c.delete(f"/api/bots/{bot_id}", headers=O).status_code in (200, 204)
    assert linux.retired and mac.retired
    assert c.app.state.desks.for_bot(bot_id, "linux") is not linux


async def test_another_users_bot_desk_is_404():
    app = create_gateway()
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    made = (await alice.post("/api/bots", json={"name": "Scout", "job": "r", "instructions": "", "avatar": AVATAR},
                             headers=O)).json()["id"]
    await alice.patch(f"/api/bots/{made}", json={"computer": "linux"}, headers=O)
    bob = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    cfg = load_config()
    await register_user(cfg, "bob", "pw-123456")
    await bob.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"}, headers=O)
    assert (await bob.get(f"/api/bots/{made}/desk")).status_code == 404
    assert (await bob.post(f"/api/bots/{made}/desk/browser/start", headers=O)).status_code == 404
    assert (await bob.get(f"/api/bots/{made}/desk/screenshot")).status_code == 404


async def test_desk_busy_becomes_a_plain_tool_result():
    from roost.db.connection import init_db
    from roost.gateway.auth import register_user
    from roost.llm.types import ToolCallRequested, TurnDone
    from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle

    cfg = load_config()
    await init_db(cfg)
    user_id = (await register_user(cfg, "alice", "pw-123456")).id
    bot = await make_bot(cfg, user_id, "Helper")
    call = [ToolCallRequested(id="p", name="open_page", arguments={"url": "https://example.com"}), TurnDone("tool_use")]
    rig = make_rig(cfg, team_model({"Helper": [call, say("ok")]}))
    rig.desks.for_bot(bot.id, bot.computer).force_busy = True
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "read it")
    await wait_idle(rig.runner, timeout=8)
    assert [t.text for t in rig.model.requests[-1].turns if t.role == "tool"] == [COMPUTERS_BUSY_TEXT]


async def test_the_runner_names_the_busy_bots_and_says_it_is_waiting():
    from roost.db.connection import init_db
    from roost.gateway.auth import register_user
    from team_helpers import make_bot, make_rig, team_model

    cfg = load_config()
    await init_db(cfg)
    user_id = (await register_user(cfg, "alice", "pw-123456")).id
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({}))
    assert rig.runner.busy_ids() == frozenset()
    await rig.desks.room_hooks.on_wait(bot.id)              # no run yet: nobody to tell
    assert rig.runner._activity.get(bot.id) is None
    rig.runner.note_run_user(user_id, bot.id)
    await rig.desks.room_hooks.on_wait(bot.id)
    assert rig.runner._activity.get(bot.id) == WAITING_LINE


# -- the screen stream (Task 8) -----------------------------------------------------------------------------


class FakeSocket:
    """A websockets client stand-in: what was sent, and what the far end says next."""

    def __init__(self, incoming: list) -> None:
        self.sent: list = []
        self.closed = False
        self._incoming = list(incoming)

    async def send(self, data) -> None:
        self.sent.append(data)

    async def recv(self):
        if not self._incoming:
            import websockets
            raise websockets.ConnectionClosedOK(None, None)
        return self._incoming.pop(0)

    async def close(self) -> None:
        self.closed = True


async def test_the_computer_screen_attaches_then_connects_with_the_vnc_token(config, transport, keeper_app):
    await keeper_app.state.room.admit(BOT, frozenset())
    opened: list[tuple[str, dict]] = []
    sock = FakeSocket([b"RFB 003.008\n", b"frame"])

    async def connect(url: str, headers: dict):
        opened.append((url, headers))
        return sock

    desk = _linux(config, transport, connect_screen=connect)
    screen = await desk.open_screen()

    url, headers = opened[0]
    assert url.endswith(f"/desks/{BOT}/computer/vnc")
    assert set(headers) == {"X-Roost-Desk-Token"}                      # a one-time ticket, not the stored token
    assert headers["X-Roost-Desk-Token"] != keeper_app.state.computers.handle(BOT).vnc_token
    ticket = headers["X-Roost-Desk-Token"]
    assert keeper_app.state.computers.consume_vnc_ticket(BOT, ticket)          # live once...
    assert not keeper_app.state.computers.consume_vnc_ticket(BOT, ticket)      # ...and never again
    assert await screen.receive() == b"RFB 003.008\n"
    await screen.send(b"abc")
    assert sock.sent == [b"abc"]
    assert await screen.receive() == b"frame"
    assert await screen.receive() == b""             # the far end closed
    await screen.close()
    assert sock.closed


async def test_the_computer_screen_never_wakes_a_sleeping_computer(config, transport, keeper_app, docker):
    desk = _linux(config, transport)
    with pytest.raises(DeskAsleep):
        await desk.open_screen()
    assert not any(argv[1] in ("run", "start", "unpause") for argv in docker.calls)


async def test_a_mac_brave_desk_has_no_screen(config, transport):
    from roost.desk import DeskUnavailable
    with pytest.raises(DeskUnavailable):
        await KeeperDesk(config, BOT, transport=transport).open_screen()


async def test_a_screen_that_cannot_connect_is_unavailable(config, transport, keeper_app):
    from roost.desk import DeskUnavailable
    await keeper_app.state.room.admit(BOT, frozenset())

    async def connect(url: str, headers: dict):
        raise OSError("refused")

    with pytest.raises(DeskUnavailable):
        await _linux(config, transport, connect_screen=connect).open_screen()


def test_the_vnc_url_is_the_computer_vnc_route():
    from roost.desk.client import _vnc_url
    assert _vnc_url("http://127.0.0.1:18801", BOT) == f"ws://127.0.0.1:18801/desks/{BOT}/computer/vnc"
    assert _vnc_url("https://k.test", BOT) == f"wss://k.test/desks/{BOT}/computer/vnc"


async def test_current_url_never_wakes_the_computer(config, transport, keeper_app, docker):
    desk = _linux(config, transport, connect_page=Connector())
    assert await desk.current_url() == ""                          # never started: asleep, no URL
    assert keeper_app.state.computers.state(BOT) == "absent"
    assert not any(argv[1] in ("run", "start", "unpause") for argv in docker.calls)

    await keeper_app.state.room.admit(BOT, frozenset())
    await keeper_app.state.computers.pause(BOT)
    docker.calls.clear()
    assert await desk.current_url() == ""                          # paused: still asleep
    assert not any(argv[1] in ("start", "unpause", "run") for argv in docker.calls)


async def test_current_url_reads_the_page_of_a_running_computer(config, transport, keeper_app):
    await keeper_app.state.room.admit(BOT, frozenset())
    desk = _linux(config, transport, connect_page=Connector())
    assert await desk.current_url() == "https://example.com/"


async def test_a_page_call_wakes_a_paused_computer_on_a_fresh_connection(config, transport, keeper_app, docker):
    """Owner, 2026-11-04: Gela's routine found its computer asleep, sent CDP to the frozen container on the cached
    connection, and read the timeouts as a crashed WhatsApp tab. A page call wakes it first and connects afresh."""
    connector = Connector()
    desk = _linux(config, transport, connect_page=connector, wake_check_after_s=0.0)
    await desk.open_page("https://example.com/")
    first = desk._page
    await keeper_app.state.computers.pause(BOT)
    docker.calls.clear()

    await desk.open_page("https://web.whatsapp.com/")

    assert any(argv[1] == "unpause" for argv in docker.calls)
    assert first.closed and desk._page is not first
    assert len(connector.calls) == 2


async def test_a_page_call_on_a_running_computer_keeps_its_connection(config, transport, keeper_app, docker):
    connector = Connector()
    desk = _linux(config, transport, connect_page=connector, wake_check_after_s=0.0)
    await desk.open_page("https://example.com/")
    docker.calls.clear()

    await desk.read_page()

    assert not any(argv[1] in ("start", "unpause", "run") for argv in docker.calls)
    assert len(connector.calls) == 1 and not desk._page.closed
