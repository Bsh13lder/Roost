"""Tests for the CDP pipe relay: ``roost.keeper.pipe_relay`` directly, and
the ``/desks/{bot_id}/cdp`` WebSocket route it's wired into
(``roost.keeper.app``).

Every test here uses a fake pipe peer -- two real ``os.pipe()`` pairs
standing in for the ends Brave itself would hold, per the Task 6 brief --
so nothing here ever starts a real browser. The real Brave round trip
(``Browser.getVersion`` / ``Target.createTarget`` over a token-authed
connection) is ``tests/test_relay_real.py``, marker ``desk``.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from pathlib import Path

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from roost.config import RoostConfig
from roost.keeper.app import create_app
from roost.keeper.browsers import BrowserHandle
from roost.keeper.pipe_relay import PipeRelay, RelayRegistry, tokens_match

_VALID_BOT_ID = "88888888-8888-4888-8888-888888888888"
_WRONG_TOKEN_BOT_ID = "99999999-9999-4999-8999-999999999999"
_NOT_RUNNING_BOT_ID = "77777777-7777-4777-8777-777777777777"


class _FakePipePeer:
    """The 'browser side' of a fake CDP pipe pair: two real ``os.pipe()``s,
    with the keeper's ends wrapped into a ``BrowserHandle`` and the
    opposite ends (the ones Brave itself would hold) driven directly by
    the test as plain blocking reads/writes."""

    def __init__(self) -> None:
        self.cmd_r, self.cmd_w = os.pipe()  # keeper writes commands -> cmd_w; browser reads cmd_r
        self.evt_r, self.evt_w = os.pipe()  # browser writes events -> evt_w; keeper reads evt_r

    def handle(self, *, pid: int = 4242, token: str = "tok") -> BrowserHandle:
        return BrowserHandle(pid=pid, cdp_token=token, read_fd=self.evt_r, write_fd=self.cmd_w)

    def read_command(self, max_bytes: int = 4096) -> bytes:
        return os.read(self.cmd_r, max_bytes)

    def write_event(self, data: bytes) -> None:
        os.write(self.evt_w, data)

    def close_all(self) -> None:
        for fd in (self.cmd_r, self.cmd_w, self.evt_r, self.evt_w):
            with contextlib.suppress(OSError):
                os.close(fd)


@pytest.fixture
def pipe_pair():
    peer = _FakePipePeer()
    yield peer
    peer.close_all()


# ---------------------------------------------------------------------------
# PipeRelay, exercised directly against the fake pipe peer
# ---------------------------------------------------------------------------


async def test_send_writes_the_frame_with_a_trailing_nul(pipe_pair):
    relay = PipeRelay(pipe_pair.handle())
    try:
        await relay.send('{"id":1,"method":"Browser.getVersion"}')
        assert pipe_pair.read_command() == b'{"id":1,"method":"Browser.getVersion"}\0'
    finally:
        relay.close()


async def test_iteration_yields_a_nul_terminated_reply_decoded_without_the_nul(pipe_pair):
    relay = PipeRelay(pipe_pair.handle())
    try:
        pipe_pair.write_event(b'{"id":1,"result":{}}\0')
        text = await asyncio.wait_for(relay.__anext__(), timeout=2)
        assert text == '{"id":1,"result":{}}'
    finally:
        relay.close()


async def test_one_read_carrying_two_frames_yields_both_in_order(pipe_pair):
    relay = PipeRelay(pipe_pair.handle())
    try:
        pipe_pair.write_event(b'{"a":1}\0{"b":2}\0')
        first = await asyncio.wait_for(relay.__anext__(), timeout=2)
        second = await asyncio.wait_for(relay.__anext__(), timeout=2)
        assert (first, second) == ('{"a":1}', '{"b":2}')
    finally:
        relay.close()


async def test_a_frame_split_across_two_writes_is_reassembled(pipe_pair):
    relay = PipeRelay(pipe_pair.handle())
    try:
        pipe_pair.write_event(b'{"a":')
        await asyncio.sleep(0.05)
        pipe_pair.write_event(b'1}\0')
        text = await asyncio.wait_for(relay.__anext__(), timeout=2)
        assert text == '{"a":1}'
    finally:
        relay.close()


async def test_browser_side_eof_ends_iteration(pipe_pair):
    relay = PipeRelay(pipe_pair.handle())
    os.close(pipe_pair.evt_w)  # the browser's write end going away -> EOF on handle.read_fd
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(relay.__anext__(), timeout=2)


async def test_close_ends_iteration_even_with_no_eof(pipe_pair):
    relay = PipeRelay(pipe_pair.handle())
    relay.close()
    with pytest.raises(StopAsyncIteration):
        await relay.__anext__()


async def test_invalid_utf8_frame_ends_the_relay(pipe_pair):
    relay = PipeRelay(pipe_pair.handle())
    try:
        pipe_pair.write_event(b"\xff\xfe\0")  # not valid UTF-8
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(relay.__anext__(), timeout=2)
    finally:
        relay.close()


async def test_a_genuine_read_error_closes_the_relay_instead_of_crashing(pipe_pair):
    relay = PipeRelay(pipe_pair.handle())
    os.close(pipe_pair.evt_r)  # the relay's own read fd, yanked out from under it
    # Simulates the loop invoking the readiness callback on a now-bad fd --
    # not reliably reproducible by just closing the fd and waiting, since
    # closing it also deregisters it from the selector on most platforms.
    relay._on_readable()
    with pytest.raises(StopAsyncIteration):
        await relay.__anext__()


async def test_close_is_idempotent(pipe_pair):
    relay = PipeRelay(pipe_pair.handle())
    relay.close()
    relay.close()  # must not raise or double-push the sentinel in a way that breaks iteration
    with pytest.raises(StopAsyncIteration):
        await relay.__anext__()


async def test_a_superseded_relays_close_never_evicts_the_handover_winners_reader(pipe_pair):
    """Reproduces the real-process handover bug (fix round 1, finding 2):
    a second ``PipeRelay`` wrapping the same handle (a WS takeover)
    silently replaces the first's ``add_reader`` callback on the shared
    ``read_fd`` -- that's normal asyncio behaviour, not the bug. The bug
    is the *first* (superseded) relay's own ``close()``, run later by the
    old connection's cleanup, calling ``remove_reader`` unconditionally
    and deregistering whatever is CURRENTLY there: the second relay's
    callback. This must be exercised on one shared event loop, like the
    real single-process keeper -- Starlette's ``TestClient`` gives each
    ``websocket_connect()`` its own anyio portal/event loop, which hides
    this bug entirely (two different loops never collide on the fd), so
    a WS-route-level test through ``TestClient`` would pass whether or
    not this fix exists and isn't a real regression guard."""
    handle = pipe_pair.handle()
    first = PipeRelay(handle)
    second = PipeRelay(handle)  # takes over the same fd, as a real handover would
    first.close()  # the superseded connection's own cleanup, running after the handover
    try:
        pipe_pair.write_event(b'{"id":1,"result":{}}\0')
        text = await asyncio.wait_for(second.__anext__(), timeout=2)
        assert text == '{"id":1,"result":{}}'
    finally:
        second.close()


# ---------------------------------------------------------------------------
# tokens_match
# ---------------------------------------------------------------------------


def test_tokens_match_exact_value_only():
    assert tokens_match("secret", "secret") is True
    assert tokens_match("secret", "wrong") is False
    assert tokens_match("secret", "") is False
    assert tokens_match("secret", None) is False


# ---------------------------------------------------------------------------
# RelayRegistry (one active relay client per bot)
# ---------------------------------------------------------------------------


class _FakeWebSocket:
    def __init__(self) -> None:
        self.close_codes: list[int] = []

    async def close(self, code: int = 1000) -> None:
        self.close_codes.append(code)


async def test_take_over_closes_the_previous_connection_with_4409():
    registry = RelayRegistry()
    first, second = _FakeWebSocket(), _FakeWebSocket()
    await registry.take_over("bot-1", first)
    await registry.take_over("bot-1", second)
    assert first.close_codes == [4409]
    assert second.close_codes == []


async def test_take_over_does_not_affect_other_bots():
    registry = RelayRegistry()
    bot_1, bot_2 = _FakeWebSocket(), _FakeWebSocket()
    await registry.take_over("bot-1", bot_1)
    await registry.take_over("bot-2", bot_2)
    assert bot_1.close_codes == []
    assert bot_2.close_codes == []


async def test_release_clears_the_current_holder():
    registry = RelayRegistry()
    first = _FakeWebSocket()
    await registry.take_over("bot-1", first)
    registry.release("bot-1", first)

    second = _FakeWebSocket()
    await registry.take_over("bot-1", second)
    assert second.close_codes == []  # nothing left registered to close


async def test_release_of_a_superseded_connection_is_a_noop():
    registry = RelayRegistry()
    first, second = _FakeWebSocket(), _FakeWebSocket()
    await registry.take_over("bot-1", first)
    await registry.take_over("bot-1", second)  # first is now superseded
    registry.release("bot-1", first)  # must not evict second's registration

    third = _FakeWebSocket()
    await registry.take_over("bot-1", third)
    assert second.close_codes == [4409]  # proves second was still the registered holder


# ---------------------------------------------------------------------------
# The WS route itself: /desks/{bot_id}/cdp
# ---------------------------------------------------------------------------


@pytest.fixture
def config(tmp_path: Path) -> RoostConfig:
    return RoostConfig(
        server_secret="x" * 32,
        database_dir=tmp_path / "data",
        desks_dir=tmp_path / "desks",
        keeper_secret="y" * 32,
    )


@pytest.fixture
def client(config: RoostConfig) -> TestClient:
    return TestClient(create_app(config))


def test_no_token_closes_4401(client: TestClient):
    client.app.state.launcher.get_handle = lambda bot_id: BrowserHandle(
        pid=1, cdp_token="right-token", read_fd=-1, write_fd=-1
    )
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/desks/{_VALID_BOT_ID}/cdp") as ws:
            ws.receive_text()
    assert exc_info.value.code == 4401


def test_wrong_token_closes_4401(client: TestClient):
    client.app.state.launcher.get_handle = lambda bot_id: BrowserHandle(
        pid=1, cdp_token="right-token", read_fd=-1, write_fd=-1
    )
    headers = {"x-roost-desk-token": "wrong-token"}
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/desks/{_WRONG_TOKEN_BOT_ID}/cdp", headers=headers) as ws:
            ws.receive_text()
    assert exc_info.value.code == 4401


def test_bot_not_running_closes_4404(client: TestClient):
    client.app.state.launcher.get_handle = lambda bot_id: None
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/desks/{_NOT_RUNNING_BOT_ID}/cdp") as ws:
            ws.receive_text()
    assert exc_info.value.code == 4404


def test_malformed_bot_id_closes_with_a_distinct_code_not_4404(client: TestClient):
    """Fix round 1, finding 1: a malformed bot_id must not silently fall
    through to the generic 'not running' 4404 -- it gets its own close
    code, same as the signed HTTP routes 400 on the same check. Rigged
    so that if the format check were skipped, get_handle would be
    reached and report 'running' (not None), proving a 4404 here could
    only come from the not-running branch, not this one."""
    calls: list[str] = []

    def _get_handle(bot_id: str) -> BrowserHandle:
        calls.append(bot_id)
        return BrowserHandle(pid=1, cdp_token="tok", read_fd=-1, write_fd=-1)

    client.app.state.launcher.get_handle = _get_handle
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/desks/not-a-uuid/cdp") as ws:
            ws.receive_text()
    assert exc_info.value.code not in (4401, 4404, 4409)
    assert calls == []  # the handle lookup must never be reached for a malformed id


def test_frame_round_trips_through_the_full_ws_route(client: TestClient, pipe_pair):
    handle = pipe_pair.handle(token="secret-token")
    client.app.state.launcher.get_handle = lambda bot_id: handle
    headers = {"x-roost-desk-token": "secret-token"}

    with client.websocket_connect(f"/desks/{_VALID_BOT_ID}/cdp", headers=headers) as ws:
        ws.send_text('{"id":1,"method":"Browser.getVersion"}')
        assert pipe_pair.read_command() == b'{"id":1,"method":"Browser.getVersion"}\0'

        pipe_pair.write_event(b'{"id":1,"result":{"product":"Brave"}}\0')
        assert ws.receive_text() == '{"id":1,"result":{"product":"Brave"}}'

        # Let the server-side handler actually unwind (cancel its pump
        # tasks, release the registry slot) before the test client's own
        # __exit__ force-cancels the connection's task -- the TestClient's
        # in-memory transport has no notion of a real socket close
        # unwinding both directions together, so without this the
        # teardown can race the handler's own cleanup (harmless in a real
        # ASGI server, but flaky against this synchronous test harness).
        ws.close()
        time.sleep(0.2)


def test_second_connection_for_the_same_bot_closes_the_first_with_4409(client: TestClient, pipe_pair):
    handle = pipe_pair.handle(token="tok")
    client.app.state.launcher.get_handle = lambda bot_id: handle
    headers = {"x-roost-desk-token": "tok"}

    with client.websocket_connect(f"/desks/{_VALID_BOT_ID}/cdp", headers=headers) as first_ws:
        with client.websocket_connect(f"/desks/{_VALID_BOT_ID}/cdp", headers=headers) as second_ws:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                first_ws.receive_text()
            assert exc_info.value.code == 4409

            # The 4409 close only pushed a message on first_ws's *send*
            # side; its server-side handler is still parked on its own
            # receive() until the client side disconnects too (see note
            # above) -- close it explicitly so that handler's cleanup
            # finishes before either connection's teardown force-cancels it.
            first_ws.close()
            time.sleep(0.2)
            second_ws.close()
            time.sleep(0.2)
