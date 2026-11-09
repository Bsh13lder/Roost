"""One ``docker exec -i ... roost-pipe cdp|vnc`` process as an async byte pipe, and the CDP NUL framer.

The keeper relays between a WebSocket and this pipe. Nothing it reads or writes is ever logged, and the argv
comes only from ``roost.keeper.computers.build_pipe_argv`` (one bot's container, one of two sockets).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Sequence

from roost.constants import LIVE_RELAY_CHUNK_MAX

_CLOSE_GRACE_S = 2.0
_KILL_WAIT_S = 2.0
_CDP_MESSAGE_MAX_BYTES = 64 * 1024 * 1024
_NUL = b"\0"


class ExecPipe:
    def __init__(self, proc: asyncio.subprocess.Process, grace_s: float) -> None:
        self._proc = proc
        self._grace_s = grace_s
        self._closed = False

    @classmethod
    async def open(cls, argv: Sequence[str], *, grace_s: float = _CLOSE_GRACE_S) -> "ExecPipe":
        proc = await asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, limit=LIVE_RELAY_CHUNK_MAX,
        )
        return cls(proc, grace_s)

    @property
    def returncode(self) -> int | None:
        return self._proc.returncode

    async def write(self, data: bytes) -> None:
        stdin = self._proc.stdin
        if self._closed or stdin is None or stdin.is_closing():
            raise OSError("the pipe is closed")
        try:
            stdin.write(data)
            await stdin.drain()
        except (ConnectionError, BrokenPipeError) as exc:
            raise OSError("the pipe is closed") from exc

    async def read(self) -> bytes:
        """The next bytes, at most ``LIVE_RELAY_CHUNK_MAX``; ``b""`` at the end."""
        stdout = self._proc.stdout
        if stdout is None:
            return b""
        return await stdout.read(LIVE_RELAY_CHUNK_MAX)

    async def close(self) -> None:
        """Terminate the exec, then kill it after the grace. Never raises."""
        if self._closed:
            return
        self._closed = True
        with contextlib.suppress(Exception):
            if self._proc.stdin is not None:
                self._proc.stdin.close()
        if self._proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=self._grace_s)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    self._proc.kill()
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(self._proc.wait(), timeout=_KILL_WAIT_S)


class NulFramer:
    """CDP over a byte stream: UTF-8 JSON messages, each ended by one NUL byte."""

    def __init__(self, *, max_bytes: int = _CDP_MESSAGE_MAX_BYTES) -> None:
        self._buffer = bytearray()
        self._max = max_bytes

    def feed(self, data: bytes) -> tuple[str, ...]:
        self._buffer.extend(data)
        *whole, rest = bytes(self._buffer).split(_NUL)
        self._buffer = bytearray(rest)
        if len(self._buffer) > self._max:
            raise ValueError("a DevTools message is too long")
        return tuple(part.decode("utf-8") for part in whole if part)
