"""The fake screen (Computers 2.0, C1, Task 8): a tiny RFB 3.8 server for tests and the E2E."""

from __future__ import annotations

import struct

from roost.constants import FAKE_SCREEN_HEIGHT, FAKE_SCREEN_WIDTH, RFB_CLIENT_VERSION
from roost.desk import DeskAsleep, DeskUnavailable
from roost.desk.fake import FakeDesk
from roost.desk.fake_screen import FakeScreen

import pytest


async def _handshake(screen: FakeScreen) -> bytes:
    assert await screen.receive() == b"RFB 003.008\n"
    await screen.send(RFB_CLIENT_VERSION)
    assert await screen.receive() == b"\x01\x01"                 # one security type: None
    await screen.send(b"\x01")
    assert await screen.receive() == b"\x00\x00\x00\x00"         # SecurityResult OK
    await screen.send(b"\x01")                                    # ClientInit
    return await screen.receive()


async def test_the_fake_screen_speaks_rfb_3_8_and_sends_a_frame():
    screen = FakeScreen()
    init = await _handshake(screen)
    width, height = struct.unpack(">HH", init[:4])
    assert (width, height) == (FAKE_SCREEN_WIDTH, FAKE_SCREEN_HEIGHT)
    assert init[4:20][0] == 32 and init.endswith(b"Fake computer")
    assert struct.unpack(">I", init[20:24])[0] == len(b"Fake computer")

    await screen.send(struct.pack(">BBHHHH", 3, 0, 0, 0, FAKE_SCREEN_WIDTH, FAKE_SCREEN_HEIGHT))
    frame = await screen.receive()
    kind, count = struct.unpack(">BxH", frame[:4])
    assert (kind, count) == (0, 1)
    x, y, w, h, encoding = struct.unpack(">HHHHi", frame[4:16])
    assert (x, y, w, h, encoding) == (0, 0, FAKE_SCREEN_WIDTH, FAKE_SCREEN_HEIGHT, 0)
    assert len(frame) == 16 + FAKE_SCREEN_WIDTH * FAKE_SCREEN_HEIGHT * 4
    await screen.close()
    assert await screen.receive() == b""


async def test_it_counts_input_but_keeps_no_bytes():
    screen = FakeScreen()
    await _handshake(screen)
    key = struct.pack(">BBxxI", 4, 1, 0x70)
    pointer = struct.pack(">BBHH", 5, 1, 3, 4)
    await screen.send(key + pointer)
    assert screen.received_input == 2
    held = repr(vars(screen)).encode()
    assert key not in held and pointer not in held and b"hunter2" not in held


async def test_an_incremental_request_gets_no_frame_and_a_closed_screen_ignores_sends():
    screen = FakeScreen()
    await _handshake(screen)
    await screen.send(struct.pack(">BBHHHH", 3, 1, 0, 0, 8, 8))
    await screen.close()
    await screen.send(struct.pack(">BBxxI", 4, 1, 0x70))
    assert screen.received_input == 0 and await screen.receive() == b""


async def test_a_sleeping_fake_desk_has_no_screen():
    desk = FakeDesk("bot-1", computer="linux")
    with pytest.raises(DeskAsleep):
        await desk.open_screen()
    await desk.start_browser()
    screen = await desk.open_screen()
    assert isinstance(screen, FakeScreen) and await screen.receive() == b"RFB 003.008\n"
    assert await desk.open_screen() is not screen
    await desk.stop_browser()
    with pytest.raises(DeskAsleep):
        await desk.open_screen()


async def test_a_mac_brave_fake_desk_has_no_screen():
    with pytest.raises(DeskUnavailable):
        await FakeDesk("bot-1").open_screen()


async def test_an_unavailable_fake_desk_has_no_screen():
    desk = FakeDesk("bot-1", computer="linux", force_unavailable=True)
    with pytest.raises(DeskUnavailable):
        await desk.open_screen()
