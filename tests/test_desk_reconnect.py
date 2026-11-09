"""One CDP connection per bot, kept healthy (2026-10-27 incident).

The keeper's relay closes an older connection (4409) when a new one comes. The owner's Yes on a Send card then met
a superseded socket that the page driver was still handed ("not connected" → "My browser didn't answer"), and
disarming the guards failed too. These tests hold the fixes: a closed socket is never handed out, every page driver
call is retried once on a fresh page, a single failed command never tears down the shared connection, page creation
is serialised, and armed guards follow a replacement page."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
import websockets
from cu_page_helpers import FakeCdp, load_fixture

from roost.config import RoostConfig
from roost.desk import DeskUnavailable, PageText
from roost.desk.browser import DeskBrowserPage
from roost.desk.browser_guards import BrowserGuards
from roost.desk.cdp import CdpClient, CdpClientError, CdpReplyError
from roost.desk.client import KeeperDesk

_BOT_ID = "00000000-0000-4000-8000-000000000001"
_SESSION_GONE = "CDP error replying to 'Page.getNavigationHistory': {'message': 'Session with given id not found'}"
_TIMED_OUT = "timed out after 30s waiting for a reply to 'Accessibility.getFullAXTree'"


@pytest.fixture
def config(tmp_path) -> RoostConfig:
    return RoostConfig(server_secret="x" * 32, database_dir=tmp_path / "data", desks_dir=tmp_path / "desks",
                       keeper_secret="k" * 32)


@pytest.fixture
def transport() -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(200, json={"cdp_token": "t"}))


class _BrokenCdp(FakeCdp):
    """A page client whose next ``fail`` sends raise ``error``, then answers from its fixture."""

    def __init__(self, error: Exception | None = None, fail: int = 0) -> None:
        super().__init__(load_fixture("login"))
        self.error, self.fail = error, fail
        self.open = True

    @property
    def is_open(self) -> bool:
        return self.open

    async def send(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None) -> dict:
        if self.fail > 0 and self.error is not None:
            self.fail -= 1
            raise self.error
        return await super().send(method, params, session_id)


class _Guards:
    def __init__(self) -> None:
        self.fences: list[Any] = []
        self.disarmed = 0

    async def arm(self, fence: Any) -> None:
        self.fences.append(fence)

    async def disarm(self) -> None:
        self.disarmed += 1


class _Page:
    """A ``DeskBrowserPage`` stand-in over one client: its session, its guards, and how often it was told to forget."""

    def __init__(self, client: _BrokenCdp | None = None) -> None:
        self.client = client or _BrokenCdp()
        self.closed = False
        self.forgot = 0
        self.guard = _Guards()
        self.reads: list[Exception | None] = []

    async def page_session(self) -> tuple[Any, str]:
        if not self.client.is_open:
            raise CdpClientError("connection closed")
        return self.client, "S1"

    def forget_session(self) -> None:
        self.forgot += 1

    async def guards(self, hands_off=None) -> _Guards:
        return self.guard

    async def read_page(self) -> PageText:
        if self.reads:
            error = self.reads.pop(0)
            if error is not None:
                raise error
        return PageText(url="https://shop.example/", title="ok", text="ok", truncated=False)

    async def close(self) -> None:
        self.closed = True
        self.client.open = False


class _Pages:
    """A ``connect_page`` double: hands out ``pages`` in order and counts the connections."""

    def __init__(self, *pages: _Page) -> None:
        self.pages = list(pages)
        self.connects = 0

    async def __call__(self, relay_url: str, token: str) -> _Page:
        self.connects += 1
        await asyncio.sleep(0)               # a real connect yields: a concurrent caller gets to run meanwhile
        return self.pages.pop(0)


def _desk(config, transport, pages: _Pages) -> KeeperDesk:
    desk = KeeperDesk(config, _BOT_ID, transport=transport, computer="linux", connect_page=pages)

    async def started() -> dict:
        return {"cdp_token": "t"}

    desk._start_browser_session = started
    return desk


# -- 1a: a closed socket is never handed out ----------------------------------------------------------------------


class _ClosedClient:
    is_open = False

    async def send(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None) -> dict:
        raise CdpClientError("not connected")


async def test_page_session_on_a_closed_socket_raises_even_with_a_cached_session() -> None:
    page = DeskBrowserPage(_ClosedClient())  # type: ignore[arg-type]
    page._session_id = "old-session"
    with pytest.raises(CdpClientError) as raised:
        await page.page_session()
    assert not isinstance(raised.value, CdpReplyError)


async def test_page_session_of_a_superseded_page_comes_from_a_fresh_page(config, transport) -> None:
    old, fresh = _Page(), _Page()
    old.client.open = False                       # the keeper closed it (4409) when another connection came
    desk = _desk(config, transport, _Pages(old, fresh))
    client, sid = await desk._page_session()
    assert client is fresh.client and sid == "S1"
    assert old.closed is True


# -- 1b: every page driver call is retried once on a fresh page ---------------------------------------------------


async def test_a_driver_call_whose_connection_dies_runs_again_on_a_fresh_page(config, transport) -> None:
    dead = _Page(_BrokenCdp(CdpClientError("not connected"), fail=1))
    fresh = _Page()
    pages = _Pages(dead, fresh)
    desk = _desk(config, transport, pages)
    assert await desk.page().url() == "https://shop.example/login"
    assert dead.closed is True and pages.connects == 2


async def test_a_driver_call_whose_socket_closes_mid_method_runs_again_on_a_fresh_page(config, transport) -> None:
    dead = _Page(_BrokenCdp(websockets.ConnectionClosed(None, None), fail=1))
    fresh = _Page()
    desk = _desk(config, transport, _Pages(dead, fresh))
    assert len(await desk.page().targets()) > 0
    assert dead.closed is True


async def test_a_driver_call_with_one_failed_command_propagates_and_keeps_the_page(config, transport) -> None:
    page = _Page(_BrokenCdp(CdpReplyError(_TIMED_OUT), fail=1))
    pages = _Pages(page)
    desk = _desk(config, transport, pages)
    with pytest.raises(CdpReplyError):
        await desk.page().url()
    assert page.closed is False and pages.connects == 1
    assert await desk.page().url() == "https://shop.example/login"     # the same page still answers


async def test_a_driver_call_on_a_closed_tab_forgets_the_session_and_stays_on_the_same_connection(
        config, transport) -> None:
    page = _Page(_BrokenCdp(CdpReplyError(_SESSION_GONE), fail=1))
    pages = _Pages(page)
    desk = _desk(config, transport, pages)
    assert await desk.page().url() == "https://shop.example/login"
    assert page.forgot == 1 and page.closed is False and pages.connects == 1


# -- 2: one failed command never closes the shared connection -----------------------------------------------------


async def test_a_reply_timeout_never_closes_or_replaces_the_page(config, transport) -> None:
    page = _Page()
    page.reads = [CdpReplyError(_TIMED_OUT)]
    pages = _Pages(page)
    desk = _desk(config, transport, pages)
    with pytest.raises(DeskUnavailable):
        await desk.read_page()
    assert page.closed is False and page.forgot == 0 and pages.connects == 1


async def test_a_navigation_error_reply_never_closes_or_replaces_the_page(config, transport) -> None:
    page = _Page()
    page.reads = [CdpReplyError("CDP error replying to 'Page.navigate': {'message': 'Cannot navigate to invalid URL'}")]
    pages = _Pages(page)
    desk = _desk(config, transport, pages)
    with pytest.raises(DeskUnavailable):
        await desk.read_page()
    assert page.closed is False and pages.connects == 1


async def test_a_session_not_found_reply_reattaches_on_the_same_client(config, transport) -> None:
    page = _Page()
    page.reads = [CdpReplyError(_SESSION_GONE)]
    pages = _Pages(page)
    desk = _desk(config, transport, pages)
    assert (await desk.read_page()).url == "https://shop.example/"
    assert page.forgot == 1 and page.closed is False and pages.connects == 1


async def test_a_target_closed_reply_reattaches_on_the_same_client(config, transport) -> None:
    page = _Page()
    page.reads = [CdpReplyError("CDP error replying to 'DOM.getDocument': {'message': 'Target closed'}")]
    desk = _desk(config, transport, _Pages(page))
    assert (await desk.read_page()).title == "ok"
    assert page.forgot == 1 and page.closed is False


# -- 3: page creation is serialised --------------------------------------------------------------------------------


async def test_two_concurrent_first_users_connect_once(config, transport) -> None:
    pages = _Pages(_Page(), _Page())
    desk = _desk(config, transport, pages)
    first, second = await asyncio.gather(desk._ensure_page(), desk._ensure_page())
    assert first is second and pages.connects == 1


async def test_a_view_and_a_first_user_connect_once(config, transport) -> None:
    pages = _Pages(_Page(), _Page())
    desk = _desk(config, transport, pages)
    viewed, used = await asyncio.gather(desk._attach_page(), desk._ensure_page())
    assert viewed is used and pages.connects == 1


# -- 4: armed guards follow a replacement page ---------------------------------------------------------------------


async def test_a_replacement_page_mid_run_is_armed_with_the_same_fence(config, transport) -> None:
    first, second = _Page(), _Page()
    desk = _desk(config, transport, _Pages(first, second))
    fence = object()
    await desk.arm_guards(fence)
    first.reads = [CdpClientError("connection closed")]       # the keeper's 4409: another connection took over
    await desk.read_page()
    assert second.guard.fences == [fence]
    assert desk.guards() is second.guard
    assert first.guard.disarmed == 1


async def test_a_replacement_page_after_disarm_is_not_armed(config, transport) -> None:
    first, second = _Page(), _Page()
    desk = _desk(config, transport, _Pages(first, second))
    await desk.arm_guards(object())
    await desk.disarm_guards()
    first.reads = [CdpClientError("connection closed")]
    await desk.read_page()
    assert second.guard.fences == []


class _GuardClient:
    """Answers the guards' setup, then goes dead (``alive`` False) like a superseded socket."""

    def __init__(self) -> None:
        self.alive = True
        self.queues: list[asyncio.Queue[dict[str, Any]]] = []

    async def send(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None) -> dict:
        if not self.alive:
            raise CdpClientError("not connected")
        return {"result": {}}

    def listen(self, methods: frozenset[str]) -> asyncio.Queue[dict[str, Any]]:
        self.queues.append(asyncio.Queue())
        return self.queues[-1]

    def unlisten(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self.queues = [q for q in self.queues if q is not queue]


async def test_disarm_on_a_closed_client_never_raises() -> None:
    from roost.computer_use.fence import SiteFence

    client = _GuardClient()
    guards = BrowserGuards(client, "S1", "T1")  # type: ignore[arg-type]
    await guards.arm(SiteFence(frozenset({"shop.example"})))
    client.alive = False
    await guards.disarm()
    assert guards.armed is False


async def test_the_guard_pump_survives_a_dead_connection() -> None:
    from roost.computer_use.fence import SiteFence

    client = _GuardClient()
    guards = BrowserGuards(client, "S1", "T1")  # type: ignore[arg-type]
    await guards.arm(SiteFence(frozenset()))
    client.alive = False
    client.queues[0].put_nowait({"method": "Fetch.requestPaused", "sessionId": "S1",
                                 "params": {"requestId": "r1", "request": {"url": "https://elsewhere.example/"}}})
    await asyncio.sleep(0.01)
    assert guards._pump is not None and not guards._pump.done()
    await guards.disarm()


# -- 6: a closed connection ends every wait --------------------------------------------------------------------------


async def _relay_that_closes(connection: Any) -> None:
    await asyncio.sleep(0.05)
    await connection.close(4409)


async def test_a_closed_connection_fails_a_pending_wait_event_promptly() -> None:
    server = await websockets.serve(_relay_that_closes, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    client = CdpClient(f"ws://127.0.0.1:{port}", "token")
    await client.connect()
    try:
        assert client.is_open is True
        with pytest.raises(CdpClientError):
            await asyncio.wait_for(client.wait_event("Page.loadEventFired", timeout=10), timeout=2)
        assert client.is_open is False
    finally:
        await client.close()
        server.close()
        await server.wait_closed()


async def test_closing_the_client_fails_a_pending_wait_event() -> None:
    server = await websockets.serve(lambda connection: connection.wait_closed(), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    client = CdpClient(f"ws://127.0.0.1:{port}", "token")
    await client.connect()
    try:
        waiter = asyncio.ensure_future(client.wait_event("Page.loadEventFired", timeout=10))
        await asyncio.sleep(0.01)
        await client.close()
        with pytest.raises(CdpClientError):
            await asyncio.wait_for(waiter, timeout=2)
        assert client.is_open is False
    finally:
        server.close()
        await server.wait_closed()
