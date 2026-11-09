#!/usr/bin/python3
"""roost-pipe cdp|vnc|want: connect stdin/stdout to one of the computer's Unix sockets.

The keeper runs this with `docker exec -i` (cdp, vnc); it only copies bytes. `want` asks roost-computerd for the
browser and prints its "ok" or "no" (the Browser shortcut runs it). It knows these sockets and nothing else,
and it never logs what passes. Standard library only.
"""

from __future__ import annotations

import os
import select
import socket
import sys

SOCKETS = {"cdp": "/run/screen/cdp.sock", "vnc": "/run/screen/vnc.sock", "want": "/run/screen/want.sock"}
_CHUNK = 65536


def socket_for(name: str) -> str:
    if name not in SOCKETS:
        raise ValueError("unknown socket")
    return SOCKETS[name]


def relay(path: str, in_fd: int, out_fd: int) -> int:
    """Copy in_fd -> socket and socket -> out_fd until either side closes. Returns an exit code."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(path)
    except OSError:
        sock.close()
        return 1
    try:
        return _pump(sock, in_fd, out_fd)
    finally:
        sock.close()


def _pump(sock: socket.socket, in_fd: int, out_fd: int) -> int:
    readers = [sock, in_fd]
    while True:
        ready, _, _ = select.select(readers, [], [])
        if sock in ready:
            data = sock.recv(_CHUNK)
            if not data:
                return 0
            _write_all(out_fd, data)
        if in_fd in ready:
            data = os.read(in_fd, _CHUNK)
            if not data:
                _drain(sock, out_fd)
                return 0
            sock.sendall(data)


def _drain(sock: socket.socket, out_fd: int) -> None:
    """Stdin closed: give the socket a moment to finish its answer, then stop."""
    sock.settimeout(0.5)
    try:
        while True:
            data = sock.recv(_CHUNK)
            if not data:
                return
            _write_all(out_fd, data)
    except OSError:
        return


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in SOCKETS:
        sys.stderr.write("usage: roost-pipe cdp|vnc|want\n")
        return 2
    try:
        return relay(socket_for(argv[0]), 0, 1)
    except (BrokenPipeError, ConnectionError):
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
