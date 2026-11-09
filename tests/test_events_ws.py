"""Integration tests for ``WS /api/events`` (``roost/gateway/routes/events.py``)
against the real, running gateway — Origin/auth gating, the initial
snapshot, resuming from a cursor, and per-user isolation (Review Focus #1).

Every test here uses ``with TestClient(app) as c:`` (not the bare
constructor most other HTTP-only contract tests in this repo use)
specifically so the lifespan runs AND so every request/WS connection a
test makes shares the one persistent event loop the lifespan started on
-- a ``POST .../messages`` call's ``TurnRunner.start()`` schedules a
real ``asyncio.Task`` that only keeps making progress past that call's
own return if it's on a loop that's still alive afterward (see
``roost/gateway/app.py``'s docstring on ``with TestClient(app) as c:``
vs. the bare constructor, and ``tests/test_pipe_relay.py``'s note on the
same portal machinery).
"""

from __future__ import annotations

import concurrent.futures
import time

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import init_db
from roost.events.hub import EventHub
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.gateway.routes import events as events_module

O = {"Origin": "http://127.0.0.1:18800"}
BAD_O = {"Origin": "http://evil.example"}

VALID_AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}


def _register(client: TestClient, username: str) -> None:
    r = client.post("/api/auth/register", json={"username": username, "password": "pw-123456"}, headers=O)
    assert r.status_code in (201, 403)
    if r.status_code == 403:
        client.post("/api/auth/login", json={"username": username, "password": "pw-123456"}, headers=O)


def _create_bot(client: TestClient, name: str = "Scout", headers=None) -> str:
    body = {"name": name, "job": "read news", "instructions": "", "avatar": VALID_AVATAR}
    r = client.post("/api/bots", json=body, headers=headers or O)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _expect_no_frame(ws, timeout: float = 1.0) -> None:
    """Proves nothing arrives on ``ws`` within ``timeout`` seconds,
    without hanging forever if it's wrong: ``start_task_soon`` (anyio's
    own API, which ``WebSocketTestSession.receive`` is built on) returns
    a ``concurrent.futures.Future`` whose wait CAN be bounded, unlike
    ``receive()``/``receive_json()`` themselves."""
    future = ws.portal.start_task_soon(ws._send_rx.receive)
    try:
        message = future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        future.cancel()
        return
    pytest.fail(f"expected no frame within {timeout}s, got {message!r}")


# ---------------------------------------------------------------------------
# Connect: snapshot, Origin, auth
# ---------------------------------------------------------------------------

def test_connect_with_cookie_and_origin_gets_a_snapshot_of_own_bots_only():
    with TestClient(create_app()) as c:
        _register(c, "alice")
        bot_id = _create_bot(c)

        with c.websocket_connect("/api/events", headers=O) as ws:
            frame = ws.receive_json()
            assert frame["type"] == "snapshot"
            assert [b["id"] for b in frame["bots"] if not b["is_primary"]] == [bot_id]
            assert isinstance(frame["cursor"], int)


def test_connect_without_an_allowed_origin_is_refused():
    with TestClient(create_app()) as c:
        _register(c, "alice")
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with c.websocket_connect("/api/events", headers=BAD_O) as ws:
                ws.receive_text()
        assert exc_info.value.code == 4403


def test_connect_without_a_session_cookie_is_refused():
    with TestClient(create_app()) as c:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with c.websocket_connect("/api/events", headers=O) as ws:
                ws.receive_text()
        assert exc_info.value.code == 4401


# ---------------------------------------------------------------------------
# A posted message streams the turn over the socket
# ---------------------------------------------------------------------------

def test_posting_a_message_streams_the_turn_to_the_bots_own_socket():
    with TestClient(create_app()) as c:
        _register(c, "alice")
        bot_id = _create_bot(c)
        thread_id = c.post(f"/api/bots/{bot_id}/threads", json={}, headers=O).json()["id"]

        with c.websocket_connect("/api/events", headers=O) as ws:
            snapshot = ws.receive_json()
            assert snapshot["type"] == "snapshot"

            r = c.post(f"/api/threads/{thread_id}/messages", json={"text": "hello"}, headers=O)
            assert r.status_code == 202

            seen_types = []
            final_body = None
            for _ in range(20):
                frame = ws.receive_json()
                seen_types.append(frame["type"])
                if frame["type"] == "message" and frame["message"]["body"]:
                    final_body = frame["message"]["body"]
                if frame["type"] == "message_done":
                    break

            assert "bot_status" in seen_types
            assert "text_delta" in seen_types
            assert "message_done" in seen_types
            assert final_body == "I heard: hello"  # ScriptedModel's default echo


# ---------------------------------------------------------------------------
# Resume replays stored events after a cursor
# ---------------------------------------------------------------------------

def test_resume_with_a_cursor_replays_stored_events_after_it():
    with TestClient(create_app()) as c:
        _register(c, "alice")
        bot_id = _create_bot(c)
        thread_id = c.post(f"/api/bots/{bot_id}/threads", json={}, headers=O).json()["id"]

        with c.websocket_connect("/api/events", headers=O) as ws:
            cursor = ws.receive_json()["cursor"]

        c.post(f"/api/threads/{thread_id}/messages", json={"text": "hi"}, headers=O)

        for _ in range(50):
            messages = c.get(f"/api/threads/{thread_id}/messages").json()
            if any(m["role"] == "bot" for m in messages):
                break
            time.sleep(0.05)
        else:
            pytest.fail("turn never completed")

        with c.websocket_connect("/api/events", headers=O) as ws2:
            ws2.receive_json()  # snapshot
            ws2.send_json({"type": "resume", "cursor": cursor})

            replayed_types = []
            for _ in range(10):
                frame = ws2.receive_json()
                replayed_types.append(frame["type"])
                if frame["type"] == "message_done":
                    break

            assert "message" in replayed_types
            assert "message_done" in replayed_types
            assert "text_delta" not in replayed_types  # never stored


# ---------------------------------------------------------------------------
# Per-user isolation (Review Focus #1)
# ---------------------------------------------------------------------------

def test_a_second_users_socket_gets_no_frames_for_the_first_users_bot():
    app = create_app()
    with TestClient(app) as c:
        r = c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
        assert r.status_code == 201
        alice_cookie = r.cookies.get("roost_session")
        c.cookies.clear()
        alice_headers = {**O, "Cookie": f"roost_session={alice_cookie}"}

        alice_bot_id = _create_bot(c, headers=alice_headers)

        cfg = load_config()
        c.portal.call(register_user, cfg, "bob", "pw-123456")
        r = c.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"}, headers=O)
        assert r.status_code == 200
        bob_cookie = r.cookies.get("roost_session")
        c.cookies.clear()
        bob_headers = {**O, "Cookie": f"roost_session={bob_cookie}"}

        with c.websocket_connect("/api/events", headers=bob_headers) as bob_ws:
            snapshot = bob_ws.receive_json()
            assert snapshot["bots"] == []  # bob owns no bots

            thread_id = c.post(
                f"/api/bots/{alice_bot_id}/threads", json={}, headers=alice_headers,
            ).json()["id"]
            r = c.post(
                f"/api/threads/{thread_id}/messages", json={"text": "hi"}, headers=alice_headers,
            )
            assert r.status_code == 202

            for _ in range(50):
                messages = c.get(
                    f"/api/threads/{thread_id}/messages", headers=alice_headers,
                ).json()
                if any(m["role"] == "bot" for m in messages):
                    break
                time.sleep(0.05)
            else:
                pytest.fail("alice's turn never completed")

            _expect_no_frame(bob_ws, timeout=1.0)


# ---------------------------------------------------------------------------
# Fix round 1: frame ordering around connect, and paginated replay
# ---------------------------------------------------------------------------

def test_a_frame_published_while_the_snapshot_is_being_built_never_arrives_first(monkeypatch):
    """Fix round 1, findings 2/5(a): the live pump used to start before
    the snapshot was even built, so a frame published during that build
    (here: during the ``latest_seq`` call the snapshot's own cursor comes
    from) could reach the client before the ``snapshot`` frame itself.
    The first frame on any connection must always be the snapshot, and a
    frame published mid-build is already covered by the snapshot's own
    cursor, so it must never be forwarded again afterward either."""
    with TestClient(create_app()) as c:
        _register(c, "alice")
        bot_id = _create_bot(c)

        real_latest_seq = EventHub.latest_seq

        async def _publish_then_latest_seq(self, user_id):
            # Simulate a frame landing on this connection's live
            # subscription (already open -- subscribe() runs before the
            # snapshot is built) while the snapshot is still assembling.
            await self.publish(user_id, {
                "type": "bot_status", "bot_id": bot_id, "status": "on_it", "activity": None,
            })
            return await real_latest_seq(self, user_id)

        monkeypatch.setattr(EventHub, "latest_seq", _publish_then_latest_seq)

        with c.websocket_connect("/api/events", headers=O) as ws:
            frame = ws.receive_json()
            assert frame["type"] == "snapshot"
            # Already covered by the snapshot's own (later) cursor --
            # must be dropped, not delivered a second time as "live".
            _expect_no_frame(ws, timeout=1.0)


async def test_frame_sender_send_live_never_drops_a_text_delta():
    """A live-only ``text_delta`` (never stored) piggybacks its ``seq``
    on the latest STORED event without advancing it (``EventHub.
    publish``), so it must never be compared against ``_last_sent_seq``
    -- otherwise every delta after the first stored frame at that same
    seq looks like an already-covered duplicate and gets silently
    dropped (caught by ``test_posting_a_message_streams_the_turn_to_the_
    bots_own_socket`` during this fix's own first pass)."""
    sent: list[dict] = []

    class _FakeWebSocket:
        async def send_json(self, frame: dict) -> None:
            sent.append(frame)

    sender = events_module._FrameSender(_FakeWebSocket())
    sender._last_sent_seq = 5  # as if a stored event at seq=5 was already sent

    await sender.send_live({"type": "bot_status", "seq": 5, "status": "on_it", "bot_id": "b", "activity": None})
    await sender.send_live({"type": "text_delta", "seq": 5, "thread_id": "t", "message_id": "m", "delta": "a"})
    await sender.send_live({"type": "text_delta", "seq": 5, "thread_id": "t", "message_id": "m", "delta": "b"})

    assert [f.get("delta") for f in sent if f["type"] == "text_delta"] == ["a", "b"]
    assert not any(f["type"] == "bot_status" for f in sent)  # the genuine duplicate was still dropped


async def test_frame_sender_send_live_never_drops_a_computer_step():
    """The computer card's ``computer_step`` is live only like ``text_delta``: never dropped as a duplicate."""
    sent: list[dict] = []

    class _FakeWebSocket:
        async def send_json(self, frame: dict) -> None:
            sent.append(frame)

    sender = events_module._FrameSender(_FakeWebSocket())
    sender._last_sent_seq = 5
    for n in (1, 2):
        await sender.send_live({"type": "computer_step", "seq": 5, "bot_id": "b", "step": n})
    assert [f["step"] for f in sent] == [1, 2]


def test_the_snapshot_carries_each_working_bots_computer_steps():
    with TestClient(create_app()) as c:
        _register(c, "alice")
        bot_id = _create_bot(c)
        with c.websocket_connect("/api/events", headers=O) as ws:
            assert ws.receive_json()["computer_steps"] == {}
        user_id = c.get("/api/auth/me").json()["id"]
        c.app.state.computer_steps.listen(user_id, {
            "type": "computer_step", "bot_id": bot_id, "thread_id": "t", "run_id": "r", "step": 1,
            "kind": "look", "line": "Looked at the screen", "host": "shop.example", "at": "x", "seq": 3})
        with c.websocket_connect("/api/events", headers=O) as ws:
            steps = ws.receive_json()["computer_steps"]
            assert [f["line"] for f in steps[bot_id]] == ["Looked at the screen"]


def test_the_snapshot_carries_each_bots_kept_computer_runs():
    with TestClient(create_app()) as c:
        _register(c, "alice")
        bot_id = _create_bot(c)
        with c.websocket_connect("/api/events", headers=O) as ws:
            assert ws.receive_json()["computer_kept"] == {}
        user_id = c.get("/api/auth/me").json()["id"]
        hub = c.app.state.computer_steps
        hub.listen(user_id, {
            "type": "computer_step", "bot_id": bot_id, "thread_id": "t", "run_id": "r", "step": 1,
            "kind": "look", "line": "Looked at the screen", "host": "shop.example", "at": "x"})
        hub.listen(user_id, {"type": "bot_status", "bot_id": bot_id, "status": "resting", "activity": None})
        with c.websocket_connect("/api/events", headers=O) as ws:
            snapshot = ws.receive_json()
            assert snapshot["computer_steps"] == {}
            assert [[f["run_id"] for f in run] for run in snapshot["computer_kept"][bot_id]] == [["r"]]


def test_the_snapshot_carries_each_working_bots_run_steps():
    with TestClient(create_app()) as c:
        _register(c, "alice")
        bot_id = _create_bot(c)
        with c.websocket_connect("/api/events", headers=O) as ws:
            assert ws.receive_json()["run_steps"] == {}
        user_id = c.get("/api/auth/me").json()["id"]
        c.app.state.run_steps.listen(user_id, {
            "type": "run_step", "bot_id": bot_id, "thread_id": "t", "run_id": "r", "step": 1, "kind": "search",
            "line": "Searched the web", "host": None, "at": "x", "state": "start", "seq": 3})
        with c.websocket_connect("/api/events", headers=O) as ws:
            steps = ws.receive_json()["run_steps"]
            assert [(f["line"], f["state"]) for f in steps[bot_id]] == [("Searched the web", "start")]


async def test_frame_sender_replay_pages_through_since_to_exhaustion(monkeypatch):
    """Fix round 1, finding 5(c): ``since()`` is capped per call -- a
    resume's replay used to make exactly one such call, so anything
    beyond the first page was silently dropped. ``_FrameSender.replay``
    must keep paging until a page comes back short."""
    monkeypatch.setattr(events_module, "_REPLAY_PAGE_SIZE", 2)

    config = load_config()
    await init_db(config)
    user = await register_user(config, "paging-alice", "pw-123456")
    hub = EventHub(config)

    published_seqs = [
        await hub.publish(user.id, {"type": "bot_status", "bot_id": "b", "status": "on_it", "activity": None})
        for _ in range(5)
    ]

    sent: list[dict] = []

    class _FakeWebSocket:
        async def send_json(self, frame: dict) -> None:
            sent.append(frame)

    sender = events_module._FrameSender(_FakeWebSocket())
    await sender.replay(hub, user.id, 0)

    assert [f["seq"] for f in sent] == published_seqs  # every event, in order, past one page's worth
