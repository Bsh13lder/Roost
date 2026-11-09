"""A real computer through the keeper's relays. Docker only; the default run skips it.

Needs ``make computer-image`` and the egress image. It starts one computer for a fresh bot id through the keeper
app, speaks pipelined RFB (several FramebufferUpdateRequests in flight, Tight and ZRLE asked for) to
``/computer/vnc``, prints the first-frame time and the key-to-update median and p90 (the spike's open item), and
removes the computer, its volume and its network at the end. It removes ``roost-egress`` and ``roost-out`` only if
this run created them.
"""

from __future__ import annotations

import asyncio
import json
import queue
import statistics
import struct
import subprocess
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from roost.config import RoostConfig
from roost.desk.signing import signed_headers
from roost.keeper.app import create_app

pytestmark = pytest.mark.docker

_SECRET = "k" * 32
_ENCODINGS = (16, 7, 1, 0)           # ZRLE, Tight, CopyRect, Raw
_KEY_TRIES = 10
_QUIET_S = 0.4
_WAIT_S = 2.0


def _docker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=60)


def _exists(kind: str, name: str) -> bool:
    return _docker(kind, "inspect", name).returncode == 0


class _Rfb:
    """A byte reader over the WebSocket. A thread pulls binary frames so a read can time out."""

    def __init__(self, ws) -> None:
        self.ws = ws
        self.buf = b""
        self.frames: queue.Queue[bytes | None] = queue.Queue()
        threading.Thread(target=self._pull, daemon=True).start()

    def _pull(self) -> None:
        try:
            while True:
                self.frames.put(self.ws.receive_bytes())
        except Exception:
            self.frames.put(None)

    def read(self, n: int, timeout: float = _WAIT_S * 10) -> bytes:
        while len(self.buf) < n:
            frame = self.frames.get(timeout=timeout)
            if frame is None:
                raise EOFError("the relay closed")
            self.buf += frame
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, data: bytes) -> None:
        self.ws.send_bytes(data)


def _handshake(rfb: _Rfb) -> tuple[int, int]:
    assert rfb.read(12).startswith(b"RFB 003.")
    rfb.send(b"RFB 003.008\n")
    count = rfb.read(1)[0]
    assert count and 1 in rfb.read(count)
    rfb.send(b"\x01")
    assert rfb.read(4) == b"\0\0\0\0"
    rfb.send(b"\x01")
    width, height = struct.unpack(">HH", rfb.read(4))
    rfb.read(16)
    rfb.read(struct.unpack(">I", rfb.read(4))[0])
    rfb.send(struct.pack(">BxH", 2, len(_ENCODINGS)) + b"".join(struct.pack(">i", e) for e in _ENCODINGS))
    return width, height


def _request(width: int, height: int, incremental: int) -> bytes:
    return struct.pack(">BBHHHH", 3, incremental, 0, 0, width, height)


def _drain_until_quiet(rfb: _Rfb) -> None:
    """Pull whatever arrives until nothing comes for a moment (keeps the next timing clean)."""
    rfb.buf = b""
    while True:
        try:
            rfb.read(1, timeout=_QUIET_S)
        except (queue.Empty, EOFError):
            return


@pytest.fixture
def keeper(tmp_path):
    made_egress = not _exists("container", "roost-egress")
    made_out = not _exists("network", "roost-out")
    config = RoostConfig(server_secret="x" * 32, database_dir=tmp_path / "data", desks_dir=tmp_path / "desks",
                         keeper_secret=_SECRET)
    bot_id = str(uuid.uuid4())
    app = create_app(config)
    try:
        with TestClient(app) as client:
            yield client, bot_id
    finally:
        asyncio.run(app.state.computers.remove(bot_id))
        if made_egress:
            _docker("rm", "-f", "roost-egress")
        if made_out:
            _docker("network", "rm", "roost-out")


def test_pipelined_rfb_through_the_relay(keeper):
    client, bot_id = keeper
    path = f"/desks/{bot_id}/computer/start"
    body = b'{"busy": []}'
    started = client.post(path, headers=signed_headers(_SECRET, "POST", path, body), content=body)
    assert started.status_code == 200, started.text
    token = started.json()["vnc_token"]
    cdp_headers = {"x-roost-desk-token": started.json()["cdp_token"]}
    with client.websocket_connect(f"/desks/{bot_id}/computer/cdp", headers=cdp_headers) as cdp:
        cdp.send_text(json.dumps({"id": 1, "method": "Browser.getVersion"}))
        assert "product" in json.loads(cdp.receive_text())["result"]
        cdp.close()
        time.sleep(0.3)
    t0 = time.monotonic()
    with client.websocket_connect(f"/desks/{bot_id}/computer/vnc", headers={"x-roost-desk-token": token}) as ws:
        rfb = _Rfb(ws)
        width, height = _handshake(rfb)
        for incremental in (0, 1, 1, 1):                      # four requests in flight at once
            rfb.send(_request(width, height, incremental))
        assert rfb.read(1) == b"\x00"                         # a FramebufferUpdate
        first_frame_s = time.monotonic() - t0
        _drain_until_quiet(rfb)
        latencies = []
        for _ in range(_KEY_TRIES):
            rfb.send(_request(width, height, 1))
            sent = time.monotonic()
            rfb.send(struct.pack(">BBxxI", 4, 1, 0x61) + struct.pack(">BBxxI", 4, 0, 0x61))
            try:
                rfb.read(1, timeout=_WAIT_S)
            except (queue.Empty, EOFError):
                continue
            latencies.append(time.monotonic() - sent)
            _drain_until_quiet(rfb)
    summary = {"size": [width, height], "first_frame_s": round(first_frame_s, 3), "updates_after_key": len(latencies)}
    if latencies:
        ordered = sorted(latencies)
        summary["key_to_update_median_s"] = round(statistics.median(ordered), 3)
        summary["key_to_update_p90_s"] = round(ordered[int(len(ordered) * 0.9) - 1], 3)
    print("RELAY", json.dumps(summary))
    assert (width, height) == (1280, 800)
