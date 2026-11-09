"""``FakeScreen``: a tiny RFB 3.8 server standing in for a bot's computer in tests and the E2E.

It is a ``ScreenStream``. ``receive()`` gives the server's bytes (the version line first), ``send()`` takes the
client's. Security is None; ``ServerInit`` is ``FAKE_SCREEN_WIDTH`` x ``FAKE_SCREEN_HEIGHT``, 32 bits per pixel,
named "Fake computer"; a non-incremental ``FramebufferUpdateRequest`` gets one Raw rectangle of the whole screen
in one colour. It counts input messages (``received_input``) and keeps none of their bytes.
"""

from __future__ import annotations

import asyncio
import struct

from roost.constants import FAKE_SCREEN_HEIGHT, FAKE_SCREEN_WIDTH
from roost.desk.rfb import RfbClientFilter

_SERVER_VERSION = b"RFB 003.008\n"
_SECURITY_TYPES = b"\x01\x01"              # one type: None
_SECURITY_OK = b"\x00\x00\x00\x00"
_NAME = b"Fake computer"
_PIXEL_FORMAT = struct.pack(">BBBBHHHBBBxxx", 32, 24, 0, 1, 255, 255, 255, 16, 8, 0)
_PIXEL = b"\x40\x90\x40\x00"                # one green pixel, B G R pad
_RAW = 0


def _server_init() -> bytes:
    return struct.pack(">HH", FAKE_SCREEN_WIDTH, FAKE_SCREEN_HEIGHT) + _PIXEL_FORMAT + struct.pack(">I", len(_NAME)) + _NAME


def _frame() -> bytes:
    header = struct.pack(">BxH", 0, 1) + struct.pack(">HHHHi", 0, 0, FAKE_SCREEN_WIDTH, FAKE_SCREEN_HEIGHT, _RAW)
    return header + _PIXEL * (FAKE_SCREEN_WIDTH * FAKE_SCREEN_HEIGHT)


class FakeScreen:
    def __init__(self) -> None:
        self.received_input = 0              # a count only; the bytes are never kept
        self._filter = RfbClientFilter()
        self._outbox: asyncio.Queue[bytes] = asyncio.Queue()
        self._outbox.put_nowait(_SERVER_VERSION)
        self._closed = False
        self._secured = False
        try:
            self._loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

    async def send(self, data: bytes) -> None:
        if self._closed:
            return
        for message in self._filter.feed(data):
            self.received_input += int(message.is_input)
            self._answer(message.kind, message.data)

    def _answer(self, kind: str, data: bytes) -> None:
        if kind == "handshake":
            self._answer_handshake(data)
        elif kind == "update_request" and data[1] == 0:       # non-incremental: the whole screen
            self._outbox.put_nowait(_frame())

    def _answer_handshake(self, data: bytes) -> None:
        if data.startswith(b"RFB"):
            self._outbox.put_nowait(_SECURITY_TYPES)
        elif not self._secured:
            self._secured = True
            self._outbox.put_nowait(_SECURITY_OK)
        else:                                                 # ClientInit
            self._outbox.put_nowait(_server_init())

    async def receive(self) -> bytes:
        if self._closed and self._outbox.empty():
            return b""
        return await self._outbox.get()

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._outbox.put_nowait(b"")

    def close_from_far_end(self) -> None:
        """The computer stops answering: ``receive()`` returns ``b""``. Safe to call from another thread."""
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._outbox.put_nowait, b"")
        else:
            self._outbox.put_nowait(b"")
