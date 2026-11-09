"""Direct unit tests for ``roost.events.hub.EventHub`` — ``publish``,
``since`` and ``subscribe``/``Subscription`` (contract's "Events"
section). The WS route built on top of this is covered end-to-end by
``tests/test_events_ws.py``; this file is the hub's own contract.
"""

from __future__ import annotations

import asyncio

import pytest

from roost.config import load_config
from roost.crypto.encryption import is_encrypted
from roost.db.connection import db_session, init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    u = await register_user(cfg, "alice", "pw-123456")
    return u.id


async def test_since_with_no_events_returns_empty(cfg, user_id):
    hub = EventHub(cfg)
    assert await hub.since(user_id, 0) == []


async def test_latest_seq_is_zero_with_no_events(cfg, user_id):
    hub = EventHub(cfg)
    assert await hub.latest_seq(user_id) == 0


async def test_publish_persists_and_returns_an_increasing_seq(cfg, user_id):
    hub = EventHub(cfg)
    seq1 = await hub.publish(user_id, {"type": "bot_status", "bot_id": "b1", "status": "on_it", "activity": None})
    seq2 = await hub.publish(user_id, {"type": "bot_status", "bot_id": "b1", "status": "resting", "activity": None})
    assert seq2 > seq1
    assert await hub.latest_seq(user_id) == seq2


async def test_published_events_are_encrypted_at_rest(cfg, user_id):
    hub = EventHub(cfg)
    await hub.publish(user_id, {"type": "bot_status", "bot_id": "secret-bot-id", "status": "on_it", "activity": None})

    async with db_session(cfg) as db:
        cursor = await db.execute("SELECT payload FROM events WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
    assert is_encrypted(row["payload"])
    assert "secret-bot-id" not in row["payload"]


async def test_text_delta_is_never_stored(cfg, user_id):
    hub = EventHub(cfg)
    await hub.publish(user_id, {"type": "text_delta", "thread_id": "t1", "message_id": "m1", "delta": "hi"})

    async with db_session(cfg) as db:
        cursor = await db.execute("SELECT COUNT(*) AS n FROM events WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
    assert row["n"] == 0
    assert await hub.since(user_id, 0) == []


async def test_text_delta_seq_does_not_advance_the_real_cursor(cfg, user_id):
    hub = EventHub(cfg)
    stored_seq = await hub.publish(user_id, {"type": "bot_status", "bot_id": "b1", "status": "on_it", "activity": None})
    delta_seq = await hub.publish(user_id, {"type": "text_delta", "thread_id": "t1", "message_id": "m1", "delta": "hi"})
    assert delta_seq == stored_seq  # piggybacks on the last real seq, doesn't consume a new one


async def test_since_returns_events_strictly_after_the_cursor_in_order(cfg, user_id):
    hub = EventHub(cfg)
    seq1 = await hub.publish(user_id, {"type": "bot_status", "bot_id": "b1", "status": "on_it", "activity": None})
    seq2 = await hub.publish(user_id, {"type": "bot_status", "bot_id": "b1", "status": "resting", "activity": None})

    events = await hub.since(user_id, seq1)
    assert [e["seq"] for e in events] == [seq2]
    assert events[0]["status"] == "resting"


async def test_subscribe_receives_live_frames_with_seq_attached(cfg, user_id):
    hub = EventHub(cfg)
    sub = hub.subscribe(user_id)
    await hub.publish(user_id, {"type": "bot_status", "bot_id": "b1", "status": "on_it", "activity": None})

    frame = await asyncio.wait_for(sub.__anext__(), timeout=2)
    assert frame["type"] == "bot_status"
    assert isinstance(frame["seq"], int)
    sub.close()


async def test_a_second_users_subscription_never_sees_the_first_users_events(cfg, user_id):
    other = await register_user(cfg, "bob", "pw-123456")
    hub = EventHub(cfg)
    bob_sub = hub.subscribe(other.id)
    await hub.publish(user_id, {"type": "bot_status", "bot_id": "alice-bot", "status": "on_it", "activity": None})

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(bob_sub.__anext__(), timeout=0.2)
    bob_sub.close()


async def test_close_is_idempotent_and_ends_iteration():
    hub = EventHub(load_config())
    sub = hub.subscribe("some-user")
    sub.close()
    sub.close()  # must not raise
    with pytest.raises(StopAsyncIteration):
        await sub.__anext__()
