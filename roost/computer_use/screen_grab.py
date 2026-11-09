"""The whole-screen grab for a desktop look (full computer, Step 1; ``docs/plans/2026-10-23-roost-full-computer.md``).

When anything but Brave is in front, ``look`` shows the whole 1280x800 screen. The picture comes through the
keeper's VNC relay (``Desk.open_screen()``; Xvnc runs ``-AlwaysShared``, so the live viewer is not disturbed) with
a minimal RFB 3.8 client: the version, security None, a shared ClientInit, a 32-bit true-colour pixel format, Raw
encoding only and one non-incremental FramebufferUpdateRequest. Every length the server sends is checked against a
bound before anything is read, and the whole grab keeps to one deadline. It never sends a key or a pointer event.

``blackout`` then paints every visible Brave window black, so a page's fields and text never reach the model by
this side door: to see the browser, the bot brings it to the front and looks again.
"""

from __future__ import annotations

import asyncio
import io
import struct
import time
from collections.abc import Sequence

from PIL import Image, ImageDraw

from roost.constants import (
    CU_IMAGE_MAX_BYTES,
    CU_SCREEN_CUT_TEXT_MAX,
    CU_SCREEN_GRAB_TIMEOUT_S,
    CU_SCREEN_NAME_MAX,
    CU_SCREEN_RECTS_MAX,
    CU_VIEW_MAX_H,
    CU_VIEW_MAX_W,
    RFB_CLIENT_VERSION,
)
from roost.desk import ScreenStream

Rect = tuple[int, int, int, int]

_SECURITY_NONE = 1
_SHARED = b"\x01"
_BYTES_PER_PIXEL = 4
# 32 bits per pixel, depth 24, little-endian, true colour, 255 a channel, red at bit 16, green 8, blue 0: B G R pad.
_PIXEL_FORMAT = struct.pack(">BBBBHHHBBBxxx", 32, 24, 0, 1, 255, 255, 255, 16, 8, 0)
_SET_PIXEL_FORMAT = struct.pack(">Bxxx", 0) + _PIXEL_FORMAT
_SET_ENCODINGS_RAW = struct.pack(">BxHi", 2, 1, 0)
_RAW = 0
_UPDATE, _COLOUR_MAP, _BELL, _CUT_TEXT = 0, 1, 2, 3
_BLACK = (0, 0, 0)
_RAW_MODE = "BGRX"
_JPEG_QUALITY_STEPS = (60, 50, 40, 30, 20)


class ScreenGrabError(RuntimeError):
    """The grab failed: the server broke a rule, closed, or ran out of time. Says which, never a byte."""


class _Reader:
    """Exact reads from the stream, all within one deadline."""

    def __init__(self, stream: ScreenStream, deadline: float) -> None:
        self._stream, self._deadline = stream, deadline
        self._buffer = bytearray()

    async def read(self, size: int) -> bytes:
        while len(self._buffer) < size:
            left = self._deadline - time.monotonic()
            if left <= 0:
                raise ScreenGrabError("the screen did not answer in time")
            try:
                chunk = await asyncio.wait_for(self._stream.receive(), timeout=left)
            except asyncio.TimeoutError:
                raise ScreenGrabError("the screen did not answer in time") from None
            if not chunk:
                raise ScreenGrabError("the screen closed")
            self._buffer.extend(chunk)
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data

    async def u8(self) -> int:
        return (await self.read(1))[0]

    async def u16(self) -> int:
        return struct.unpack(">H", await self.read(2))[0]

    async def u32(self) -> int:
        return struct.unpack(">I", await self.read(4))[0]


def _require(ok: bool, why: str) -> None:
    if not ok:
        raise ScreenGrabError(why)


async def _handshake(reader: _Reader, stream: ScreenStream) -> tuple[int, int]:
    """Version, security None, shared ClientInit, ServerInit. Returns the screen's width and height."""
    _require((await reader.read(12)).startswith(b"RFB 003."), "not an RFB server")
    await stream.send(RFB_CLIENT_VERSION)
    count = await reader.u8()
    if count == 0:
        _require(await reader.u32() <= CU_SCREEN_NAME_MAX, "a refusal too long to read")
        raise ScreenGrabError("the screen refused the connection")
    _require(_SECURITY_NONE in await reader.read(count), "no security type the grab can use")
    await stream.send(bytes([_SECURITY_NONE]))
    _require(await reader.u32() == 0, "the screen refused the connection")
    await stream.send(_SHARED)
    width, height = await reader.u16(), await reader.u16()
    _require(0 < width <= CU_VIEW_MAX_W and 0 < height <= CU_VIEW_MAX_H, "a screen size out of bounds")
    await reader.read(len(_PIXEL_FORMAT))
    name_length = await reader.u32()
    _require(name_length <= CU_SCREEN_NAME_MAX, "a desktop name too long")
    await reader.read(name_length)
    return width, height


async def _rect(reader: _Reader, image: Image.Image) -> None:
    x, y, w, h = struct.unpack(">HHHH", await reader.read(8))
    encoding = struct.unpack(">i", await reader.read(4))[0]
    _require(encoding == _RAW, "an encoding the grab did not ask for")
    _require(x + w <= image.width and y + h <= image.height, "a rectangle outside the screen")
    if w and h:
        pixels = await reader.read(w * h * _BYTES_PER_PIXEL)
        image.paste(Image.frombuffer("RGB", (w, h), pixels, "raw", _RAW_MODE, 0, 1), (x, y))


async def _skip_message(reader: _Reader, kind: int) -> None:
    """A colour map, a bell or a cut text before the frame: read past it, within bounds."""
    if kind == _COLOUR_MAP:
        await reader.read(3)
        await reader.read(await reader.u16() * 6)
    elif kind == _CUT_TEXT:
        await reader.read(3)
        length = await reader.u32()
        _require(length <= CU_SCREEN_CUT_TEXT_MAX, "a cut text too long")
        await reader.read(length)
    else:
        _require(kind == _BELL, "a message the grab does not know")


async def _frame(reader: _Reader, width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height), _BLACK)
    while (kind := await reader.u8()) != _UPDATE:
        await _skip_message(reader, kind)
    await reader.read(1)
    rects = await reader.u16()
    _require(rects <= CU_SCREEN_RECTS_MAX, "too many rectangles")
    for _ in range(rects):
        await _rect(reader, image)
    return image


async def grab_screen(stream: ScreenStream, *, timeout_s: float = CU_SCREEN_GRAB_TIMEOUT_S) -> Image.Image:
    """One whole-screen picture from ``stream``, which is always closed after."""
    reader = _Reader(stream, time.monotonic() + timeout_s)
    try:
        width, height = await _handshake(reader, stream)
        await stream.send(_SET_PIXEL_FORMAT + _SET_ENCODINGS_RAW
                          + struct.pack(">BBHHHH", 3, 0, 0, 0, width, height))
        return await _frame(reader, width, height)
    except (OSError, struct.error, ValueError) as exc:
        raise ScreenGrabError(f"the screen grab failed ({type(exc).__name__})") from None
    finally:
        await stream.close()


def blackout(image: Image.Image, rects: Sequence[Rect]) -> Image.Image:
    """A copy of ``image`` with every rect (left, top, width, height) painted black, clipped to the picture."""
    out = image.copy()
    draw = ImageDraw.Draw(out)
    for left, top, width, height in rects:
        right, bottom = min(out.width, left + width) - 1, min(out.height, top + height) - 1
        left, top = max(0, left), max(0, top)
        if right >= left and bottom >= top:
            draw.rectangle((left, top, right, bottom), fill=_BLACK)
    return out


def desktop_jpeg(image: Image.Image, rects: Sequence[Rect]) -> bytes:
    """The blacked-out screen as a JPEG within ``CU_IMAGE_MAX_BYTES`` (quality steps down, then it shrinks)."""
    shown = blackout(image.convert("RGB"), rects)
    shown.thumbnail((CU_VIEW_MAX_W, CU_VIEW_MAX_H))
    while True:
        for quality in _JPEG_QUALITY_STEPS:
            out = io.BytesIO()
            shown.save(out, format="JPEG", quality=quality)
            if out.tell() <= CU_IMAGE_MAX_BYTES:
                return out.getvalue()
        shown = shown.resize((max(1, shown.width * 3 // 4), max(1, shown.height * 3 // 4)))
