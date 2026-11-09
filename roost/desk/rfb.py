"""The RFB client filter: what a browser may send to a bot's screen (Computers 2.0, C1, Task 8).

Everything a browser sends toward Xvnc passes through ``RfbClientFilter``. It reads the stream as RFB 3.8 and
cuts it into whole messages, each with its exact bytes. ``verdict`` then says what happens to one: input
(``KeyEvent``, ``PointerEvent``, ``ClientCutText``, the QEMU extended key event) goes through only when the
caller says input is allowed *at that moment*; ``SetDesktopSize`` and xvp never do; a client cut-text with a
negative length (the extended clipboard) never does. The filter fails closed: a client version other than
``RFB 003.008``, a security type other than None, an unknown message type, an over-long message or a stream that
stops making sense raises ``RfbProtocolError``, and the caller closes the socket.

Nothing here logs. ``RfbProtocolError`` names the kind of message, never a byte of what was sent: keystrokes
and pastes can be passwords.
"""

from __future__ import annotations

import struct
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from roost.constants import (
    LIVE_INPUT_MAX_PER_SECOND,
    LIVE_INPUT_RATE_WINDOW_S,
    LIVE_PASTE_MAX_CHARS,
    RFB_CLIENT_VERSION,
    RFB_EXT_CLIPBOARD_ENCODING,
    RFB_FENCE_MAX,
    RFB_SECURITY_NONE,
    RFB_SET_ENCODINGS_MAX,
)

RfbVerdict = Literal["forward", "drop", "close"]
RfbKind = Literal["handshake", "set_pixel_format", "set_encodings", "update_request", "key", "pointer",
                  "cut_text", "continuous_updates", "fence", "desktop_size", "xvp", "qemu_key"]

_BUFFER_MAX = 64 * 1024              # a whole message must fit in this much
_CLIENT_INIT_LENGTH = 1
_SECURITY_LENGTH = 1
_SET_PIXEL_FORMAT, _SET_ENCODINGS, _UPDATE_REQUEST, _KEY, _POINTER, _CUT_TEXT = 0, 2, 3, 4, 5, 6
_CONTINUOUS_UPDATES, _FENCE, _XVP, _DESKTOP_SIZE, _QEMU = 150, 248, 250, 251, 255
_QEMU_EXTENDED_KEY = 0
_ALWAYS_DROPPED: frozenset[RfbKind] = frozenset({"desktop_size", "xvp"})
_FIXED_LENGTHS = {_SET_PIXEL_FORMAT: 20, _UPDATE_REQUEST: 10, _KEY: 8, _POINTER: 6, _CONTINUOUS_UPDATES: 10,
                  _XVP: 4}
_FIXED_KINDS: dict[int, RfbKind] = {
    _SET_PIXEL_FORMAT: "set_pixel_format", _UPDATE_REQUEST: "update_request", _KEY: "key", _POINTER: "pointer",
    _CONTINUOUS_UPDATES: "continuous_updates", _XVP: "xvp",
}
_EXT_CLIPBOARD = struct.pack(">i", RFB_EXT_CLIPBOARD_ENCODING)


class RfbProtocolError(ValueError):
    """The stream broke the filter's rules. Names a kind of message, never the bytes."""


@dataclass(frozen=True)
class RfbMessage:
    kind: RfbKind
    data: bytes          # the exact bytes to forward (set_encodings may be rewritten)
    is_input: bool


def verdict(message: RfbMessage, input_allowed: bool) -> RfbVerdict:
    """What to do with one message. ``input_allowed`` is read by the caller per message, never cached."""
    if message.kind in _ALWAYS_DROPPED:
        return "drop"
    if message.kind == "cut_text" and struct.unpack(">i", message.data[4:8])[0] < 0:
        return "drop"                      # the extended clipboard: never forwarded
    if message.is_input:
        return "forward" if input_allowed else "drop"
    return "forward"


class RfbClientFilter:
    """Cuts the client-to-server stream into whole, checked messages. One per socket."""

    def __init__(self, *, paste_max: int = LIVE_PASTE_MAX_CHARS) -> None:
        self._paste_max = paste_max
        self._buffer = b""
        self._stage: Literal["version", "security", "init", "messages"] = "version"
        self._failed = False

    def feed(self, data: bytes) -> tuple[RfbMessage, ...]:
        """Whole messages from ``data`` plus what was waiting. A partial message waits for more bytes."""
        if self._failed:
            raise RfbProtocolError("the stream already failed")
        self._buffer += data
        messages: list[RfbMessage] = []
        try:
            while (message := self._next()) is not None:
                messages.append(message)
            if len(self._buffer) > _BUFFER_MAX:
                raise RfbProtocolError("a message is too long")
        except RfbProtocolError:
            self._failed = True
            self._buffer = b""
            raise
        return tuple(messages)

    def _take(self, size: int, kind: RfbKind, *, is_input: bool = False, data: bytes | None = None) -> RfbMessage:
        message = RfbMessage(kind, self._buffer[:size] if data is None else data, is_input)
        self._buffer = self._buffer[size:]
        return message

    def _next(self) -> RfbMessage | None:
        if self._stage == "messages":
            return self._next_message()
        return self._next_handshake()

    def _next_handshake(self) -> RfbMessage | None:
        if self._stage == "version":
            if len(self._buffer) < len(RFB_CLIENT_VERSION):
                return None
            if self._buffer[:len(RFB_CLIENT_VERSION)] != RFB_CLIENT_VERSION:
                raise RfbProtocolError("unsupported client version")
            self._stage = "security"
            return self._take(len(RFB_CLIENT_VERSION), "handshake")
        if len(self._buffer) < _SECURITY_LENGTH:
            return None
        if self._stage == "security":
            if self._buffer[0] != RFB_SECURITY_NONE:
                raise RfbProtocolError("unsupported security type")
            self._stage = "init"
            return self._take(_SECURITY_LENGTH, "handshake")
        self._stage = "messages"             # ClientInit: one byte, the shared flag
        return self._take(_CLIENT_INIT_LENGTH, "handshake")

    def _next_message(self) -> RfbMessage | None:
        if not self._buffer:
            return None
        kind_byte = self._buffer[0]
        fixed = _FIXED_LENGTHS.get(kind_byte)
        if fixed is not None:
            return self._whole(fixed, _FIXED_KINDS[kind_byte], is_input=kind_byte in (_KEY, _POINTER))
        parsers = {_SET_ENCODINGS: self._set_encodings, _CUT_TEXT: self._cut_text, _FENCE: self._fence,
                   _DESKTOP_SIZE: self._desktop_size, _QEMU: self._qemu}
        parser = parsers.get(kind_byte)
        if parser is None:
            raise RfbProtocolError(f"unknown message type {kind_byte}")
        return parser()

    def _whole(self, size: int, kind: RfbKind, *, is_input: bool = False) -> RfbMessage | None:
        return self._take(size, kind, is_input=is_input) if len(self._buffer) >= size else None

    def _set_encodings(self) -> RfbMessage | None:
        if len(self._buffer) < 4:
            return None
        count = struct.unpack(">H", self._buffer[2:4])[0]
        if count > RFB_SET_ENCODINGS_MAX:
            raise RfbProtocolError("set_encodings is too long")
        size = 4 + 4 * count
        if len(self._buffer) < size:
            return None
        encodings = [self._buffer[4 + 4 * i:8 + 4 * i] for i in range(count)]
        kept = [encoding for encoding in encodings if encoding != _EXT_CLIPBOARD]
        rewritten = self._buffer[:2] + struct.pack(">H", len(kept)) + b"".join(kept)
        return self._take(size, "set_encodings", data=rewritten)

    def _cut_text(self) -> RfbMessage | None:
        if len(self._buffer) < 8:
            return None
        length = struct.unpack(">i", self._buffer[4:8])[0]
        if length > self._paste_max:
            raise RfbProtocolError("a paste is too long")
        size = 8 + abs(length)
        if size > _BUFFER_MAX:
            raise RfbProtocolError("a clipboard message is too long")
        return self._whole(size, "cut_text", is_input=True)

    def _fence(self) -> RfbMessage | None:
        if len(self._buffer) < 9:
            return None
        if self._buffer[8] > RFB_FENCE_MAX:
            raise RfbProtocolError("a fence is too long")
        return self._whole(9 + self._buffer[8], "fence")

    def _desktop_size(self) -> RfbMessage | None:
        if len(self._buffer) < 8:
            return None
        return self._whole(8 + 16 * self._buffer[6], "desktop_size")

    def _qemu(self) -> RfbMessage | None:
        if len(self._buffer) < 2:
            return None
        if self._buffer[1] != _QEMU_EXTENDED_KEY:
            raise RfbProtocolError("unsupported QEMU message")
        return self._whole(12, "qemu_key", is_input=True)


class InputRateLimit:
    """At most ``limit`` input messages per ``LIVE_INPUT_RATE_WINDOW_S``; the rest are dropped."""

    def __init__(self, *, limit: int | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self._limit = LIVE_INPUT_MAX_PER_SECOND if limit is None else limit
        self._clock = clock
        self._stamps: deque[float] = deque()

    def allow(self) -> bool:
        now = self._clock()
        while self._stamps and now - self._stamps[0] >= LIVE_INPUT_RATE_WINDOW_S:
            self._stamps.popleft()
        if len(self._stamps) >= self._limit:
            return False
        self._stamps.append(now)
        return True
