"""Unit tests for ``roost.talk.store.TalkStore`` and the ``thread_out``/
``message_out`` serializers it ships with — see
``roost/gateway/routes/threads.py`` for the HTTP layer.

Per the Task 4 brief's minimum tests: message body is ciphertext on
disk; ``seq`` increases per thread; ``list_messages(after_seq=)`` pages;
a thread (and its messages) scoped to another user is invisible at the
store layer (the gateway turns that into a 404 — see
``tests/test_threads_api.py``). The rest covers behavior the contract
requires that those starter tests don't exercise: thread/title
roundtrips, per-thread seq independence, the ``tainted`` flag, and the
serializers' wire shape.

Deviation note (same one ``tests/test_bot_store.py`` documents): ciphertext
is asserted as ``enc:v2:`` (AAD-bound), not the Global Constraints'
literal ``enc:v1:`` — see that file's module docstring for why.
"""

from __future__ import annotations

import pytest

from roost.bots.models import Avatar, BotDraft
from roost.bots.store import BotStore
from roost.config import load_config
from roost.crypto.encryption import is_encrypted
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.talk.store import Message, TalkStore, Thread, message_out, thread_out

AVATAR = Avatar("round", "#22c55e", "none")


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def store(cfg):
    return TalkStore(cfg)


@pytest.fixture
async def user(cfg):
    u = await register_user(cfg, "alice", "pw-123456")
    return u.id


@pytest.fixture
async def other_user(cfg):
    u = await register_user(cfg, "bob", "pw-123456")
    return u.id


@pytest.fixture
async def bot_id(cfg, user):
    bot = await BotStore(cfg).create(
        user, BotDraft(name="Scout", job="read news", instructions="", avatar=AVATAR),
    )
    return bot.id


# ---------------------------------------------------------------------------
# Brief's starter tests
# ---------------------------------------------------------------------------

async def test_message_body_is_ciphertext_on_disk(store, user, bot_id, cfg):
    thread = await store.create_thread(user, bot_id)
    msg = await store.add_message(user, thread.id, "user", "hello there")

    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT body FROM messages WHERE id=?", (msg.id,))).fetchone()

    assert is_encrypted(row["body"])
    assert row["body"].startswith("enc:v2:")  # AAD-bound, see module docstring
    assert "hello there" not in row["body"]


async def test_seq_increases_per_thread(store, user, bot_id):
    thread = await store.create_thread(user, bot_id)
    m1 = await store.add_message(user, thread.id, "user", "one")
    m2 = await store.add_message(user, thread.id, "bot", "two")
    m3 = await store.add_message(user, thread.id, "user", "three")
    assert [m1.seq, m2.seq, m3.seq] == [1, 2, 3]


async def test_seq_is_independent_per_thread(store, user, bot_id):
    t1 = await store.create_thread(user, bot_id)
    t2 = await store.create_thread(user, bot_id)
    a = await store.add_message(user, t1.id, "user", "hi")
    b = await store.add_message(user, t2.id, "user", "hi")
    assert a.seq == 1
    assert b.seq == 1


async def test_list_messages_pages_with_after_seq(store, user, bot_id):
    thread = await store.create_thread(user, bot_id)
    for i in range(5):
        await store.add_message(user, thread.id, "user", f"msg {i}")

    first_page = await store.list_messages(user, thread.id, after_seq=0, limit=3)
    assert [m.seq for m in first_page] == [1, 2, 3]

    second_page = await store.list_messages(user, thread.id, after_seq=3)
    assert [m.seq for m in second_page] == [4, 5]


async def test_get_thread_other_user_returns_none(store, user, other_user, bot_id):
    thread = await store.create_thread(user, bot_id)
    assert await store.get_thread(other_user, thread.id) is None
    assert await store.get_thread(user, "nonexistent-id") is None


async def test_list_messages_other_user_sees_nothing(store, user, other_user, bot_id):
    thread = await store.create_thread(user, bot_id)
    await store.add_message(user, thread.id, "user", "secret")
    assert await store.list_messages(other_user, thread.id) == []


# ---------------------------------------------------------------------------
# Additional coverage
# ---------------------------------------------------------------------------

async def test_create_thread_defaults_title_none_and_kind_chat(store, user, bot_id):
    thread = await store.create_thread(user, bot_id)
    assert thread.title is None
    assert thread.kind == "chat"
    assert thread.bot_id == bot_id
    assert thread.user_id == user
    assert thread.created_at == thread.updated_at
    assert "T" in thread.created_at  # ISO-8601


async def test_create_thread_with_title_roundtrips_and_encrypts(store, user, bot_id, cfg):
    thread = await store.create_thread(user, bot_id, title="Morning check-in")
    assert thread.title == "Morning check-in"

    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT title FROM threads WHERE id=?", (thread.id,))).fetchone()
    assert is_encrypted(row["title"])
    assert "Morning check-in" not in row["title"]


async def test_get_thread_roundtrips(store, user, bot_id):
    created = await store.create_thread(user, bot_id, title="Catch-up")
    fetched = await store.get_thread(user, created.id)
    assert fetched == created


async def test_list_threads_returns_empty_when_none(store, user, bot_id):
    assert await store.list_threads(user, bot_id) == []


async def test_list_threads_only_own_and_in_creation_order(store, user, other_user, bot_id):
    t1 = await store.create_thread(user, bot_id, title="First")
    t2 = await store.create_thread(user, bot_id, title="Second")

    threads = await store.list_threads(user, bot_id)
    assert [t.id for t in threads] == [t1.id, t2.id]

    assert await store.list_threads(other_user, bot_id) == []


async def test_add_message_role_and_tainted_persist(store, user, bot_id):
    thread = await store.create_thread(user, bot_id)
    msg = await store.add_message(user, thread.id, "activity", "opened a page", tainted=True)
    assert msg.role == "activity"
    assert msg.tainted is True
    assert msg.thread_id == thread.id
    assert msg.user_id == user
    assert "T" in msg.created_at


async def test_add_message_defaults_tainted_false(store, user, bot_id):
    thread = await store.create_thread(user, bot_id)
    msg = await store.add_message(user, thread.id, "user", "hi")
    assert msg.tainted is False


async def test_add_message_accepts_a_pregenerated_message_id(store, user, bot_id):
    """Ruling 15: the turn loop pre-generates a bot reply's id and
    publishes a placeholder event under it before persisting the real
    reply — this keyword-only param is what lets it persist the final
    row under that SAME id instead of a fresh one."""
    thread = await store.create_thread(user, bot_id)
    msg = await store.add_message(user, thread.id, "bot", "final text", message_id="fixed-id-123")
    assert msg.id == "fixed-id-123"

    [fetched] = await store.list_messages(user, thread.id)
    assert fetched.id == "fixed-id-123"


async def test_add_message_without_message_id_still_generates_one(store, user, bot_id):
    thread = await store.create_thread(user, bot_id)
    msg = await store.add_message(user, thread.id, "user", "hi")
    assert msg.id  # some non-empty generated id, unaffected by the new param


async def test_list_messages_default_order_and_roundtrip(store, user, bot_id):
    thread = await store.create_thread(user, bot_id)
    await store.add_message(user, thread.id, "user", "first")
    await store.add_message(user, thread.id, "bot", "second")

    messages = await store.list_messages(user, thread.id)
    assert [m.body for m in messages] == ["first", "second"]
    assert [m.role for m in messages] == ["user", "bot"]


# ---------------------------------------------------------------------------
# list_latest_messages (final review, finding 8)
# ---------------------------------------------------------------------------

async def test_list_latest_messages_returns_the_newest_n_in_chronological_order(store, user, bot_id):
    """Once a thread passes the page limit, ``list_messages``'s
    oldest-first default would silently drop the newest messages from
    both the turn's own model context and a fresh page load.
    ``list_latest_messages`` is the newest ``limit`` messages, still
    returned oldest-to-newest so a caller can append them straight onto
    a transcript."""
    thread = await store.create_thread(user, bot_id)
    for i in range(5):
        await store.add_message(user, thread.id, "user", f"msg {i}")

    latest = await store.list_latest_messages(user, thread.id, limit=3)
    assert [m.body for m in latest] == ["msg 2", "msg 3", "msg 4"]


async def test_list_latest_messages_returns_everything_when_under_the_limit(store, user, bot_id):
    thread = await store.create_thread(user, bot_id)
    await store.add_message(user, thread.id, "user", "only one")

    latest = await store.list_latest_messages(user, thread.id, limit=200)
    assert [m.body for m in latest] == ["only one"]


async def test_list_latest_messages_default_limit_comes_from_the_module_constant(store, user, bot_id, monkeypatch):
    """The default is read dynamically (not baked into the function's
    own default argument at import time), so it can be turned down in
    a test without inserting hundreds of rows -- the same pattern
    ``roost/talk/turn.py``/``roost/talk/runner.py`` already use for
    ``MAX_RUN_SECONDS``."""
    import roost.talk.store as store_module

    monkeypatch.setattr(store_module, "DEFAULT_MESSAGE_PAGE_LIMIT", 2)
    thread = await store.create_thread(user, bot_id)
    for i in range(3):
        await store.add_message(user, thread.id, "user", f"msg {i}")

    latest = await store.list_latest_messages(user, thread.id)
    assert [m.body for m in latest] == ["msg 1", "msg 2"]


async def test_list_latest_messages_other_user_sees_nothing(store, user, other_user, bot_id):
    thread = await store.create_thread(user, bot_id)
    await store.add_message(user, thread.id, "user", "secret")
    assert await store.list_latest_messages(other_user, thread.id) == []


# ---------------------------------------------------------------------------
# thread_out / message_out serializers (roost/talk/store.py)
# ---------------------------------------------------------------------------

def test_thread_out_shape_matches_contract():
    thread = Thread(
        id="t1", user_id="u1", bot_id="b1", title="Hi", kind="chat",
        created_at="2026-10-13T00:00:00+00:00", updated_at="2026-10-13T00:00:01+00:00",
    )
    assert thread_out(thread) == {
        "id": "t1",
        "bot_id": "b1",
        "title": "Hi",
        "kind": "chat",
        "created_at": "2026-10-13T00:00:00+00:00",
        "updated_at": "2026-10-13T00:00:01+00:00",
    }


def test_message_out_shape_matches_contract():
    message = Message(
        id="m1", user_id="u1", thread_id="t1", role="user", body="hello",
        tainted=False, seq=1, created_at="2026-10-13T00:00:00+00:00",
    )
    assert message_out(message) == {
        "id": "m1",
        "thread_id": "t1",
        "role": "user",
        "body": "hello",
        "tainted": False,
        "seq": 1,
        "created_at": "2026-10-13T00:00:00+00:00",
        "kind": "text",
        "author_bot_id": None,
        "reply_to": None,
        "reply_quote": None,
        "reply_tainted": False,
        "media": [],                 # chat pictures (owner, 2026-11-05): every message has the list
    }


async def test_add_message_stores_kind_and_author(store, user, bot_id):
    thread = await store.create_thread(user, bot_id)
    await store.add_message(user, thread.id, "activity", "Chief → Scout: hours?", kind="handoff", author_bot_id=bot_id)
    [stored] = await store.list_messages(user, thread.id)
    assert (stored.kind, stored.author_bot_id, stored.body) == ("handoff", bot_id, "Chief → Scout: hours?")
