"""``WS /api/bots/{id}/live?mode=control`` (Computers 2.0, C2, Task 11): input only while the lock is held."""

from __future__ import annotations

import logging
import sqlite3
import struct
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from roost.config import load_config
from roost.constants import RFB_CLIENT_VERSION
from roost.gateway.app import create_app

O = {"Origin": "http://127.0.0.1:18800"}
AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}
REQUEST = struct.pack(">BBHHHH", 3, 0, 0, 0, 320, 200)
SECRET = "hunter2-секрет"


def _key(char: str) -> bytes:
    keysym = ord(char) if ord(char) < 0x100 else 0x01000000 + ord(char)
    return struct.pack(">BBxxI", 4, 1, keysym)


def _client() -> TestClient:
    return TestClient(create_app(replace(load_config(), in_container=True)))


def _bot(c: TestClient) -> str:
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    bot_id = c.post("/api/bots", json={"name": "Scout", "job": "read", "instructions": "", "avatar": AVATAR},
                    headers=O).json()["id"]
    c.patch(f"/api/bots/{bot_id}", json={"computer": "linux"}, headers=O)
    c.post(f"/api/bots/{bot_id}/desk/browser/start", headers=O)
    return bot_id


def _url(bot_id: str, mode: str = "control") -> str:
    return f"/api/bots/{bot_id}/live?mode={mode}"


def _handshake(ws) -> None:
    assert ws.receive_bytes() == b"RFB 003.008\n"
    ws.send_bytes(RFB_CLIENT_VERSION)
    assert ws.receive_bytes() == b"\x01\x01"
    ws.send_bytes(b"\x01")
    assert ws.receive_bytes() == b"\x00\x00\x00\x00"
    ws.send_bytes(b"\x01")
    assert ws.receive_bytes().endswith(b"Fake computer")


def _screens(c: TestClient, bot_id: str):
    return c.app.state.desks.for_bot(bot_id, "linux").screens


def test_control_without_the_lock_is_4409():
    with _client() as c:
        bot_id = _bot(c)
        with pytest.raises(WebSocketDisconnect) as caught:
            with c.websocket_connect(_url(bot_id), headers=O) as ws:
                ws.receive_bytes()
        assert caught.value.code == 4409


def test_input_reaches_the_screen_while_you_hold_control():
    with _client() as c:
        bot_id = _bot(c)
        assert c.post(f"/api/bots/{bot_id}/control", headers=O).status_code == 200
        with c.websocket_connect(_url(bot_id), headers=O) as ws:
            _handshake(ws)
            ws.send_bytes(_key("a") + struct.pack(">BBHH", 5, 1, 4, 5))
            ws.send_bytes(REQUEST)
            ws.receive_bytes()
        assert _screens(c, bot_id)[-1].received_input == 2


def test_input_stops_the_moment_control_is_given_back():
    with _client() as c:
        bot_id = _bot(c)
        c.post(f"/api/bots/{bot_id}/control", headers=O)
        with pytest.raises(WebSocketDisconnect) as caught:
            with c.websocket_connect(_url(bot_id), headers=O) as ws:
                _handshake(ws)
                ws.send_bytes(_key("a"))
                ws.send_bytes(REQUEST)
                ws.receive_bytes()
                assert c.delete(f"/api/bots/{bot_id}/control", headers=O).status_code == 200
                ws.send_bytes(_key("b"))
                while True:
                    ws.receive_bytes()
        assert caught.value.code == 4000
        assert _screens(c, bot_id)[-1].received_input == 1


def test_the_view_socket_never_forwards_input_even_while_held():
    with _client() as c:
        bot_id = _bot(c)
        c.post(f"/api/bots/{bot_id}/control", headers=O)
        with c.websocket_connect(_url(bot_id, "view"), headers=O) as ws:
            _handshake(ws)
            ws.send_bytes(_key("a"))
            ws.send_bytes(REQUEST)
            ws.receive_bytes()
        assert _screens(c, bot_id)[-1].received_input == 0


def test_a_second_control_socket_replaces_the_first():
    with _client() as c:
        bot_id = _bot(c)
        c.post(f"/api/bots/{bot_id}/control", headers=O)
        with c.websocket_connect(_url(bot_id), headers=O) as one:
            one.receive_bytes()
            with c.websocket_connect(_url(bot_id), headers=O) as two:
                two.receive_bytes()
                with pytest.raises(WebSocketDisconnect) as caught:
                    while True:
                        one.receive_bytes()
                assert caught.value.code == 4000


def test_a_long_paste_closes_4400():
    with _client() as c:
        bot_id = _bot(c)
        c.post(f"/api/bots/{bot_id}/control", headers=O)
        text = b"x" * 5000
        with pytest.raises(WebSocketDisconnect) as caught:
            with c.websocket_connect(_url(bot_id), headers=O) as ws:
                _handshake(ws)
                ws.send_bytes(struct.pack(">Bxxxi", 6, len(text)) + text)
                ws.receive_bytes()
        assert caught.value.code == 4400


def test_a_typed_password_in_control_is_in_no_log_event_or_audit(caplog):
    with _client() as c:
        bot_id = _bot(c)
        c.post(f"/api/bots/{bot_id}/control", headers=O)
        caplog.set_level(logging.DEBUG)
        with c.websocket_connect(_url(bot_id), headers=O) as ws:
            _handshake(ws)
            ws.send_bytes(b"".join(_key(char) for char in SECRET))
            text = SECRET.encode()
            ws.send_bytes(struct.pack(">Bxxxi", 6, len(text)) + text)
            ws.send_bytes(REQUEST)
            ws.receive_bytes()
        config = c.app.state.config
    needles = (SECRET, "hunter2", "секрет")
    assert not any(needle in caplog.text for needle in needles)
    for path in config.database_dir.rglob("*"):
        if path.is_file():
            assert not any(n.encode() in path.read_bytes() for n in needles), path.name
    with sqlite3.connect(config.database_dir / "roost.db") as db:
        dump = "\n".join(db.iterdump())
    assert not any(needle in dump for needle in needles)
