"""Tests for ``roost.desk.client`` — the gateway-side ``KeeperClient``
(signed HTTP calls to the keeper) and ``KeeperDesk`` (the real ``Desk``
built on top of it).

Runs the keeper's *actual* FastAPI app in-process via
``httpx.ASGITransport`` (the same "run the real app, fake only the
process boundary" style ``tests/test_bots_api.py`` uses for the gateway)
with a fake docker runner and a fake Brave spawner — never a real
keeper process, a real Brave window, or a real container.
"""

from __future__ import annotations

import httpx
import pytest

from roost.config import RoostConfig
from roost.constants import EXEC_TIMEOUT_S, KEEPER_RETIRE_REQUEST_TIMEOUT_S
from roost.desk import DeskStatus, DeskUnavailable, ExecResult, PageText
from roost.desk.cdp import CdpClientError, CdpReplyError
from roost.desk.client import KeeperClient, KeeperDesk, _connect_page, _relay_url
from roost.desk.url_policy import UrlBlocked
from roost.keeper.app import create_app
from roost.keeper.browsers import BraveLauncher
from roost.keeper.computers import ComputerManager
from roost.keeper.networks import EgressNetworks
from roost.keeper.main_browser import MainBrowserOpener
from roost.keeper.workspaces import WorkspaceManager, _RunOutcome

_BOT_ID = "77777777-7777-4777-8777-777777777777"
_SECRET = "k" * 32


class _FakeSpawner:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self._next_pid = 5000

    def __call__(self, path, argv, env, *, file_actions):
        self.calls.append((path, list(argv)))
        pid = self._next_pid
        self._next_pid += 1
        return pid


class _FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], float]] = []
        self._default = _RunOutcome(returncode=0, stdout=b"hi\n", stderr=b"", timed_out=False)

    async def __call__(self, argv, timeout_s):
        self.calls.append((list(argv), timeout_s))
        if argv[:2] == ["docker", "top"]:
            return _RunOutcome(returncode=0, stdout=b"PID COMMAND\n1 sleep infinity", stderr=b"", timed_out=False)
        if argv[:3] == ["docker", "exec", "--user"] and "kill" in argv:
            return _RunOutcome(returncode=1, stdout=b"", stderr=b"", timed_out=False)
        return self._default


async def _no_docker(argv, timeout_s):
    return _RunOutcome(returncode=0, stdout=b"", stderr=b"", timed_out=False)


def _offline_computers(config):
    """A ComputerManager whose docker calls all succeed and run nothing."""
    return ComputerManager(config, EgressNetworks(runner=_no_docker), runner=_no_docker)


@pytest.fixture
def config(tmp_path) -> RoostConfig:
    return RoostConfig(
        server_secret="x" * 32,
        database_dir=tmp_path / "data",
        desks_dir=tmp_path / "desks",
        keeper_secret=_SECRET,
    )


@pytest.fixture
def runner() -> _FakeRunner:
    return _FakeRunner()


@pytest.fixture
def keeper_app(config: RoostConfig, runner: _FakeRunner):
    app = create_app(config)
    app.state.workspaces = WorkspaceManager(config, runner=runner)
    app.state.computers = _offline_computers(config)
    app.state.launcher = BraveLauncher(config, spawner=_FakeSpawner())
    return app


@pytest.fixture
def transport(keeper_app) -> httpx.ASGITransport:
    return httpx.ASGITransport(app=keeper_app)


# -- KeeperClient ----------------------------------------------------------


async def test_get_desk_reports_initial_state(config: RoostConfig, transport: httpx.ASGITransport) -> None:
    client = KeeperClient(config, transport=transport)
    result = await client.get_desk(_BOT_ID)
    assert result == {"browser": "stopped", "workspace": "absent", "computer": "absent"}


async def test_start_browser_returns_a_cdp_token(config: RoostConfig, transport: httpx.ASGITransport) -> None:
    client = KeeperClient(config, transport=transport)
    result = await client.start_browser(_BOT_ID)
    assert result["browser"] == "running"
    assert isinstance(result["cdp_token"], str) and len(result["cdp_token"]) > 10


async def test_exec_workspace_sends_argv_and_timeout(
    config: RoostConfig, transport: httpx.ASGITransport, runner: _FakeRunner
) -> None:
    client = KeeperClient(config, transport=transport)
    await client.start_workspace(_BOT_ID)
    result = await client.exec_workspace(_BOT_ID, ["/bin/sh", "-c", "echo hi"], 120)
    assert result == {"exit_code": 0, "stdout": "hi\n", "stderr": "", "timed_out": False, "truncated": False}

    exec_call = next(c for c in runner.calls if c[0][-3:] == ["/bin/sh", "-c", "echo hi"])
    assert exec_call[1] == 120.0


async def test_desk_unavailable_when_keeper_is_unreachable(tmp_path) -> None:
    config = RoostConfig(
        server_secret="x" * 32,
        database_dir=tmp_path / "data",
        desks_dir=tmp_path / "desks",
        keeper_secret=_SECRET,
        keeper_url="http://127.0.0.1:1",
    )
    client = KeeperClient(config)  # real transport -- nothing listens on port 1
    with pytest.raises(DeskUnavailable):
        await client.get_desk(_BOT_ID)


def test_relay_url_converts_http_to_ws() -> None:
    assert _relay_url("http://127.0.0.1:18801", _BOT_ID) == f"ws://127.0.0.1:18801/desks/{_BOT_ID}/cdp"


def test_relay_url_converts_https_to_wss() -> None:
    assert _relay_url("https://example.test", _BOT_ID) == f"wss://example.test/desks/{_BOT_ID}/cdp"


# -- KeeperDesk --------------------------------------------------------------


async def test_keeper_desk_status_round_trip(config: RoostConfig, transport: httpx.ASGITransport) -> None:
    desk = KeeperDesk(config, _BOT_ID, transport=transport)
    assert await desk.status() == DeskStatus(browser="stopped", workspace="absent")


async def test_keeper_desk_start_and_stop_browser(config: RoostConfig, transport: httpx.ASGITransport) -> None:
    desk = KeeperDesk(config, _BOT_ID, transport=transport)
    started = await desk.start_browser()
    assert started == DeskStatus(browser="running", workspace="absent")

    stopped = await desk.stop_browser()
    assert stopped == DeskStatus(browser="stopped", workspace="absent")


async def test_keeper_desk_exec_auto_starts_the_workspace_and_builds_shell_argv(
    config: RoostConfig, transport: httpx.ASGITransport, runner: _FakeRunner
) -> None:
    desk = KeeperDesk(config, _BOT_ID, transport=transport)

    result = await desk.exec("echo hi")

    assert result == ExecResult(exit_code=0, stdout="hi\n", stderr="", timed_out=False, truncated=False)
    # The very first docker call must be the workspace's own `docker run`
    # (auto-started), with the exec call -- carrying the fixed
    # ["/bin/sh", "-c", command] shape, never a raw/split argv -- after it.
    assert runner.calls[0][0][:3] == ["docker", "run", "-d"]
    exec_call = next(c for c in runner.calls if c[0][-3:] == ["/bin/sh", "-c", "echo hi"])
    assert exec_call[1] == 120.0


async def test_keeper_desk_exec_passes_a_shorter_timeout_and_caps_a_longer_one(
    config: RoostConfig, transport: httpx.ASGITransport, runner: _FakeRunner
) -> None:
    """Programs: run_program's own timeout reaches the keeper, never past EXEC_TIMEOUT_S."""
    desk = KeeperDesk(config, _BOT_ID, transport=transport)
    await desk.exec("echo short", timeout_s=7)
    await desk.exec("echo long", timeout_s=999)
    timeouts = {c[0][-1]: c[1] for c in runner.calls if c[0][-3:-1] == ["/bin/sh", "-c"]}
    assert timeouts == {"echo short": 7.0, "echo long": 120.0}


async def test_keeper_desk_retire_calls_the_keeper_and_clears_the_browser_page(
    config: RoostConfig, transport: httpx.ASGITransport
) -> None:
    desk = KeeperDesk(config, _BOT_ID, transport=transport)
    await desk.retire()
    # Retiring a never-started desk still succeeds (mirrors the keeper's
    # own idempotent DELETE route) and must not raise.


async def test_retire_closes_an_open_page(config: RoostConfig, transport: httpx.ASGITransport) -> None:
    """Mirrors ``stop_browser``'s own page-closing behavior (the test
    right below this one): retire must not abandon an open CDP
    connection -- real-desk smoke (Task 13) found this while chasing an
    intermittent retire slowdown, and it's the same class of bug
    ``test_stop_browser_closes_an_open_page`` already guards against for
    the other browser-stopping path."""
    page = _WorksPage()
    desk = KeeperDesk(config, _BOT_ID, transport=transport, connect_page=_sequential_page_factory([page]))
    await desk.open_page("https://example.com/")

    await desk.retire()

    assert page.closed is True


# -- Fix round 1, finding 6: keeper HTTP errors and relay-connect failures --


async def test_keeper_http_error_response_becomes_desk_unavailable(tmp_path) -> None:
    # Before this fix, a non-2xx keeper response (Docker not running,
    # Brave failed to launch, a secret mismatch, ...) raised a raw
    # httpx.HTTPStatusError that the gateway route's `except
    # DeskUnavailable` was never written to catch -- a bare 500 instead
    # of the clean 503 the contract defines for "can't use the desk
    # right now".
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="failed to start the bot's workspace")

    config = RoostConfig(
        server_secret="x" * 32,
        database_dir=tmp_path / "data",
        desks_dir=tmp_path / "desks",
        keeper_secret=_SECRET,
    )
    client = KeeperClient(config, transport=httpx.MockTransport(handler))
    with pytest.raises(DeskUnavailable):
        await client.get_desk(_BOT_ID)


async def test_connect_page_wraps_a_refused_relay_connection_as_desk_unavailable() -> None:
    # Nothing listens on port 1 -- the same "deliberately unreachable"
    # port test_desk_unavailable_when_keeper_is_unreachable (above) uses
    # for the HTTP side. websockets.connect raises a raw OSError here;
    # before this fix that propagated straight out of
    # KeeperDesk._ensure_page, past the route's `except
    # DeskUnavailable`.
    with pytest.raises(DeskUnavailable):
        await _connect_page("ws://127.0.0.1:1/desks/x/cdp", "token")


# -- Fix round 1, finding 5: exec needs a longer HTTP timeout than control calls --


async def test_exec_workspace_uses_a_longer_timeout_than_control_calls(
    config: RoostConfig, transport: httpx.ASGITransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_timeouts: list[float] = []
    real_async_client = httpx.AsyncClient

    class _RecordingAsyncClient(real_async_client):  # type: ignore[misc]
        def __init__(self, *args, **kwargs) -> None:
            captured_timeouts.append(kwargs.get("timeout"))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)

    client = KeeperClient(config, transport=transport)
    await client.start_workspace(_BOT_ID)  # a control call -- the short timeout
    await client.exec_workspace(_BOT_ID, ["/bin/sh", "-c", "echo hi"], 120)  # needs real headroom

    assert captured_timeouts[0] <= EXEC_TIMEOUT_S
    assert captured_timeouts[-1] > EXEC_TIMEOUT_S


# -- Real-desk smoke (Task 13): retire needs a longer timeout too --
#
# DELETE /desks/{bot_id} runs BraveLauncher.stop() (SIGTERM, up to a few
# seconds' grace, then SIGKILL) and a `docker rm -f` sequentially; their
# combined worst case can land close to an ordinary control-call
# timeout, making a retire that's about to finish on time look exactly
# like a dead keeper -- the same class of bug the exec timeout above
# already fixes once, for a different route.


async def test_retire_uses_a_longer_timeout_than_control_calls(
    config: RoostConfig, transport: httpx.ASGITransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_timeouts: list[float] = []
    real_async_client = httpx.AsyncClient

    class _RecordingAsyncClient(real_async_client):  # type: ignore[misc]
        def __init__(self, *args, **kwargs) -> None:
            captured_timeouts.append(kwargs.get("timeout"))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)

    client = KeeperClient(config, transport=transport)
    await client.get_desk(_BOT_ID)  # a control call -- the short timeout
    await client.retire(_BOT_ID)  # needs real headroom

    assert captured_timeouts[0] <= EXEC_TIMEOUT_S
    assert captured_timeouts[-1] == KEEPER_RETIRE_REQUEST_TIMEOUT_S


# -- Fix round 1, finding 4: a dead page gets dropped and replaced, not reused forever --


class _AlwaysFailsPage:
    """A fake ``DeskBrowserPage`` whose connection is already dead --
    every call raises, as a real one would after an oversized reply, a
    keeper restart, a Brave crash, or a 4409 takeover."""

    def __init__(self) -> None:
        self.closed = False

    async def open_page(self, url: str) -> PageText:
        raise CdpClientError("simulated dead connection")

    async def read_page(self) -> PageText:
        raise CdpClientError("simulated dead connection")

    async def close(self) -> None:
        self.closed = True


class _WorksPage:
    """A fake ``DeskBrowserPage`` that just works."""

    def __init__(self) -> None:
        self.calls = 0
        self.closed = False

    async def open_page(self, url: str) -> PageText:
        self.calls += 1
        return PageText(url=url, title="ok", text="ok", truncated=False)

    async def read_page(self) -> PageText:
        self.calls += 1
        return PageText(url="about:blank", title="ok", text="ok", truncated=False)

    async def close(self) -> None:
        self.closed = True

    def forget_session(self) -> None:
        return None                       # a closed tab: the next call attaches the tab in front again


def _sequential_page_factory(pages: list):
    """A ``connect_page`` double that hands out ``pages`` in order, one
    per call -- standing in for a fresh real connection each time
    ``KeeperDesk`` reconnects."""
    remaining = iter(pages)

    async def factory(relay_url: str, token: str):
        return next(remaining)

    return factory


async def test_keeper_desk_replaces_a_dead_page_and_retries_once(
    config: RoostConfig, transport: httpx.ASGITransport
) -> None:
    dead = _AlwaysFailsPage()
    works = _WorksPage()
    desk = KeeperDesk(config, _BOT_ID, transport=transport, connect_page=_sequential_page_factory([dead, works]))

    result = await desk.open_page("https://example.com/")

    assert result.url == "https://example.com/"
    assert dead.closed is True
    assert works.calls == 1


async def test_keeper_desk_reuses_the_same_page_across_calls(
    config: RoostConfig, transport: httpx.ASGITransport
) -> None:
    works = _WorksPage()
    desk = KeeperDesk(config, _BOT_ID, transport=transport, connect_page=_sequential_page_factory([works]))

    await desk.open_page("https://example.com/")
    await desk.read_page()

    # Only one page was ever built -- the factory above has exactly one
    # entry, so a second call to it would raise StopIteration.
    assert works.calls == 2


async def test_stop_browser_closes_an_open_page(config: RoostConfig, transport: httpx.ASGITransport) -> None:
    first = _WorksPage()
    second = _WorksPage()
    desk = KeeperDesk(config, _BOT_ID, transport=transport, connect_page=_sequential_page_factory([first, second]))
    await desk.open_page("https://example.com/")

    await desk.stop_browser()

    assert first.closed is True

    # The next open_page must build a brand new page (the factory's
    # second entry), not reuse the one browser/stop just invalidated
    # server-side.
    await desk.open_page("https://example.com/")
    assert second.calls == 1


async def test_page_calls_after_retire_raise_desk_unavailable(
    config: RoostConfig, transport: httpx.ASGITransport,
) -> None:
    """Final review, finding 5: if a turn is still in flight when the
    bot is retired, its next open_page/read_page must not relaunch
    Brave (and recreate the desk directory retire just removed) for a
    bot that's already gone -- this instance-level flag is the last
    line of defense, independent of whether TurnRunner cancelled the
    turn in time."""
    desk = KeeperDesk(config, _BOT_ID, transport=transport)
    await desk.retire()

    with pytest.raises(DeskUnavailable):
        await desk.open_page("https://example.com/")
    with pytest.raises(DeskUnavailable):
        await desk.read_page()


async def test_keeper_desk_raises_desk_unavailable_when_every_page_is_dead(
    config: RoostConfig, transport: httpx.ASGITransport
) -> None:
    desk = KeeperDesk(
        config, _BOT_ID, transport=transport, connect_page=_sequential_page_factory([_AlwaysFailsPage(), _AlwaysFailsPage()])
    )

    with pytest.raises(DeskUnavailable):
        await desk.read_page()


_ATTACH = f"/desks/{_BOT_ID}/browser/attach"
_START = f"/desks/{_BOT_ID}/browser/start"


class _ShotPage:
    """A connected page whose capture works until ``alive`` is switched off."""

    def __init__(self) -> None:
        self.alive = True

    async def capture_screenshot(self) -> bytes:
        if not self.alive:
            import websockets
            raise websockets.ConnectionClosed(None, None)
        return b"\xff\xd8jpeg"

    async def close(self) -> None:
        return None


class _ReplyErrorPage:
    """A connected page whose capture fails with a CDP-level error reply
    (e.g. "Session with given id not found") while the socket itself is
    still fine -- unlike ``_ShotPage``, which simulates the socket dying.
    Also answers ``open_page``, so a test can prove the bot's own tab
    survives a screenshot's error reply (S1.8 Fix round 1, finding 1)."""

    def __init__(self) -> None:
        self.closed = False
        self.open_page_calls: list[str] = []

    async def capture_screenshot(self) -> bytes:
        raise CdpReplyError("CDP error replying to 'Page.captureScreenshot': Session with given id not found")

    async def open_page(self, url: str) -> PageText:
        self.open_page_calls.append(url)
        return PageText(url=url, title="ok", text="ok", truncated=False)

    async def close(self) -> None:
        self.closed = True


async def test_screenshot_of_a_sleeping_computer_never_starts_its_browser(config):
    from roost.desk import DeskAsleep
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(409, json={"detail": "asleep"})

    desk = KeeperDesk(config, _BOT_ID, transport=httpx.MockTransport(handler))
    with pytest.raises(DeskAsleep):
        await desk.screenshot()
    assert seen == [("POST", _ATTACH)]


async def test_screenshot_of_a_running_computer_is_its_pages_jpeg(config):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == _ATTACH
        return httpx.Response(200, json={"browser": "running", "cdp_token": "tok"})

    async def connect(url: str, token: str):
        assert token == "tok"
        return _ShotPage()

    desk = KeeperDesk(config, _BOT_ID, transport=httpx.MockTransport(handler), connect_page=connect)
    assert await desk.screenshot() == b"\xff\xd8jpeg"


async def test_a_dead_connection_during_a_screenshot_never_starts_the_browser(config):
    """'Close window' while a capture is in flight: the connection dies and the browser is gone.
    The view answers 503, then 'asleep'. It never retries through _ensure_page, which would start Brave."""
    from roost.desk import DeskAsleep
    seen: list[tuple[str, str]] = []
    running = {"now": True}
    page = _ShotPage()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if running["now"]:
            return httpx.Response(200, json={"browser": "running", "cdp_token": "tok"})
        return httpx.Response(409, json={"detail": "asleep"})

    async def connect(url: str, token: str):
        return page

    desk = KeeperDesk(config, _BOT_ID, transport=httpx.MockTransport(handler), connect_page=connect)
    assert await desk.screenshot() == b"\xff\xd8jpeg"
    page.alive, running["now"] = False, False
    with pytest.raises(DeskUnavailable):
        await desk.screenshot()
    with pytest.raises(DeskAsleep):
        await desk.screenshot()
    assert ("POST", _START) not in seen
    assert seen == [("POST", _ATTACH), ("POST", _ATTACH)]


# -- Fix round 1, finding 1: a CDP reply error during a screenshot must never
# close the bot's own page -- only a genuinely dead connection may. --


async def test_a_cdp_reply_error_during_a_screenshot_never_closes_the_bots_page(config):
    """Minimizing/hiding the bot's tab during 'Take control', or the
    Computer tab just polling a tab that was closed, can make one capture
    answer a CDP-level error reply (or hit the send timeout) while the
    connection itself stays up. Before this fix, KeeperDesk.screenshot
    treated that exactly like a dead connection: it closed the bot's own
    page and nulled it out, so the bot's next open_page/read_page went
    through _ensure_page -- POSTing /browser/start and opening a brand
    new tab (Target.createTarget) that orphans the one the user was
    looking at."""
    seen: list[tuple[str, str]] = []
    page = _ReplyErrorPage()
    connect_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json={"browser": "running", "cdp_token": "tok"})

    async def connect(url: str, token: str):
        nonlocal connect_calls
        connect_calls += 1
        return page

    desk = KeeperDesk(config, _BOT_ID, transport=httpx.MockTransport(handler), connect_page=connect)
    with pytest.raises(DeskUnavailable):
        await desk.screenshot()
    assert page.closed is False   # the bot's page survives a reply error

    result = await desk.open_page("https://example.com/")

    assert result.url == "https://example.com/"
    assert page.open_page_calls == ["https://example.com/"]
    assert connect_calls == 1   # the same page the screenshot attached to, never replaced
    assert ("POST", _START) not in seen


# -- Stuck flow (Task 6): open in your main Brave --


class _FakeOpenRunner:
    """Stands in for ``/usr/bin/open`` behind the real keeper app. It records
    each argv and answers ``exit_code``. It never runs anything."""

    def __init__(self, exit_code: int = 0) -> None:
        self.calls: list[list[str]] = []
        self._exit_code = exit_code

    async def __call__(self, argv, timeout_s):
        self.calls.append(list(argv))
        return self._exit_code


async def test_open_in_main_browser_opens_the_address_through_the_real_keeper(
    config: RoostConfig, keeper_app, transport: httpx.ASGITransport
) -> None:
    opener = _FakeOpenRunner()
    keeper_app.state.main_browser = MainBrowserOpener(runner=opener)
    client = KeeperClient(config, transport=transport)

    assert await client.open_in_main_browser(_BOT_ID, "https://example.com/") is None
    assert opener.calls == [["/usr/bin/open", "-a", "Brave Browser", "https://example.com/"]]


async def test_open_in_main_browser_refused_address_is_url_blocked_not_desk_unavailable(
    config: RoostConfig, keeper_app, transport: httpx.ASGITransport
) -> None:
    opener = _FakeOpenRunner()
    keeper_app.state.main_browser = MainBrowserOpener(runner=opener)
    client = KeeperClient(config, transport=transport)

    with pytest.raises(UrlBlocked):
        await client.open_in_main_browser(_BOT_ID, "javascript:alert(1)")
    assert opener.calls == []


async def test_open_in_main_browser_failure_is_desk_unavailable(
    config: RoostConfig, keeper_app, transport: httpx.ASGITransport
) -> None:
    keeper_app.state.main_browser = MainBrowserOpener(runner=_FakeOpenRunner(exit_code=1))
    client = KeeperClient(config, transport=transport)

    with pytest.raises(DeskUnavailable):
        await client.open_in_main_browser(_BOT_ID, "https://example.com/")


async def test_open_in_main_browser_with_the_keeper_down_is_desk_unavailable(config: RoostConfig) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = KeeperClient(config, transport=httpx.MockTransport(handler))
    with pytest.raises(DeskUnavailable):
        await client.open_in_main_browser(_BOT_ID, "https://example.com/")


async def test_a_400_from_any_other_keeper_call_is_still_desk_unavailable(config: RoostConfig) -> None:
    """``refused_on_bad_request`` is opt-in: only ``open_in_main_browser`` turns a 400 into ``UrlBlocked``."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "bot_id must be a UUID4"})

    client = KeeperClient(config, transport=httpx.MockTransport(handler))
    with pytest.raises(DeskUnavailable):
        await client.get_desk(_BOT_ID)


class _GoneTabGuards:
    async def arm(self, fence) -> None:
        raise CdpReplyError("CDP error replying to 'Page.getFrameTree': Session with given id not found.")


class _GoneTabPage(_WorksPage):
    """The bot's tab was closed: every call on its session fails, the socket itself is fine."""

    async def guards(self, hands_off=None):
        return _GoneTabGuards()

    async def page_session(self):
        raise CdpReplyError("Session with given id not found.")


class _FreshTabGuards:
    armed = False

    async def arm(self, fence) -> None:
        _FreshTabGuards.armed = True


class _FreshTabPage(_WorksPage):
    async def guards(self, hands_off=None):
        return _FreshTabGuards()

    async def page_session(self):
        return ("client", "fresh-session")


async def _started() -> dict:
    return {"cdp_token": "t"}


async def test_arming_the_guards_on_a_closed_tab_reconnects_once(config, transport) -> None:
    gone, fresh = _GoneTabPage(), _FreshTabPage()
    desk = KeeperDesk(config, _BOT_ID, transport=transport, computer="linux",
                      connect_page=_sequential_page_factory([gone, fresh]))
    desk._start_browser_session = _started
    await desk.arm_guards(object())
    assert gone.closed is True and _FreshTabGuards.armed is True


async def test_the_page_session_of_a_closed_tab_reconnects_once(config, transport) -> None:
    gone, fresh = _GoneTabPage(), _FreshTabPage()
    desk = KeeperDesk(config, _BOT_ID, transport=transport, computer="linux",
                      connect_page=_sequential_page_factory([gone, fresh]))
    desk._start_browser_session = _started
    assert await desk._page_session() == ("client", "fresh-session")
    assert gone.closed is True
