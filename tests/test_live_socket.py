"""The live screen's socket side (Computers 2.0, C1, Task 9): who counts as this Mac, the viewer count, and the
relay's two pumps. Small fakes only."""

from __future__ import annotations

import asyncio
import struct
from dataclasses import replace
from types import SimpleNamespace

import pytest
from starlette.datastructures import Address, Headers

from roost.config import load_config
from roost.constants import LIVE_VIEWERS_MAX, RFB_CLIENT_VERSION
from roost.desk.fake_screen import FakeScreen
from roost.gateway.live_socket import LiveViewers, peer_is_this_mac
from roost.gateway.routes.live import relay_screen


def _peer(host: str | None, headers: dict[str, str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(headers=Headers(headers=headers or {}),
                           client=None if host is None else Address(host, 50000))


@pytest.fixture
def config():
    return load_config()


@pytest.mark.parametrize(("host", "this_mac"), [
    ("127.0.0.1", True), ("::1", True), ("192.168.1.20", False), ("10.0.0.5", False),
    ("127.0.0.2", False), ("testclient", False),
])
def test_only_the_loopback_peer_is_this_mac(config, host, this_mac):
    assert peer_is_this_mac(_peer(host), config) is this_mac


def test_no_peer_at_all_is_not_this_mac(config):
    assert peer_is_this_mac(_peer(None), config) is False


def test_any_peer_in_the_gateway_container_is_this_mac(config):
    """Compose publishes the gateway on the Mac's 127.0.0.1 alone, so every peer the container sees is this Mac."""
    assert peer_is_this_mac(_peer("192.168.65.1"), replace(config, in_container=True)) is True


@pytest.mark.parametrize("header", ["X-Forwarded-For", "Forwarded", "X-Real-IP"])
def test_a_forwarded_connection_is_refused_even_from_this_mac(config, header):
    forwarded = _peer("127.0.0.1", {header: "203.0.113.7"})
    assert peer_is_this_mac(forwarded, config) is False
    assert peer_is_this_mac(forwarded, replace(config, in_container=True)) is False


def test_viewers_are_capped_per_bot_and_per_mode():
    viewers = LiveViewers()
    assert [viewers.enter("b1", "view") for _ in range(LIVE_VIEWERS_MAX + 1)] == [True] * LIVE_VIEWERS_MAX + [False]
    assert viewers.enter("b2", "view") is True            # another bot has its own count
    assert viewers.enter("b1", "control") is True and viewers.enter("b1", "control") is False
    viewers.leave("b1", "view")
    assert viewers.enter("b1", "view") is True
    for _ in range(5):
        viewers.leave("b3", "view")                       # leaving what was never entered is harmless
    assert viewers.enter("b3", "view") is True


class _Socket:
    """A WebSocket stand-in: ``incoming`` is what the browser sends, ``sent`` what the relay sent back."""

    def __init__(self, incoming: list[dict]) -> None:
        self._incoming: asyncio.Queue[dict] = asyncio.Queue()
        for event in incoming:
            self._incoming.put_nowait(event)
        self.sent: list[bytes] = []
        self.closed: tuple[int, str] | None = None

    async def receive(self) -> dict:
        return await self._incoming.get()

    def push(self, *events: dict) -> None:
        for event in events:
            self._incoming.put_nowait(event)

    async def send_bytes(self, data: bytes) -> None:
        self.sent.append(data)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = (code, reason)


def _bytes(data: bytes) -> dict:
    return {"type": "websocket.receive", "bytes": data}


HANDSHAKE = [RFB_CLIENT_VERSION, b"\x01", b"\x01"]
KEY = struct.pack(">BBxxI", 4, 1, 0x61)
POINTER = struct.pack(">BBHH", 5, 1, 1, 2)
REQUEST = struct.pack(">BBHHHH", 3, 0, 0, 0, 320, 200)


async def test_relay_screen_forwards_input_only_while_allowed():
    screen = FakeScreen()
    allowed = {"on": False}
    socket = _Socket([_bytes(b) for b in HANDSHAKE] + [_bytes(KEY), _bytes(POINTER)])
    task = asyncio.create_task(relay_screen(socket, screen, input_allowed=lambda: allowed["on"]))
    await asyncio.sleep(0.05)
    assert screen.received_input == 0                     # view: both dropped
    allowed["on"] = True
    socket.push(_bytes(KEY), _bytes(POINTER), {"type": "websocket.disconnect"})
    assert await asyncio.wait_for(task, 2) == "client"
    assert screen.received_input == 2


async def test_relay_screen_is_checked_per_message_not_per_connection():
    screen = FakeScreen()
    flips = iter([True, False, False])
    socket = _Socket([_bytes(b) for b in HANDSHAKE] + [_bytes(KEY + KEY + KEY), {"type": "websocket.disconnect"}])
    await asyncio.wait_for(relay_screen(socket, screen, input_allowed=lambda: next(flips, False)), 2)
    assert screen.received_input == 1


async def test_relay_screen_says_protocol_on_garbage_and_screen_when_the_computer_closes():
    socket = _Socket([_bytes(b"GET / HTTP/1.1\r\n")])
    assert await asyncio.wait_for(relay_screen(socket, FakeScreen(), input_allowed=lambda: False), 2) == "protocol"
    screen = FakeScreen()
    await screen.close()
    assert await asyncio.wait_for(relay_screen(_Socket([]), screen, input_allowed=lambda: False), 2) == "screen"


async def test_relay_screen_treats_a_text_frame_as_a_protocol_error():
    socket = _Socket([{"type": "websocket.receive", "text": "hello"}])
    assert await asyncio.wait_for(relay_screen(socket, FakeScreen(), input_allowed=lambda: False), 2) == "protocol"


async def test_relay_screen_drops_input_past_the_rate_cap():
    screen = FakeScreen()
    socket = _Socket([_bytes(b) for b in HANDSHAKE] + [_bytes(KEY * 600), {"type": "websocket.disconnect"}])
    await asyncio.wait_for(relay_screen(socket, screen, input_allowed=lambda: True), 2)
    assert 0 < screen.received_input < 600


async def test_input_held_by_the_teach_observer_is_dropped_if_control_was_given_back_meanwhile():
    """Review FAIL 3: input_allowed() is read again after on_input, so a press never lands after a hand-back."""
    screen = FakeScreen()
    allowed = {"on": True}

    async def observer(_message) -> None:
        allowed["on"] = False                               # given back while the page was being read

    socket = _Socket([_bytes(b) for b in HANDSHAKE] + [_bytes(KEY), {"type": "websocket.disconnect"}])
    await asyncio.wait_for(relay_screen(socket, screen, input_allowed=lambda: allowed["on"], on_input=observer), 2)
    assert screen.received_input == 0


TAILNET = "https://mac.example.ts.net"


def _tailnet_config(config):
    return replace(config, allowed_origins=(*config.allowed_origins, TAILNET), tailnet_origins=(TAILNET,))


@pytest.mark.parametrize("address", ["100.124.139.37", "100.64.0.1", "fd7a:115c:a1e0::1"])
def test_the_phone_through_tailscale_serve_is_this_mac(config, address):
    """`tailscale serve` (tailnet only) forwards the phone with its tailnet address and the tailnet origin."""
    phone = _peer("127.0.0.1", {"X-Forwarded-For": address, "Origin": TAILNET})
    assert peer_is_this_mac(phone, _tailnet_config(config)) is True
    assert peer_is_this_mac(phone, replace(_tailnet_config(config), in_container=True)) is True


@pytest.mark.parametrize("headers", [
    {"X-Forwarded-For": "203.0.113.7", "Origin": TAILNET},                  # a public address (Funnel, a proxy)
    {"X-Forwarded-For": "100.124.139.37, 203.0.113.7", "Origin": TAILNET},  # any public hop
    {"X-Forwarded-For": "100.128.0.1", "Origin": TAILNET},                  # just outside Tailscale's range
    {"X-Forwarded-For": "not-an-address", "Origin": TAILNET},
    {"X-Forwarded-For": "100.124.139.37", "Origin": "http://localhost:5173"},  # not the tailnet origin
    {"Forwarded": "for=100.124.139.37", "Origin": TAILNET},
    {"X-Forwarded-For": "100.124.139.37", "X-Real-IP": "203.0.113.7", "Origin": TAILNET},
])
def test_other_forwarded_connections_stay_refused(config, headers):
    assert peer_is_this_mac(_peer("127.0.0.1", headers), _tailnet_config(config)) is False


def test_a_tailnet_address_without_a_tailnet_origin_configured_is_refused(config):
    phone = _peer("127.0.0.1", {"X-Forwarded-For": "100.124.139.37", "Origin": TAILNET})
    assert peer_is_this_mac(phone, config) is False


async def test_a_viewer_that_leaves_has_its_close_code_logged(caplog):
    """Owner, 2026-11-01: the screen dropped "when the bot's page changes" and the log said only "ended by client".
    The viewer's own close code tells an app that closed it (1000/1001) from a broken link (1006)."""
    socket = _Socket([_bytes(b) for b in HANDSHAKE] + [{"type": "websocket.disconnect", "code": 1006}])
    with caplog.at_level("WARNING", logger="roost.gateway.routes.live"):
        assert await asyncio.wait_for(relay_screen(socket, FakeScreen(), input_allowed=lambda: False), 2) == "client"
    assert "viewer closed the live screen with code 1006" in caplog.text
