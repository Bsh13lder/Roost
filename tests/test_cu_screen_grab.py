"""Full computer, Step 1: the whole-screen grab (a minimal RFB client) and the black-out of Brave's windows.

Against ``roost/desk/fake_screen.py`` and small scripted servers; nothing reaches a real computer."""

from __future__ import annotations

import asyncio
import io
import struct

import pytest
from PIL import Image

from roost.computer_use.screen_grab import ScreenGrabError, blackout, desktop_jpeg, grab_screen
from roost.constants import FAKE_SCREEN_HEIGHT, FAKE_SCREEN_WIDTH
from roost.desk.fake_screen import FakeScreen

GREEN = (0x40, 0x90, 0x40)              # FakeScreen's one pixel colour (B G R pad on the wire)
_FORMAT = struct.pack(">BBBBHHHBBBxxx", 32, 24, 0, 1, 255, 255, 255, 16, 8, 0)


class Scripted:
    """A server that sends fixed chunks, then closes (or hangs), and records what the client sent."""

    def __init__(self, *chunks: bytes, hang: bool = False) -> None:
        self.chunks, self.hang = list(chunks), hang
        self.sent: list[bytes] = []
        self.closed = False

    async def send(self, data: bytes) -> None:
        self.sent.append(bytes(data))

    async def receive(self) -> bytes:
        if self.chunks:
            return self.chunks.pop(0)
        if self.hang:
            await asyncio.sleep(3600)
        return b""

    async def close(self) -> None:
        self.closed = True


def _hello(width: int = 4, height: int = 2, name: bytes = b"x", types: bytes = b"\x01\x01") -> list[bytes]:
    init = struct.pack(">HH", width, height) + _FORMAT + struct.pack(">I", len(name)) + name
    return [b"RFB 003.008\n", types, b"\x00\x00\x00\x00", init]


def _update(*rects: tuple[int, int, int, int, int, bytes]) -> bytes:
    out = struct.pack(">BxH", 0, len(rects))
    for x, y, w, h, encoding, pixels in rects:
        out += struct.pack(">HHHHi", x, y, w, h, encoding) + pixels
    return out


async def test_grab_reads_the_fake_computer_s_whole_screen():
    screen = FakeScreen()
    image = await grab_screen(screen, timeout_s=5)
    assert image.size == (FAKE_SCREEN_WIDTH, FAKE_SCREEN_HEIGHT)
    assert image.getpixel((0, 0)) == GREEN and image.getpixel((FAKE_SCREEN_WIDTH - 1, FAKE_SCREEN_HEIGHT - 1)) == GREEN
    assert screen.received_input == 0                    # a grab never sends a key or a pointer event


async def test_grab_closes_the_stream_and_asks_raw_shared_non_incremental():
    red = b"\x00\x00\xff\x00" * 8                         # B G R pad
    server = Scripted(*_hello(), b"\x02", _update((0, 0, 4, 2, 0, red)))     # a bell first, then the frame
    image = await grab_screen(server, timeout_s=5)
    assert image.getpixel((3, 1)) == (255, 0, 0) and server.closed
    sent = b"".join(server.sent)
    assert sent.startswith(b"RFB 003.008\n\x01\x01")      # version, security None, ClientInit shared
    assert struct.pack(">BxHi", 2, 1, 0) in sent          # SetEncodings: Raw only
    assert sent.endswith(struct.pack(">BBHHHH", 3, 0, 0, 0, 4, 2))


async def test_a_frame_in_pieces_and_two_rects_is_assembled():
    left, right = b"\x00\xff\x00\x00" * 4, b"\xff\x00\x00\x00" * 4
    frame = _update((0, 0, 2, 2, 0, left), (2, 0, 2, 2, 0, right))
    server = Scripted(*_hello(), frame[:7], frame[7:30], frame[30:])
    image = await grab_screen(server, timeout_s=5)
    assert image.getpixel((0, 0)) == (0, 255, 0) and image.getpixel((3, 1)) == (0, 0, 255)


@pytest.mark.parametrize("chunks", [
    [b"HTTP/1.1 200\n"],                                                 # not RFB
    _hello(types=b"\x01\x02"),                                           # no None security
    [*_hello()[:1], b"\x00", struct.pack(">I", 10**9)],                  # a refusal with a huge reason
    [*_hello()[:2], b"\x00\x00\x00\x01"],                                # security failed
    _hello(width=5000),                                                  # wider than the screen can be
    _hello(height=0),
    [*_hello()[:3], struct.pack(">HH", 4, 2) + _FORMAT + struct.pack(">I", 10**6)],   # a giant name
    [*_hello(), _update((0, 0, 4, 2, 7, b""))],                          # not Raw
    [*_hello(), _update((2, 0, 4, 2, 0, b""))],                          # outside the screen
    [*_hello(), struct.pack(">BxH", 0, 60000)],                          # too many rects
    [*_hello(), b"\x09"],                                                # an unknown message
    [*_hello(), b"\x03\x00\x00\x00" + struct.pack(">I", 10**8)],         # a huge cut text
    [*_hello(), _update((0, 0, 4, 2, 0, b"\x00" * 10))],                 # the far end closes mid-frame
])
async def test_a_strange_server_fails_the_grab(chunks):
    server = Scripted(*chunks)
    with pytest.raises(ScreenGrabError):
        await grab_screen(server, timeout_s=5)
    assert server.closed


async def test_a_silent_server_runs_out_of_time():
    server = Scripted(b"RFB 003.008\n", hang=True)
    with pytest.raises(ScreenGrabError):
        await grab_screen(server, timeout_s=0.05)
    assert server.closed


def test_blackout_paints_every_browser_window_and_clips_off_screen_parts():
    image = Image.new("RGB", (100, 50), (200, 200, 200))
    out = blackout(image, ((10, 10, 20, 10), (-30, 40, 50, 30)))
    assert out.getpixel((15, 15)) == (0, 0, 0) and out.getpixel((0, 45)) == (0, 0, 0)
    assert out.getpixel((5, 5)) == (200, 200, 200) and out.getpixel((60, 45)) == (200, 200, 200)
    assert image.getpixel((15, 15)) == (200, 200, 200)    # the input image is left as it was


def test_desktop_jpeg_is_a_jpeg_within_the_caps():
    image = Image.new("RGB", (1280, 800), (10, 120, 200))
    data = desktop_jpeg(image, ((0, 0, 640, 800),))
    with Image.open(io.BytesIO(data)) as shown:
        assert shown.format == "JPEG" and shown.size == (1280, 800)
        assert shown.convert("RGB").getpixel((100, 100))[2] < 30          # the browser half is black
