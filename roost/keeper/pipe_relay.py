"""Bridges one WebSocket client to a bot's already-running Brave CDP pipe.

``BraveLauncher`` (``roost/keeper/browsers.py``) gives each running bot a
``BrowserHandle`` with ``read_fd``/``write_fd`` — the keeper's own ends of
the two pipes wired to Brave's ``--remote-debugging-pipe`` (fd 3 for
commands the browser reads, fd 4 for events the browser writes), each
message framed as UTF-8 JSON followed by a single NUL (``\\0``) byte,
never a length prefix. ``PipeRelay`` turns that raw, blocking pipe pair
into an async `send`/async-iterator pair so ``roost/keeper/app.py``'s
WebSocket route can forward text frames both ways without ever blocking
the event loop on a syscall.

Exactly one relay is meant to be attached to a given bot's pipe at a
time (the pipe is a single stream — two simultaneous readers would race
for its bytes); ``RelayRegistry`` enforces that at the WebSocket-client
level by closing an older connection (code 4409) the moment a new one
takes over the same bot.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket

    from roost.keeper.browsers import BrowserHandle

# The framing terminator Brave's `--remote-debugging-pipe` protocol uses
# in place of a length prefix: one NUL byte after each JSON message, both
# directions. Not in roost/constants.py — like browsers.py's own pipe/CDP
# constants, this is a protocol detail local to this one module, not a
# cross-cutting app setting.
_FRAME_TERMINATOR = b"\0"

_READ_CHUNK_SIZE = 65536

# Fix round 1, finding 2: at most one PipeRelay may hold the event
# loop's `add_reader` registration for a given fd at a time. The moment
# a WS handover happens (RelayRegistry.take_over), a second PipeRelay is
# constructed on the SAME handle/fd -- asyncio's add_reader silently
# *replaces* the first relay's callback for that fd, which is fine. The
# bug this map prevents: the superseded (first) relay's own close(),
# run later by the old connection's route-handler cleanup, calling
# `loop.remove_reader(fd)` unconditionally -- that deregisters whatever
# is CURRENTLY installed for that fd, i.e. the *second* relay's
# callback, permanently starving the surviving connection of further
# browser events (confirmed against the real class on one event loop;
# Starlette's TestClient masks it by giving each websocket_connect() its
# own loop). Keyed by fd, not bot_id, because that's exactly the
# resource `remove_reader` operates on. One keeper process runs one
# event loop, so these plain dict reads/writes never race in practice.
_fd_readers: dict[int, "PipeRelay"] = {}


def _write_all(fd: int, data: bytes) -> None:
    """``os.write`` is one syscall and may write fewer bytes than asked for
    a large message on a blocking pipe; loop until every byte is sent."""
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def tokens_match(expected: str, provided: str | None) -> bool:
    """Constant-time comparison for the ``X-Roost-Desk-Token`` header,
    mirroring ``roost/desk/signing.py``'s HMAC compare. ``None`` (header
    absent) never matches, and is checked before touching ``hmac`` so a
    missing header can't be timed against a present-but-wrong one."""
    if provided is None:
        return False
    return hmac.compare_digest(expected, provided)


class PipeRelay:
    """One relay per connected WebSocket client, wired to one bot's
    running browser pipe.

    ``await relay.send(text)`` writes ``text`` to the browser's command
    pipe, framed with the trailing ``\\0``. Iterating the relay
    (``async for text in relay``) yields each ``\\0``-terminated reply
    from the browser's event pipe, decoded, with the terminator stripped;
    iteration ends (``StopAsyncIteration``) once the browser's end of the
    pipe closes (process exited) or ``close()`` is called.

    Reading never blocks the event loop: the pipe's read end is put in
    non-blocking mode and registered with ``loop.add_reader``, so a
    callback only runs once the kernel says there is data (or EOF) to
    read, never while idle.
    """

    def __init__(self, handle: BrowserHandle) -> None:
        self._handle = handle
        self._loop = asyncio.get_running_loop()
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._buffer = b""
        self._closed = False

        os.set_blocking(handle.read_fd, False)
        self._loop.add_reader(handle.read_fd, self._on_readable)
        _fd_readers[handle.read_fd] = self

    def _on_readable(self) -> None:
        try:
            chunk = os.read(self._handle.read_fd, _READ_CHUNK_SIZE)
        except BlockingIOError:
            return
        except OSError:
            self.close()
            return

        if not chunk:
            # EOF: the browser's end of the pipe closed (process exited).
            self.close()
            return

        self._buffer += chunk
        while _FRAME_TERMINATOR in self._buffer:
            frame, self._buffer = self._buffer.split(_FRAME_TERMINATOR, 1)
            try:
                text = frame.decode("utf-8")
            except UnicodeDecodeError:
                # Brave's CDP pipe protocol is always UTF-8 JSON; bytes
                # that fail to decode mean the framing itself is no
                # longer trustworthy, so the relay ends rather than
                # guessing at a repair.
                self.close()
                return
            self._queue.put_nowait(text)

    async def send(self, text: str) -> None:
        data = text.encode("utf-8") + _FRAME_TERMINATOR
        await self._loop.run_in_executor(None, _write_all, self._handle.write_fd, data)

    def __aiter__(self) -> PipeRelay:
        return self

    async def __anext__(self) -> str:
        item = await self._queue.get()
        if item is None:
            raise StopAsyncIteration
        return item

    def close(self) -> None:
        """Stop reading from the browser pipe and end iteration. Idempotent.
        Never closes the underlying fds — those belong to the
        ``BrowserHandle``/``BraveLauncher`` and outlive any one relay."""
        if self._closed:
            return
        self._closed = True
        # Only deregister the reader if this relay is still the one
        # currently installed for the fd -- a superseded relay (see
        # `_fd_readers` above) must no-op here instead of evicting
        # whatever relay took over from it.
        if _fd_readers.get(self._handle.read_fd) is self:
            with contextlib.suppress(ValueError, OSError):
                self._loop.remove_reader(self._handle.read_fd)
            del _fd_readers[self._handle.read_fd]
        self._queue.put_nowait(None)


class RelayRegistry:
    """Tracks the single active CDP WebSocket client per bot, keeper-wide.

    A second client for the same bot replaces the first: the older
    connection is closed with code 4409 the moment the new one takes
    over, before the new relay starts reading.
    """

    def __init__(self) -> None:
        self._active: dict[str, WebSocket] = {}

    async def take_over(self, bot_id: str, websocket: WebSocket) -> None:
        previous = self._active.get(bot_id)
        self._active[bot_id] = websocket
        if previous is not None and previous is not websocket:
            with contextlib.suppress(Exception):
                await previous.close(code=4409)

    def release(self, bot_id: str, websocket: WebSocket) -> None:
        """No-op if ``websocket`` has already been superseded by a newer
        connection for the same bot — only the current holder may clear
        itself, so a slow-to-clean-up loser can never evict the winner."""
        if self._active.get(bot_id) is websocket:
            del self._active[bot_id]
