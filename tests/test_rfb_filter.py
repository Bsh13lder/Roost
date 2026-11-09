"""The RFB client filter (Computers 2.0, C1, Task 8): what a browser may send to a bot's screen.

Every client message is parsed to its exact length. Input is forwarded only when allowed; anything unknown closes.
"""

from __future__ import annotations

import struct

import pytest

from roost.constants import (
    LIVE_INPUT_MAX_PER_SECOND,
    LIVE_INPUT_RATE_WINDOW_S,
    LIVE_PASTE_MAX_CHARS,
    RFB_CLIENT_VERSION,
    RFB_EXT_CLIPBOARD_ENCODING,
    RFB_FENCE_MAX,
    RFB_SET_ENCODINGS_MAX,
)
from roost.desk.rfb import InputRateLimit, RfbClientFilter, RfbProtocolError, verdict

HANDSHAKE = RFB_CLIENT_VERSION + b"\x01" + b"\x01"     # version, security None, ClientInit shared


def _ready() -> RfbClientFilter:
    filt = RfbClientFilter()
    filt.feed(HANDSHAKE)
    return filt


def set_pixel_format() -> bytes:
    return b"\x00" + b"\x00" * 3 + b"\x20\x18\x00\x01" + struct.pack(">HHH", 255, 255, 255) + b"\x10\x08\x00" + b"\x00" * 3


def set_encodings(*encodings: int) -> bytes:
    return struct.pack(">BxH", 2, len(encodings)) + b"".join(struct.pack(">i", e) for e in encodings)


def update_request() -> bytes:
    return struct.pack(">BBHHHH", 3, 0, 0, 0, 320, 200)


def key_event() -> bytes:
    return struct.pack(">BBxxI", 4, 1, 0x61)


def pointer_event() -> bytes:
    return struct.pack(">BBHH", 5, 1, 10, 20)


def cut_text(text: bytes) -> bytes:
    return struct.pack(">Bxxx i", 6, len(text)) + text


def extended_cut_text(size: int) -> bytes:
    return struct.pack(">Bxxx i", 6, -size) + b"\x00" * size


def continuous_updates() -> bytes:
    return struct.pack(">BBHHHH", 150, 1, 0, 0, 320, 200)


def fence(payload: bytes) -> bytes:
    return struct.pack(">Bxxx IB", 248, 0, len(payload)) + payload


def xvp() -> bytes:
    return b"\xfa\x00\x01\x02"


def desktop_size(screens: int = 1) -> bytes:
    return struct.pack(">BxHHBx", 251, 640, 480, screens) + b"\x00" * 16 * screens


def qemu_key() -> bytes:
    return struct.pack(">BBHII", 255, 0, 1, 0x61, 30)


EVERY_MESSAGE = [
    ("set_pixel_format", set_pixel_format(), False), ("update_request", update_request(), False),
    ("key", key_event(), True), ("pointer", pointer_event(), True), ("cut_text", cut_text(b"hello"), True),
    ("continuous_updates", continuous_updates(), False), ("fence", fence(b"abc"), False),
    ("xvp", xvp(), False), ("desktop_size", desktop_size(2), False), ("qemu_key", qemu_key(), True),
]


def test_handshake_passes_and_wrong_versions_close():
    filt = RfbClientFilter()
    messages = filt.feed(HANDSHAKE)
    assert [m.kind for m in messages] == ["handshake"] * 3 and b"".join(m.data for m in messages) == HANDSHAKE
    assert not any(m.is_input for m in messages)
    for version in (b"RFB 003.003\n", b"RFB 003.007\n", b"RFB 004.000\n", b"GET / HTTP/1\n"):
        with pytest.raises(RfbProtocolError):
            RfbClientFilter().feed(version)


@pytest.mark.parametrize("security", [0, 2, 16, 255])
def test_security_other_than_none_closes(security):
    with pytest.raises(RfbProtocolError):
        RfbClientFilter().feed(RFB_CLIENT_VERSION + bytes([security]))


@pytest.mark.parametrize(("kind", "data", "is_input"), EVERY_MESSAGE)
def test_each_message_type_is_split_at_its_exact_length(kind, data, is_input):
    filt = _ready()
    messages = filt.feed(data + update_request() + data)
    assert [m.kind for m in messages] == [kind, "update_request", kind]
    assert messages[0].data == data and messages[0].is_input is is_input
    assert messages[1].data == update_request() and messages[2].data == data


def test_set_encodings_passes_through_untouched_without_the_clipboard_extension():
    data = set_encodings(0, 1, -223)
    assert _ready().feed(data)[0].data == data


@pytest.mark.parametrize("data", [key_event(), cut_text(b"x" * 40), fence(b"f" * 20), desktop_size(3), set_encodings(0, 1)])
def test_partial_messages_wait_for_more_bytes(data):
    filt = _ready()
    for i in range(len(data) - 1):
        assert filt.feed(data[i:i + 1]) == ()
    assert filt.feed(data[-1:])[0].data == data


def test_partial_handshake_waits_too():
    filt = RfbClientFilter()
    assert filt.feed(RFB_CLIENT_VERSION[:5]) == ()
    assert [m.kind for m in filt.feed(RFB_CLIENT_VERSION[5:] + b"\x01\x01")] == ["handshake"] * 3


def test_input_is_dropped_when_not_allowed_and_forwarded_when_allowed():
    for kind, data, is_input in EVERY_MESSAGE:
        message = _ready().feed(data)[0]
        if is_input:
            assert verdict(message, input_allowed=False) == "drop", kind
            assert verdict(message, input_allowed=True) == "forward", kind


def test_view_mode_drops_every_input_message_and_forwards_the_rest():
    filt = _ready()
    kept = [m.kind for m in filt.feed(b"".join(d for _, d, _ in EVERY_MESSAGE))
            if verdict(m, input_allowed=False) == "forward"]
    assert kept == ["set_pixel_format", "update_request", "continuous_updates", "fence"]


def test_desktop_size_and_xvp_are_always_dropped():
    for data in (xvp(), desktop_size()):
        message = _ready().feed(data)[0]
        assert verdict(message, input_allowed=True) == "drop" and not message.is_input


def test_extended_clipboard_is_stripped_and_never_forwarded():
    message = _ready().feed(set_encodings(0, RFB_EXT_CLIPBOARD_ENCODING, 1))[0]
    assert message.data == set_encodings(0, 1)
    assert struct.pack(">i", RFB_EXT_CLIPBOARD_ENCODING) not in message.data
    extended = _ready().feed(extended_cut_text(24))[0]
    assert verdict(extended, input_allowed=True) == "drop" and verdict(extended, input_allowed=False) == "drop"


def test_a_long_paste_closes():
    assert len(_ready().feed(cut_text(b"x" * LIVE_PASTE_MAX_CHARS))) == 1
    with pytest.raises(RfbProtocolError):
        _ready().feed(cut_text(b"x" * (LIVE_PASTE_MAX_CHARS + 1)))


def test_too_many_encodings_or_a_long_fence_close():
    with pytest.raises(RfbProtocolError):
        _ready().feed(set_encodings(*range(RFB_SET_ENCODINGS_MAX + 1)))
    with pytest.raises(RfbProtocolError):
        _ready().feed(fence(b"f" * (RFB_FENCE_MAX + 1)))


def test_unknown_types_close_without_echoing_bytes():
    secret = b"hunter2-correct-horse"
    for unknown in (b"\x07" + secret, b"\xff\x09" + secret, b"\x01" + secret, b"\xfe" + secret):
        with pytest.raises(RfbProtocolError) as caught:
            _ready().feed(unknown)
        assert "hunter2" not in str(caught.value) and "hunter2" not in repr(caught.value)
    with pytest.raises(RfbProtocolError) as caught:
        RfbClientFilter().feed(b"hunter2-secret")
    assert "hunter2" not in str(caught.value)


def test_a_buffer_past_64_kib_without_a_whole_message_closes():
    with pytest.raises(RfbProtocolError):
        _ready().feed(extended_cut_text(70_000)[:66_000])


def test_after_an_error_the_filter_stays_closed():
    filt = _ready()
    with pytest.raises(RfbProtocolError):
        filt.feed(b"\x07")
    with pytest.raises(RfbProtocolError):
        filt.feed(update_request())


def test_rate_limit_drops_input_past_the_cap():
    now = [0.0]
    limit = InputRateLimit(limit=3, clock=lambda: now[0])
    assert [limit.allow() for _ in range(5)] == [True, True, True, False, False]
    now[0] += LIVE_INPUT_RATE_WINDOW_S + 0.01
    assert limit.allow() is True


def test_rate_limit_defaults_to_the_contract_cap():
    now = [0.0]
    limit = InputRateLimit(clock=lambda: now[0])
    assert sum(limit.allow() for _ in range(LIVE_INPUT_MAX_PER_SECOND + 10)) == LIVE_INPUT_MAX_PER_SECOND
