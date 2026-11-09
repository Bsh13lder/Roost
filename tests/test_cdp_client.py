"""Unit tests for ``roost.desk.cdp.CdpClient`` and
``roost.desk.browser.DeskBrowserPage`` against a fake CDP WebSocket
server — never a real browser (that's ``tests/test_browsers_real.py``'s
job, marker ``desk``, for the actual Brave process).

The fake server plays the role of the keeper's relay + Brave itself: it
checks the ``X-Roost-Desk-Token`` header, answers the exact handshake and
read sequence the brief specifies, and records every message it receives
so tests can assert on the precise CDP call sequence — including that
``Runtime.evaluate`` is never sent, anywhere.
"""

from __future__ import annotations

import asyncio
import base64
import itertools
import json
import logging
import re
from typing import Any

import pytest
import websockets

import roost.desk.browser as browser_module
from roost.constants import PAGE_TEXT_LIMIT, STUCK_CAPTCHA_FRAME_SELECTOR, STUCK_PASSWORD_SELECTOR
from roost.desk.browser import DeskBrowserPage, _build_page_text, _collapse_consecutive_repeats
from roost.desk.cdp import CdpClient, CdpClientError, CdpReplyError
from roost.desk.url_policy import UrlBlocked

_TOKEN = "test-cdp-token"

_AX_NODES = [
    {"ignored": True, "role": {"value": "heading"}, "name": {"value": "ignored heading"}},
    {"role": {"value": "heading"}, "name": {"value": "Welcome"}},
    {"role": {"value": "generic"}, "name": {"value": "not readable, wrong role"}},
    {"role": {"value": "paragraph"}, "name": {"value": "Welcome"}},  # immediate repeat -> collapsed
    {"role": {"value": "paragraph"}, "name": {"value": "Second paragraph"}},
    {"role": {"value": "button"}, "name": {"value": ""}},  # empty name -> skipped
]

# Comfortably over websockets' own 1 MiB default `max_size` once wrapped
# in the rest of the CDP JSON envelope.
_OVERSIZED_AX_NODES = [{"role": {"value": "paragraph"}, "name": {"value": "x" * (2 * 1024 * 1024)}}]

_MAIN_FRAME_ID = "frame-1"
_ROOT_NODE_ID = 1

# Stuck flow (Task 2): responses a real page sends besides its own document.
_IFRAME_DOCUMENT = {"type": "Document", "frameId": "frame-2", "response": {"status": 403}}
_MAIN_FRAME_SCRIPT = {"type": "Script", "frameId": _MAIN_FRAME_ID, "response": {"status": 404}}

_HCAPTCHA_SRC = "https://newassets.hcaptcha.com/captcha/v1/1a2b3c/static/hcaptcha.html#frame=checkbox"
_VISIBLE_RECAPTCHA_SRC = "https://www.google.com/recaptcha/api2/anchor?ar=1&k=site-key&size=normal"
_INVISIBLE_RECAPTCHA_SRC = "https://www.google.com/recaptcha/api2/anchor?ar=1&k=site-key&size=invisible"
_AD_FRAME_SRC = "https://ads.example/frame?slot=top"

# The CSS subset STUCK_CAPTCHA_FRAME_SELECTOR uses: iframe[src*="…"], optionally with :not([src*="…"]).
_FRAME_RULE = re.compile(r'iframe\[src\*="(?P<has>[^"]+)"\](?::not\(\[src\*="(?P<hasnt>[^"]+)"\]\))?')


def _frame_selector_matches(selector: str, src: str) -> bool:
    """Evaluate ``selector`` on one iframe ``src`` the way Chromium's selector engine would, for the
    subset above -- so the fake DOM answers like a real one and the tests check the real selector."""
    for rule in selector.split(","):
        found = _FRAME_RULE.fullmatch(rule.strip())
        if found is not None and found["has"] in src and not (found["hasnt"] and found["hasnt"] in src):
            return True
    return False


class _FakeCdpServer:
    """Answers exactly the handshake/read sequence the brief specifies.
    Records every inbound message (for call-sequence assertions) and the
    desk-token header presented on connect.

    Stuck flow (Task 2): after ``Page.navigate`` it sends
    ``pre_responses`` first (an iframe's or a sub-resource's), then the
    main document's ``Network.responseReceived`` (``doc_status``; None
    sends none), always before ``Page.loadEventFired``, as a real tab
    does. Its DOM has ``password_fields`` password boxes and one iframe
    per ``frame_srcs`` entry; ``dom_error`` makes every DOM call an error
    reply."""

    def __init__(
        self, *, fire_load_event: bool = True, oversized_ax_tree: bool = False, open_pages: bool = True,
        fail_first_screenshot: bool = False, doc_status: int | None = 200,
        pre_responses: tuple[dict[str, Any], ...] = (), password_fields: int = 0,
        frame_srcs: tuple[str, ...] = (), dom_error: bool = False,
        frame_tree_id: str | None = _MAIN_FRAME_ID, navigate_frame_id: str = _MAIN_FRAME_ID,
    ) -> None:
        self.received_token: str | None = None
        self.received: list[dict[str, Any]] = []
        self._fire_load_event = fire_load_event
        self._oversized_ax_tree = oversized_ax_tree
        self._open_pages = open_pages
        # S1.8 Fix round 1, finding 1: the *first* Page.captureScreenshot
        # answers a CDP-level error reply (the tab behind that session
        # closed) -- every one after that succeeds, so a test can prove
        # DeskBrowserPage.capture_screenshot retries once instead of
        # failing every poll.
        self._fail_first_screenshot = fail_first_screenshot
        self._screenshot_calls = 0
        self._doc_status = doc_status
        self._pre_responses = pre_responses
        self._password_fields = password_fields
        self._frame_srcs = frame_srcs
        self._dom_error = dom_error
        # What Page.getFrameTree names the main frame (None: no id at all) and what Page.navigate
        # reports it navigated; a real browser gives the same id for both.
        self._frame_tree_id = frame_tree_id
        self._navigate_frame_id = navigate_frame_id
        self._target_ids = itertools.count(1)
        self._server: websockets.server.Server | None = None

    async def start(self) -> None:
        self._server = await websockets.serve(self._handle, "127.0.0.1", 0)

    async def stop(self) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    @property
    def url(self) -> str:
        assert self._server is not None
        port = self._server.sockets[0].getsockname()[1]
        return f"ws://127.0.0.1:{port}"

    async def _handle(self, connection: Any) -> None:
        self.received_token = connection.request.headers.get("X-Roost-Desk-Token")
        async for raw in connection:
            message = json.loads(raw)
            self.received.append(message)
            await self._respond(connection, message)

    async def _respond(self, connection: Any, message: dict[str, Any]) -> None:
        method = message["method"]
        msg_id = message["id"]
        if method == "Page.captureScreenshot":
            await self._respond_to_screenshot(connection, msg_id)
            return
        result = self._result_for(method, message.get("params") or {})
        if result is None:
            await connection.send(json.dumps({"id": msg_id, "error": {"message": f"unhandled {method}"}}))
            return
        await connection.send(json.dumps({"id": msg_id, "result": result}))
        if method == "Page.navigate":
            await self._send_navigation_events(connection, message.get("sessionId"))

    def _result_for(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        if method == "Target.createTarget":
            return {"targetId": f"target-{next(self._target_ids)}"}
        if method == "Target.attachToTarget":
            return {"sessionId": "session-1"}
        if method == "Target.detachFromTarget":
            return {}
        if method == "Page.createIsolatedWorld":
            return {"executionContextId": 5}
        if method == "Runtime.evaluate":          # the front-tab probe: [visible, focused]
            return {"result": {"value": [True, True]}}
        if method in ("Page.enable", "Inspector.enable", "Network.enable", "Network.disable"):
            return {}
        if method == "Page.getFrameTree":
            frame = {} if self._frame_tree_id is None else {"id": self._frame_tree_id}
            return {"frameTree": {"frame": frame}}
        if method == "Page.navigate":
            return {"frameId": self._navigate_frame_id}
        if method == "Accessibility.getFullAXTree":
            # Fix round 1, finding 4: a real page's accessibility tree
            # routinely exceeds websockets.connect's own 1 MiB default
            # `max_size` -- this fakes that, a single node whose name is
            # well over it, to prove CdpClient asks for a larger one.
            return {"nodes": _OVERSIZED_AX_NODES if self._oversized_ax_tree else _AX_NODES}
        if method == "Target.getTargetInfo":
            return {"targetInfo": {"title": "Example Page", "url": "https://example.com/"}}
        if method == "Target.getTargets":
            infos = [{"targetId": "target-0", "type": "page", "url": "https://example.com/"}] if self._open_pages else []
            return {"targetInfos": infos}
        if method.startswith("DOM.") and not self._dom_error:
            return self._dom_result(method, params)
        return None

    def _dom_result(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        if method == "DOM.getDocument":
            return {"root": {"nodeId": _ROOT_NODE_ID, "nodeName": "#document"}}
        if method == "DOM.disable":
            return {}
        if method != "DOM.querySelectorAll" or params.get("nodeId") != _ROOT_NODE_ID:
            return None
        selector = params.get("selector", "")
        if selector == STUCK_PASSWORD_SELECTOR:
            return {"nodeIds": list(range(100, 100 + self._password_fields))}
        return {"nodeIds": [200 + i for i, src in enumerate(self._frame_srcs) if _frame_selector_matches(selector, src)]}

    async def _send_navigation_events(self, connection: Any, session_id: str | None) -> None:
        main = ({"type": "Document", "frameId": _MAIN_FRAME_ID, "response": {"status": self._doc_status}},)
        for params in (*self._pre_responses, *(main if self._doc_status is not None else ())):
            await connection.send(
                json.dumps({"method": "Network.responseReceived", "sessionId": session_id, "params": params})
            )
        if self._fire_load_event:
            await connection.send(json.dumps({"method": "Page.loadEventFired", "sessionId": session_id, "params": {}}))

    async def _respond_to_screenshot(self, connection: Any, msg_id: int) -> None:
        self._screenshot_calls += 1
        if self._fail_first_screenshot and self._screenshot_calls == 1:
            await connection.send(json.dumps({"id": msg_id, "error": {"message": "Session with given id not found"}}))
            return
        data = base64.b64encode(b"\xff\xd8jpeg").decode()
        await connection.send(json.dumps({"id": msg_id, "result": {"data": data}}))


@pytest.fixture
async def fake_server():
    server = _FakeCdpServer()
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


@pytest.fixture
async def connected_client(fake_server: _FakeCdpServer):
    client = CdpClient(fake_server.url, _TOKEN)
    await client.connect()
    try:
        yield client
    finally:
        await client.close()


# -- CdpClient ---------------------------------------------------------


async def test_connect_sends_the_desk_token_header(fake_server: _FakeCdpServer, connected_client: CdpClient) -> None:
    await connected_client.send("Page.enable")
    assert fake_server.received_token == _TOKEN


async def test_send_before_connect_raises() -> None:
    client = CdpClient("ws://127.0.0.1:1", _TOKEN)
    with pytest.raises(CdpClientError):
        await client.send("Page.enable")


async def test_send_assigns_incrementing_ids(fake_server: _FakeCdpServer, connected_client: CdpClient) -> None:
    await connected_client.send("Page.enable")
    await connected_client.send("Page.enable")
    assert [m["id"] for m in fake_server.received] == [1, 2]


async def test_send_returns_the_reply_matching_its_own_id(connected_client: CdpClient) -> None:
    reply = await connected_client.send("Target.createTarget", {"url": "about:blank"})
    assert reply["result"]["targetId"] == "target-1"


async def test_send_carries_params_and_session_id(fake_server: _FakeCdpServer, connected_client: CdpClient) -> None:
    await connected_client.send("Page.navigate", {"url": "https://example.com/"}, session_id="session-xyz")
    sent = fake_server.received[0]
    assert sent["params"] == {"url": "https://example.com/"}
    assert sent["sessionId"] == "session-xyz"


async def test_wait_event_sees_an_event_fired_after_navigate(connected_client: CdpClient) -> None:
    waiter = asyncio.create_task(connected_client.wait_event("Page.loadEventFired", session_id="s1", timeout=5))
    await connected_client.send("Page.navigate", {"url": "https://example.com/"}, session_id="s1")
    event = await waiter
    assert event is not None
    assert event["method"] == "Page.loadEventFired"
    assert event["sessionId"] == "s1"


async def test_wait_event_times_out_and_returns_none(fake_server: _FakeCdpServer) -> None:
    fake_server._fire_load_event = False
    client = CdpClient(fake_server.url, _TOKEN)
    await client.connect()
    try:
        await client.send("Page.navigate", {"url": "https://example.com/"}, session_id="s1")
        event = await client.wait_event("Page.loadEventFired", session_id="s1", timeout=0.1)
        assert event is None
    finally:
        await client.close()


async def test_close_is_idempotent(connected_client: CdpClient) -> None:
    await connected_client.close()
    await connected_client.close()  # does not raise


async def test_send_accepts_a_reply_larger_than_websockets_default_max_size() -> None:
    # Fix round 1, finding 4: before CDP_MAX_MESSAGE_BYTES, this closed
    # the socket with code 1009 and every pending/later send raised
    # instead of returning the oversized (but otherwise normal) reply.
    server = _FakeCdpServer(oversized_ax_tree=True)
    await server.start()
    client = CdpClient(server.url, _TOKEN)
    await client.connect()
    try:
        reply = await client.send("Accessibility.getFullAXTree")
        name = reply["result"]["nodes"][0]["name"]["value"]
        assert len(name) > 1024 * 1024
    finally:
        await client.close()
        await server.stop()


async def test_send_times_out_and_raises_cdp_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Final review, finding 4: a hostile page can hang its own
    renderer, so a CDP call like ``Accessibility.getFullAXTree`` never
    gets a reply at all. Before this, ``send`` awaited the reply future
    forever -- the turn (and every later message for that bot) never
    ended. A real timeout is ``CDP_SEND_TIMEOUT_S`` (30s); shortened
    here the same way ``test_open_page_still_reads_after_load_event_
    times_out`` shortens ``PAGE_LOAD_EVENT_TIMEOUT_S`` -- proving the
    *path*, not the exact duration."""
    import roost.desk.cdp as cdp_module

    monkeypatch.setattr(cdp_module, "CDP_SEND_TIMEOUT_S", 0.05)

    async def _never_respond(connection: Any) -> None:
        async for _raw in connection:
            pass  # received, but a hung renderer never gets a reply

    server = await websockets.serve(_never_respond, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    client = CdpClient(f"ws://127.0.0.1:{port}", _TOKEN)
    await client.connect()
    try:
        with pytest.raises(CdpClientError):
            await client.send("Accessibility.getFullAXTree")
    finally:
        await client.close()
        server.close()
        await server.wait_closed()


async def test_a_send_on_a_socket_the_relay_closed_raises_cdp_client_error() -> None:
    """Gela, 2026-10-25: the relay closed the socket (4503) between two calls, and the next send raised
    websockets' ConnectionClosedError, which no caller catches, so the whole run ended with "Something went
    wrong". It is the browser not answering, the error every caller already handles."""
    async def _close_at_once(connection: Any) -> None:
        await connection.close(4503)

    server = await websockets.serve(_close_at_once, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    client = CdpClient(f"ws://127.0.0.1:{port}", _TOKEN)
    await client.connect()
    try:
        await asyncio.sleep(0.05)
        with pytest.raises(CdpClientError):
            await client.send("Page.bringToFront")
    finally:
        await client.close()
        server.close()
        await server.wait_closed()


async def test_send_raises_on_a_cdp_level_error_reply(fake_server: _FakeCdpServer, connected_client: CdpClient) -> None:
    # The fake server's catch-all branch answers any unhandled method
    # with {"id": ..., "error": {...}} -- the same shape a real browser
    # sends back for a CDP call it refuses or doesn't recognize.
    with pytest.raises(CdpClientError):
        await connected_client.send("Some.UnhandledMethod")


async def test_wait_event_skips_an_event_its_predicate_rejects(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    fake_server._pre_responses = (_IFRAME_DOCUMENT,)   # an iframe's Document (403) arrives first
    waiter = asyncio.create_task(
        connected_client.wait_event(
            "Network.responseReceived", session_id="s1", timeout=5,
            predicate=lambda event: event["params"]["frameId"] == _MAIN_FRAME_ID,
        )
    )
    await connected_client.send("Page.navigate", {"url": "https://example.com/"}, session_id="s1")
    event = await waiter
    assert event is not None
    assert event["params"]["frameId"] == _MAIN_FRAME_ID
    assert event["params"]["response"]["status"] == 200


async def test_a_predicate_that_raises_skips_the_event_and_keeps_the_connection(
    connected_client: CdpClient,
) -> None:
    """An error inside a filter must not end the reader task: that would fail
    every pending send on a socket that is still fine."""

    def broken(event: dict[str, Any]) -> bool:
        raise KeyError("params")

    waiter = asyncio.create_task(
        connected_client.wait_event("Page.loadEventFired", session_id="s1", timeout=0.3, predicate=broken)
    )
    await connected_client.send("Page.navigate", {"url": "https://example.com/"}, session_id="s1")
    assert await waiter is None
    reply = await connected_client.send("Target.createTarget", {"url": "about:blank"})
    assert reply["result"]["targetId"] == "target-1"


# -- DeskBrowserPage -----------------------------------------------------


async def test_open_page_runs_the_exact_handshake_and_read_sequence(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    page = DeskBrowserPage(connected_client)
    result = await page.open_page("https://example.com/")

    methods = [m["method"] for m in fake_server.received]
    assert methods == [
        "Target.getTargets",                      # the tab in front (roost/desk/front_tab.py) ...
        "Target.attachToTarget",
        "Page.getFrameTree",
        "Page.createIsolatedWorld",
        "Runtime.evaluate",
        "Target.detachFromTarget",
        "Target.attachToTarget",                  # ... becomes the bot's tab: no new tab
        "Page.enable",
        "Inspector.enable",                       # voice §4: Inspector.targetCrashed tells a crashed tab
        "Page.getFrameTree",
        "Network.enable",
        "Page.navigate",
        "Network.disable",
        "Accessibility.getFullAXTree",
        "Target.getTargetInfo",
        "DOM.getDocument",
        "DOM.querySelectorAll",
        "DOM.querySelectorAll",
        "DOM.disable",
    ]
    assert result.url == "https://example.com/"
    assert result.title == "Example Page"
    assert "Welcome" in result.text
    assert result.status == 200


async def test_runtime_evaluate_runs_only_in_an_isolated_world(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    """A page's own script never answers: the only evaluate (the front-tab probe) names an isolated world."""
    page = DeskBrowserPage(connected_client)
    await page.open_page("https://example.com/")
    await page.read_page()
    evaluates = [m for m in fake_server.received if m["method"] == "Runtime.evaluate"]
    assert evaluates and all(m["params"]["contextId"] == 5 for m in evaluates)


async def test_a_tab_is_created_only_when_the_browser_has_no_page() -> None:
    server = _FakeCdpServer(open_pages=False)
    await server.start()
    client = CdpClient(server.url, "tok")
    await client.connect()
    try:
        async def no_wait(_seconds: float) -> None:
            return None

        await DeskBrowserPage(client, sleep=no_wait).open_page("https://example.com/")
        methods = [m["method"] for m in server.received]
        created = methods.index("Target.createTarget")       # D5: only after Brave had its moment to show one
        assert set(methods[:created]) == {"Target.getTargets"}
        assert methods.count("Target.createTarget") == 1 and methods[created + 1] == "Target.attachToTarget"
    finally:
        await client.close()
        await server.stop()


async def test_network_is_enabled_only_around_a_navigation(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    """I6: the Network domain streams every response of the tab, so it is on only while a navigation
    needs the main document's status. It is armed before the waiters, and off again right after."""
    page = DeskBrowserPage(connected_client)
    await page.open_page("https://example.com/")
    await page.read_page()                       # reading never needs it
    await page.open_page("https://example.com/")

    methods = [m["method"] for m in fake_server.received]
    network = [(i, m) for i, m in enumerate(methods) if m.startswith("Network.")]
    assert [m for _, m in network] == ["Network.enable", "Network.disable", "Network.enable", "Network.disable"]
    for enable_at, disable_at in ((network[0][0], network[1][0]), (network[2][0], network[3][0])):
        assert methods[enable_at + 1] == "Page.navigate"
        assert methods[disable_at - 1] == "Page.navigate"
    assert {m["sessionId"] for m in fake_server.received if m["method"].startswith("Network.")} == {"session-1"}


async def test_network_is_disabled_even_when_the_load_event_never_comes(
    fake_server: _FakeCdpServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(browser_module, "PAGE_LOAD_EVENT_TIMEOUT_S", 0.1)
    fake_server._fire_load_event = False
    client = CdpClient(fake_server.url, _TOKEN)
    await client.connect()
    try:
        await DeskBrowserPage(client).open_page("https://example.com/")
    finally:
        await client.close()
    methods = [m["method"] for m in fake_server.received]
    assert methods.count("Network.enable") == methods.count("Network.disable") == 1


async def test_dom_is_disabled_after_reading_the_signals(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    """I6: the DOM domain keeps node ids alive on the browser's side, so it is switched off once the
    two signals are read."""
    await DeskBrowserPage(connected_client).read_page()
    methods = [m["method"] for m in fake_server.received]
    assert methods[-4:] == ["DOM.getDocument", "DOM.querySelectorAll", "DOM.querySelectorAll", "DOM.disable"]
    assert fake_server.received[-1]["sessionId"] == "session-1"


async def test_a_dom_disable_that_fails_is_a_warning_and_the_read_still_succeeds(
    fake_server: _FakeCdpServer, connected_client: CdpClient, caplog: pytest.LogCaptureFixture
) -> None:
    fake_server._dom_error = True                # every DOM call, DOM.disable included, answers an error reply
    with caplog.at_level(logging.WARNING, logger=browser_module.logger.name):
        result = await DeskBrowserPage(connected_client).read_page()
    assert "Welcome" in result.text
    assert [m["method"] for m in fake_server.received][-2:] == ["DOM.getDocument", "DOM.disable"]
    assert any("DOM.disable" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)


async def test_read_page_reuses_the_session_from_open_page(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    page = DeskBrowserPage(connected_client)
    await page.open_page("https://example.com/")
    fake_server.received.clear()

    await page.read_page()

    methods = [m["method"] for m in fake_server.received]
    assert "Target.createTarget" not in methods
    assert "Target.attachToTarget" not in methods
    assert "Network.enable" not in methods
    assert "Network.disable" not in methods
    assert methods == [
        "Accessibility.getFullAXTree",
        "Target.getTargetInfo",
        "DOM.getDocument",
        "DOM.querySelectorAll",
        "DOM.querySelectorAll",
        "DOM.disable",
    ]


async def test_open_page_blocks_a_disallowed_url_before_any_cdp_call(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    page = DeskBrowserPage(connected_client)
    with pytest.raises(UrlBlocked):
        await page.open_page("http://127.0.0.1")
    assert fake_server.received == []


async def test_open_page_still_reads_after_load_event_times_out(
    fake_server: _FakeCdpServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A real timeout really is PAGE_LOAD_EVENT_TIMEOUT_S (20 s, per the
    # contract) -- shortened here purely so this test doesn't spend 20
    # real seconds proving the *path*, not the exact duration.
    monkeypatch.setattr(browser_module, "PAGE_LOAD_EVENT_TIMEOUT_S", 0.1)
    fake_server._fire_load_event = False
    client = CdpClient(fake_server.url, _TOKEN)
    await client.connect()
    try:
        page = DeskBrowserPage(client)
        result = await page.open_page("https://example.com/")
        assert result.title == "Example Page"
    finally:
        await client.close()


async def test_a_screenshot_with_no_session_attaches_to_the_open_page_and_never_creates_a_tab(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    page = DeskBrowserPage(connected_client)
    assert await page.capture_screenshot() == b"\xff\xd8jpeg"
    methods = [m["method"] for m in fake_server.received]
    assert methods[0] == "Target.getTargets" and "Target.createTarget" not in methods
    assert methods[-2:] == ["Target.attachToTarget", "Page.captureScreenshot"]   # the front tab, after its probe
    fake_server.received.clear()
    await page.capture_screenshot()   # the view's session is kept: nothing is attached again
    assert [m["method"] for m in fake_server.received] == ["Page.captureScreenshot"]


async def test_a_screenshot_reuses_the_bots_own_session(fake_server: _FakeCdpServer, connected_client: CdpClient) -> None:
    page = DeskBrowserPage(connected_client)
    await page.open_page("https://example.com/")
    fake_server.received.clear()
    await page.capture_screenshot()
    assert [(m["method"], m.get("sessionId")) for m in fake_server.received] == [("Page.captureScreenshot", "session-1")]


async def test_a_browser_with_no_page_is_asleep_for_a_screenshot() -> None:
    from roost.desk import DeskAsleep
    server = _FakeCdpServer(open_pages=False)
    await server.start()
    client = CdpClient(server.url, _TOKEN)
    await client.connect()
    try:
        with pytest.raises(DeskAsleep):
            await DeskBrowserPage(client).capture_screenshot()
        assert "Target.createTarget" not in [m["method"] for m in server.received]
    finally:
        await client.close()
        await server.stop()


async def test_a_screenshot_error_reply_reattaches_once_and_never_creates_a_tab() -> None:
    """S1.8 Fix round 1, finding 1: a CDP error reply (e.g. "Session with
    given id not found" -- the viewed tab closed) is not a dead
    connection. It is retried once through _attach_view, never
    Target.createTarget, so a closed tab doesn't fail every poll."""
    server = _FakeCdpServer(fail_first_screenshot=True)
    await server.start()
    client = CdpClient(server.url, _TOKEN)
    await client.connect()
    try:
        page = DeskBrowserPage(client)
        assert await page.capture_screenshot() == b"\xff\xd8jpeg"
        methods = [m["method"] for m in server.received]
        # the first attach, then the retry's (each front-tab probe detaches its own session again)
        assert methods.count("Target.attachToTarget") - methods.count("Target.detachFromTarget") == 2
        assert "Target.createTarget" not in methods
    finally:
        await client.close()
        await server.stop()


async def test_a_screenshot_error_reply_on_the_bots_own_session_reattaches_without_creating_a_tab(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    """The bot's own session can go stale too (its tab closed from outside
    roost, not through a view) -- the retry still never creates a tab, it
    just attaches to whatever page is open now."""
    page = DeskBrowserPage(connected_client)
    await page.open_page("https://example.com/")   # the bot's own session, "session-1"
    fake_server.received.clear()
    fake_server._fail_first_screenshot = True

    assert await page.capture_screenshot() == b"\xff\xd8jpeg"

    methods = [m["method"] for m in fake_server.received]
    assert "Target.createTarget" not in methods
    # the retry's _attach_view only (its front-tab probe detaches its own session again)
    assert methods.count("Target.attachToTarget") - methods.count("Target.detachFromTarget") == 1


# -- DeskBrowserPage: the stuck flow's page signals (design §1, R2, R3) --


async def test_open_page_reports_the_main_document_status(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    fake_server._doc_status = 403
    result = await DeskBrowserPage(connected_client).open_page("https://example.com/")
    assert result.status == 403


async def test_an_iframe_document_or_a_sub_resource_never_sets_the_status(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    """A page's own frames and files answer too: an ad frame's 403 or a
    missing script's 404 is not the page refusing the bot. Only the main
    frame's Document response is the page's status."""
    fake_server._pre_responses = (_IFRAME_DOCUMENT, _MAIN_FRAME_SCRIPT)
    result = await DeskBrowserPage(connected_client).open_page("https://example.com/")
    assert result.status == 200


async def test_a_page_with_no_document_response_has_no_status_and_no_extra_wait(
    fake_server: _FakeCdpServer, connected_client: CdpClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The response wait shares the load event's timeout. Once the load
    # event is in, the status is caught or never coming, so open_page must
    # not sit out the rest of that timeout (2 s here, 20 s for real).
    monkeypatch.setattr(browser_module, "PAGE_LOAD_EVENT_TIMEOUT_S", 2.0)
    fake_server._doc_status = None
    fake_server._pre_responses = (_IFRAME_DOCUMENT,)   # only an iframe answered
    loop = asyncio.get_running_loop()
    started = loop.time()
    result = await DeskBrowserPage(connected_client).open_page("https://example.com/")
    assert result.status is None
    assert loop.time() - started < 1.0


async def test_a_missing_main_frame_id_warns_once_per_page_session_without_the_address(
    fake_server: _FakeCdpServer, connected_client: CdpClient, caplog: pytest.LogCaptureFixture
) -> None:
    """With no main frame id no document can be told from an iframe's, so every open_page has no
    status. That is said once for the page session, and never names the address."""
    fake_server._frame_tree_id = None
    page = DeskBrowserPage(connected_client)
    with caplog.at_level(logging.WARNING, logger=browser_module.logger.name):
        first = await page.open_page("https://example.com/secret-path?token=abc")
        second = await page.open_page("https://example.com/other")
    assert (first.status, second.status) == (None, None)
    [warning] = [r.getMessage() for r in caplog.records if "status" in r.getMessage()]
    assert "main frame" in warning
    assert "example.com" not in warning and "secret-path" not in warning and "token" not in warning


async def test_a_main_frame_id_that_the_navigation_does_not_share_warns_once_per_page_session(
    fake_server: _FakeCdpServer, connected_client: CdpClient, caplog: pytest.LogCaptureFixture
) -> None:
    fake_server._navigate_frame_id = "frame-9"      # the tab navigated a frame the page never named main
    with caplog.at_level(logging.WARNING, logger=browser_module.logger.name):
        page = DeskBrowserPage(connected_client)
        await page.open_page("https://example.com/")
        await page.open_page("https://example.com/")
        await DeskBrowserPage(connected_client).open_page("https://example.com/")   # another page session
    warnings = [r.getMessage() for r in caplog.records if "main frame" in r.getMessage()]
    assert len(warnings) == 2
    assert all("example.com" not in w for w in warnings)


async def test_a_matching_main_frame_id_warns_about_nothing(
    fake_server: _FakeCdpServer, connected_client: CdpClient, caplog: pytest.LogCaptureFixture
) -> None:
    page = DeskBrowserPage(connected_client)
    with caplog.at_level(logging.WARNING, logger=browser_module.logger.name):
        assert (await page.open_page("https://example.com/")).status == 200
        await page.open_page("https://example.com/")
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


async def test_read_page_reports_no_status(fake_server: _FakeCdpServer, connected_client: CdpClient) -> None:
    """read_page loads nothing, so it never knows a status (the user may have navigated since)."""
    page = DeskBrowserPage(connected_client)
    assert (await page.open_page("https://example.com/")).status == 200
    assert (await page.read_page()).status is None


async def test_a_password_box_is_reported_as_a_password_field(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    fake_server._password_fields = 1
    result = await DeskBrowserPage(connected_client).read_page()
    assert (result.password_field, result.captcha_frame) == (True, False)


async def test_a_visible_captcha_frame_is_reported(fake_server: _FakeCdpServer, connected_client: CdpClient) -> None:
    fake_server._frame_srcs = (_AD_FRAME_SRC, _HCAPTCHA_SRC)
    result = await DeskBrowserPage(connected_client).read_page()
    assert (result.password_field, result.captcha_frame) == (False, True)


async def test_a_plain_page_has_no_password_field_and_no_captcha_frame(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    fake_server._frame_srcs = (_AD_FRAME_SRC,)
    result = await DeskBrowserPage(connected_client).read_page()
    assert (result.password_field, result.captcha_frame) == (False, False)


async def test_the_signals_are_dom_queries_on_the_bots_own_session(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    await DeskBrowserPage(connected_client).read_page()
    queries = [m for m in fake_server.received if m["method"] == "DOM.querySelectorAll"]
    assert [q["params"] for q in queries] == [
        {"nodeId": _ROOT_NODE_ID, "selector": STUCK_PASSWORD_SELECTOR},
        {"nodeId": _ROOT_NODE_ID, "selector": STUCK_CAPTCHA_FRAME_SELECTOR},
    ]
    assert {q["sessionId"] for q in queries} == {"session-1"}
    evaluates = [m for m in fake_server.received if m["method"] == "Runtime.evaluate"]
    assert all("contextId" in m["params"] for m in evaluates)      # only the front-tab probe's isolated world


async def test_an_invisible_recaptcha_frame_is_not_a_captcha_frame(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    """Review Focus 1: an invisible reCAPTCHA runs quietly behind many
    normal pages (a shop's checkout, a sign-up form) and must not make the
    bot Stuck. Chromium's selector engine does the excluding, so what
    matters is the exact selector sent; the fake DOM evaluates it."""
    fake_server._frame_srcs = (_INVISIBLE_RECAPTCHA_SRC,)
    page = DeskBrowserPage(connected_client)
    assert (await page.read_page()).captcha_frame is False
    sent = [m["params"]["selector"] for m in fake_server.received if m["method"] == "DOM.querySelectorAll"]
    assert sent == [STUCK_PASSWORD_SELECTOR, STUCK_CAPTCHA_FRAME_SELECTOR]
    assert ':not([src*="size=invisible"])' in STUCK_CAPTCHA_FRAME_SELECTOR
    fake_server._frame_srcs = (_INVISIBLE_RECAPTCHA_SRC, _VISIBLE_RECAPTCHA_SRC)
    assert (await page.read_page()).captcha_frame is True   # a visible checkbox on the same page still counts


async def test_a_page_whose_dom_cannot_be_read_still_returns_its_text(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    """A DOM error reply (the page navigating away mid-read) gives no
    signals instead of failing the read: KeeperDesk treats any CDP error as
    a dead connection and would replace the bot's tab, losing the page."""
    fake_server._dom_error = True
    result = await DeskBrowserPage(connected_client).read_page()
    assert "Welcome" in result.text
    assert (result.password_field, result.captcha_frame) == (False, False)


# -- page-text building (pure helpers) -----------------------------------


def test_build_page_text_skips_ignored_nodes_and_unreadable_roles() -> None:
    text, truncated = _build_page_text(_AX_NODES)
    assert "ignored heading" not in text
    assert "not readable, wrong role" not in text
    assert truncated is False


def test_build_page_text_collapses_immediate_repeats() -> None:
    text, _truncated = _build_page_text(_AX_NODES)
    assert text.count("Welcome") == 1


def test_build_page_text_skips_empty_names() -> None:
    text, _truncated = _build_page_text(_AX_NODES)
    assert text.splitlines().count("") == 0


def test_collapse_consecutive_repeats_only_collapses_adjacent_duplicates() -> None:
    assert _collapse_consecutive_repeats(["a", "a", "b", "a"]) == ["a", "b", "a"]


def test_build_page_text_truncates_at_the_page_text_limit() -> None:
    long_name = "x" * (PAGE_TEXT_LIMIT + 500)
    nodes = [{"role": {"value": "paragraph"}, "name": {"value": long_name}}]
    text, truncated = _build_page_text(nodes)
    assert truncated is True
    assert len(text) == PAGE_TEXT_LIMIT
