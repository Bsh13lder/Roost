"""``WS /api/bots/{id}/live`` (Computers 2.0, C1, Task 9): the accept rules, view-only, and nothing typed in any log.

The gateway runs in-process with the fake desk and the fake screen. The test client's peer is ``testclient``, so
the tests that need a Mac peer run the gateway the way its container does (``in_container``)."""

from __future__ import annotations

import contextlib
import logging
import sqlite3
import struct
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from roost.config import load_config
from roost.constants import RFB_CLIENT_VERSION
from roost.gateway.app import create_app
from roost.gateway.auth import register_user

O = {"Origin": "http://127.0.0.1:18800"}
AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}
REQUEST = struct.pack(">BBHHHH", 3, 0, 0, 0, 320, 200)
SECRET = "hunter2-секрет"


def _key(char: str) -> bytes:
    keysym = ord(char) if ord(char) < 0x100 else 0x01000000 + ord(char)
    return struct.pack(">BBxxI", 4, 1, keysym)


def _app(**changes):
    return create_app(replace(load_config(), in_container=True, **changes))


def _login(client: TestClient, name: str = "alice") -> None:
    assert client.post("/api/auth/register", json={"username": name, "password": "pw-123456"}, headers=O).status_code == 201


def _bot(client: TestClient, computer: str = "linux", *, wake: bool = True) -> str:
    bot_id = client.post("/api/bots", json={"name": "Scout", "job": "read", "instructions": "", "avatar": AVATAR},
                         headers=O).json()["id"]
    client.patch(f"/api/bots/{bot_id}", json={"computer": computer}, headers=O)
    if wake and computer == "linux":
        client.post(f"/api/bots/{bot_id}/desk/browser/start", headers=O)
    return bot_id


def _url(bot_id: str, mode: str = "view") -> str:
    return f"/api/bots/{bot_id}/live?mode={mode}"


def _close_code(client: TestClient, url: str, headers: dict | None = None) -> int:
    with pytest.raises(WebSocketDisconnect) as caught:
        with client.websocket_connect(url, headers=O if headers is None else headers) as ws:
            ws.receive_bytes()
    return caught.value.code


def _handshake(ws) -> None:
    assert ws.receive_bytes() == b"RFB 003.008\n"
    ws.send_bytes(RFB_CLIENT_VERSION)
    assert ws.receive_bytes() == b"\x01\x01"
    ws.send_bytes(b"\x01")
    assert ws.receive_bytes() == b"\x00\x00\x00\x00"
    ws.send_bytes(b"\x01")
    assert ws.receive_bytes().endswith(b"Fake computer")


def test_a_foreign_origin_is_4403():
    c = TestClient(_app())
    _login(c)
    bot_id = _bot(c)
    assert _close_code(c, _url(bot_id), {"Origin": "http://evil.example"}) == 4403
    assert _close_code(c, _url(bot_id), {}) == 4403


def test_a_peer_that_is_not_this_mac_is_4403():
    c = TestClient(create_app(replace(load_config(), in_container=False)))      # peer is "testclient"
    _login(c)
    assert _close_code(c, _url(_bot(c))) == 4403


def test_a_forwarded_request_is_4403_even_in_the_container():
    c = TestClient(_app())
    _login(c)
    bot_id = _bot(c)
    assert _close_code(c, _url(bot_id), {**O, "X-Forwarded-For": "203.0.113.7"}) == 4403


def test_no_session_is_4401():
    c = TestClient(_app())
    assert _close_code(c, "/api/bots/anything/live?mode=view") == 4401


async def test_another_users_bot_is_4404():
    app = _app()
    alice = TestClient(app)
    _login(alice)
    bot_id = _bot(alice)
    await register_user(app.state.config, "bob", "pw-123456")
    bob = TestClient(app)
    assert bob.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"}, headers=O).status_code == 200
    assert _close_code(bob, _url(bot_id)) == 4404
    assert _close_code(alice, _url("not-a-bot")) == 4404


def test_a_sleeping_computer_is_4410():
    c = TestClient(_app())
    _login(c)
    assert _close_code(c, _url(_bot(c, wake=False))) == 4410


def test_a_mac_brave_bot_has_no_live_screen():
    c = TestClient(_app())
    _login(c)
    assert _close_code(c, _url(_bot(c, "mac_brave"))) == 4503


def test_control_mode_without_the_lock_is_4409_and_a_bad_mode_is_4400():
    c = TestClient(_app())
    _login(c)
    bot_id = _bot(c)
    assert _close_code(c, _url(bot_id, "control")) == 4409
    assert _close_code(c, _url(bot_id, "drive")) == 4400


def test_a_third_tab_is_4429():
    c = TestClient(_app())
    _login(c)
    bot_id = _bot(c)
    with c.websocket_connect(_url(bot_id), headers=O) as one, c.websocket_connect(_url(bot_id), headers=O) as two:
        assert one.receive_bytes() == b"RFB 003.008\n" and two.receive_bytes() == b"RFB 003.008\n"
        assert _close_code(c, _url(bot_id)) == 4429
    with c.websocket_connect(_url(bot_id), headers=O) as again:           # the count went back down
        assert again.receive_bytes() == b"RFB 003.008\n"


def test_bytes_flow_both_ways_with_the_fake_screen():
    c = TestClient(_app())
    _login(c)
    bot_id = _bot(c)
    with c.websocket_connect(_url(bot_id), headers=O) as ws:
        _handshake(ws)
        ws.send_bytes(REQUEST)
        frame = ws.receive_bytes()
        assert frame[0] == 0 and len(frame) > 1000


def test_view_mode_never_forwards_input():
    c = TestClient(_app())
    _login(c)
    bot_id = _bot(c)
    with c.websocket_connect(_url(bot_id), headers=O) as ws:
        _handshake(ws)
        ws.send_bytes(_key("a") + struct.pack(">BBHH", 5, 1, 4, 5) + struct.pack(">Bxxxi", 6, 3) + b"abc")
        ws.send_bytes(REQUEST)          # answered only after the dropped input was dealt with, in order
        ws.receive_bytes()
    screen = c.app.state.desks.for_bot(bot_id, "linux").screens[-1]
    assert screen.received_input == 0


def test_a_protocol_error_closes_4400():
    c = TestClient(_app())
    _login(c)
    bot_id = _bot(c)
    with pytest.raises(WebSocketDisconnect) as caught:
        with c.websocket_connect(_url(bot_id), headers=O) as ws:
            ws.receive_bytes()
            ws.send_bytes(b"GET / HTTP/1.1\r\n\r\n")
            ws.receive_bytes()
    assert caught.value.code == 4400


def test_a_computer_that_stops_answering_closes_4503():
    c = TestClient(_app())
    _login(c)
    bot_id = _bot(c)
    with pytest.raises(WebSocketDisconnect) as caught:
        with c.websocket_connect(_url(bot_id), headers=O) as ws:
            ws.receive_bytes()
            c.app.state.desks.for_bot(bot_id, "linux").screens[-1].close_from_far_end()
            ws.receive_bytes()
    assert caught.value.code == 4503


@pytest.mark.parametrize(("far_end", "reason", "code"), [(True, "screen", "4503"), (False, "client", "-")])
def test_every_screen_socket_end_is_logged_with_why_and_never_what(caplog, far_end, reason, code):
    """Owner, 2026-10-29: the phone's screen dropped and nothing said why. One line per end: who ended it, the
    close code, how long it lived; never a byte of what passed."""
    c = TestClient(_app())
    _login(c)
    bot_id = _bot(c)
    caplog.set_level(logging.INFO, logger="roost.gateway.routes.live")
    with contextlib.suppress(WebSocketDisconnect):
        with c.websocket_connect(_url(bot_id), headers=O) as ws:
            ws.receive_bytes()
            if far_end:
                c.app.state.desks.for_bot(bot_id, "linux").screens[-1].close_from_far_end()
                ws.receive_bytes()
    lines = [r.getMessage() for r in caplog.records if "live screen" in r.getMessage()]
    assert any(bot_id in line and f"ended by {reason}" in line and f"code {code}" in line for line in lines), lines


def test_a_typed_password_is_in_no_log_event_or_audit(caplog):
    app = _app()
    config = app.state.config
    c = TestClient(app)
    _login(c)
    bot_id = _bot(c)
    caplog.set_level(logging.DEBUG)
    with c.websocket_connect(_url(bot_id), headers=O) as ws:
        _handshake(ws)
        ws.send_bytes(b"".join(_key(char) for char in SECRET))
        text = SECRET.encode()
        ws.send_bytes(struct.pack(">Bxxxi", 6, len(text)) + text)
        ws.send_bytes(REQUEST)
        ws.receive_bytes()
    needles = (SECRET, "hunter2", "секрет")
    assert not any(needle in caplog.text for needle in needles)
    for path in config.database_dir.rglob("*"):
        if path.is_file():
            blob = path.read_bytes()
            assert not any(needle.encode() in blob for needle in needles), path.name
    with sqlite3.connect(config.database_dir / "roost.db") as db:
        dump = "\n".join(db.iterdump())
    assert not any(needle in dump for needle in needles)
