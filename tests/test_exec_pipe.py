"""ExecPipe against a real subprocess (a tiny Python program, no docker) and the NUL framer."""

from __future__ import annotations

import sys
import time

import pytest

from roost.constants import LIVE_RELAY_CHUNK_MAX
from roost.keeper.exec_pipe import ExecPipe, NulFramer

_ECHO = (
    "import os,sys\n"
    "while True:\n"
    "    d=os.read(0,1<<20)\n"
    "    if not d: break\n"
    "    os.write(1,d)\n"
)
_STUCK = "import signal,time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\nprint('up',flush=True)\ntime.sleep(60)\n"


def _argv(code: str) -> list[str]:
    return [sys.executable, "-I", "-c", code]


async def _read_exactly(pipe: ExecPipe, n: int) -> bytes:
    got = b""
    while len(got) < n:
        chunk = await pipe.read()
        assert chunk
        got += chunk
    return got


async def test_bytes_round_trip_unchanged():
    pipe = await ExecPipe.open(_argv(_ECHO))
    payload = bytes(range(256)) * 4 + b"\0\xff\x00end"
    try:
        await pipe.write(payload)
        assert await _read_exactly(pipe, len(payload)) == payload
    finally:
        await pipe.close()


async def test_read_is_bounded():
    pipe = await ExecPipe.open(_argv(_ECHO))
    big = b"x" * (LIVE_RELAY_CHUNK_MAX * 3)
    try:
        await pipe.write(big)
        sizes = []
        got = 0
        while got < len(big):
            chunk = await pipe.read()
            sizes.append(len(chunk))
            got += len(chunk)
        assert max(sizes) <= LIVE_RELAY_CHUNK_MAX and got == len(big)
    finally:
        await pipe.close()


async def test_eof_reads_empty_bytes():
    pipe = await ExecPipe.open(_argv("pass"))
    assert await pipe.read() == b""
    await pipe.close()


async def test_close_kills_a_stuck_process():
    pipe = await ExecPipe.open(_argv(_STUCK), grace_s=0.3)
    await pipe.read()                       # "up": the SIGTERM handler is installed
    started = time.monotonic()
    await pipe.close()
    assert time.monotonic() - started < 5
    assert pipe.returncode is not None
    await pipe.close()                      # closing twice is fine
    with pytest.raises(OSError):
        await pipe.write(b"x")


def test_nul_framer_splits_and_buffers_partial_messages():
    framer = NulFramer()
    assert framer.feed(b'{"a":1}\0{"b"') == ('{"a":1}',)
    assert framer.feed(b':2}') == ()
    assert framer.feed(b"\0\0") == ('{"b":2}',)           # empty frames are dropped
    snow = "é".encode()
    assert framer.feed(b'"' + snow[:1]) == ()              # a UTF-8 character split across reads
    assert framer.feed(snow[1:] + b'"\0') == ('"é"',)


def test_nul_framer_refuses_an_endless_message_and_bad_utf8():
    framer = NulFramer(max_bytes=16)
    with pytest.raises(ValueError):
        framer.feed(b"x" * 17)
    with pytest.raises(ValueError):
        NulFramer().feed(b"\xff\xfe\0")
