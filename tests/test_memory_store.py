"""MemoryStore (memory Task 2): sealed text, keyed fingerprints, one row per memory per scope."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from roost.config import load_config
from roost.crypto.encryption import decrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session, get_db_path, init_db
from roost.gateway.auth import register_user
from roost.memory.fingerprint import fingerprint, memory_key
from roost.memory.models import SHARED_SCOPE, MemoryDraft, memory_out, scope_of
from roost.memory.store import MemoryExists, MemoryStore
from team_helpers import make_bot


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _draft(text="Ana's birthday is in May.", kind="about_you", bot_id=None, **fields) -> MemoryDraft:
    base = dict(kind=kind, text=text, bot_id=bot_id, source="user", created_by_bot=None, importance=3,
                pinned=False, tainted=False)
    return MemoryDraft(**{**base, **fields})


def _raw(cfg, sql, params=()):
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def _iso(delta_days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=delta_days)).isoformat()


async def test_text_is_sealed_under_memories_text(cfg, user_id):
    memory, _ = await MemoryStore(cfg).upsert(user_id, _draft())
    [(raw,)] = _raw(cfg, "SELECT text FROM memories WHERE id = ?", (memory.id,))
    assert raw.startswith("enc:v2:")
    dek = await get_user_dek(cfg, user_id)
    assert decrypt(raw, dek, user_aad(user_id, "memories:text")) == "Ana's birthday is in May."
    with pytest.raises(Exception):
        decrypt(raw, dek, user_aad("someone-else", "memories:text"))


async def test_saving_the_same_thing_again_refreshes_one_row(cfg, user_id):
    store = MemoryStore(cfg)
    first, created_first = await store.upsert(user_id, _draft("Ana's birthday is in May.", importance=2))
    second, created_second = await store.upsert(user_id, _draft("ana's  birthday is in may", importance=4))
    assert created_first and not created_second
    assert second.id == first.id and second.importance == 4
    assert second.updated_at > first.updated_at
    assert _raw(cfg, "SELECT COUNT(*) FROM memories") == [(1,)]


async def test_the_fingerprint_is_keyed_and_per_user(cfg, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    text = "Ana's birthday is in May."
    await MemoryStore(cfg).upsert(user_id, _draft(text))
    await MemoryStore(cfg).upsert(bob, _draft(text))
    rows = _raw(cfg, "SELECT fingerprint FROM memories")
    assert len({r[0] for r in rows}) == 2
    assert all(r[0] != hashlib.sha256(text.encode()).hexdigest() for r in rows)
    dek = await get_user_dek(cfg, user_id)
    assert memory_key(dek) != dek
    assert fingerprint(dek, "about_you", text) == rows[0][0] or fingerprint(dek, "about_you", text) == rows[1][0]


async def test_about_you_is_shared_and_other_kinds_are_per_bot(cfg, user_id):
    store = MemoryStore(cfg)
    one, two = await make_bot(cfg, user_id, "One"), await make_bot(cfg, user_id, "Two")
    await store.upsert(user_id, _draft("Ana likes orchids."))
    await store.upsert(user_id, _draft("Short answers please.", kind="preference", bot_id=one.id))
    assert {m.text for m in await store.list_scopes(user_id, one.id)} == {"Ana likes orchids.",
                                                                          "Short answers please."}
    assert {m.text for m in await store.list_scopes(user_id, two.id)} == {"Ana likes orchids."}
    with pytest.raises(ValueError):
        await store.upsert(user_id, _draft("x", kind="fact", bot_id=None))
    assert scope_of("about_you", "b1") == (None, SHARED_SCOPE)
    assert scope_of("fact", "b1") == ("b1", "b1")


async def test_another_users_memory_is_none_everywhere(cfg, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    store = MemoryStore(cfg)
    memory, _ = await store.upsert(user_id, _draft())
    assert await store.get(bob, memory.id) is None
    assert await store.update(bob, memory.id, pinned=True) is None
    assert await store.delete(bob, memory.id) is False
    await store.touch_recalled(bob, [memory.id])
    mine = await store.get(user_id, memory.id)
    assert mine is not None and mine.last_recalled_at is None and not mine.pinned
    assert "user_id" not in memory_out(mine) and "fingerprint" not in memory_out(mine)


async def test_fade_archives_only_old_minor_unpinned_bot_memories(cfg, user_id):
    store = MemoryStore(cfg)
    bot = await make_bot(cfg, user_id, "One")
    base = dict(kind="fact", bot_id=bot.id, source="bot", created_by_bot=bot.id, importance=1)
    target, _ = await store.upsert(user_id, _draft("target", **base))
    others = {
        "important": await store.upsert(user_id, _draft("important", **{**base, "importance": 3})),
        "pinned": await store.upsert(user_id, _draft("pinned", **{**base, "pinned": True})),
        "user": await store.upsert(user_id, _draft("user", **{**base, "source": "user"})),
        "recalled": await store.upsert(user_id, _draft("recalled", **base)),
        "fresh": await store.upsert(user_id, _draft("fresh", **base)),
    }
    old = _iso(-90)
    async with db_session(cfg) as db:
        await db.execute("UPDATE memories SET updated_at = ? WHERE text != 'x' AND id != ?",
                         (old, others["fresh"][0].id))
        await db.commit()
    await store.touch_recalled(user_id, [others["recalled"][0].id])
    assert await store.fade(user_id, _iso(-60)) == 1
    assert (await store.get(user_id, target.id)).archived_at is not None
    for name, (memory, _) in others.items():
        assert (await store.get(user_id, memory.id)).archived_at is None, name
    assert [m.id for m in await store.list_scopes(user_id, bot.id, faded=True)].count(target.id) == 1
    assert target.id not in [m.id for m in await store.list_scopes(user_id, bot.id)]


async def test_an_edit_onto_an_existing_memory_raises_memory_exists(cfg, user_id):
    store = MemoryStore(cfg)
    await store.upsert(user_id, _draft("Ana likes orchids."))
    other, _ = await store.upsert(user_id, _draft("Ana likes tulips."))
    with pytest.raises(MemoryExists):
        await store.update(user_id, other.id, text="ana likes orchids")
    renamed = await store.update(user_id, other.id, text="Ana likes roses.", importance=5)
    assert (renamed.text, renamed.importance) == ("Ana likes roses.", 5)
    assert renamed.updated_at >= other.updated_at


async def test_count_bot_saved_since_counts_new_bot_rows_only(cfg, user_id):
    store = MemoryStore(cfg)
    bot = await make_bot(cfg, user_id, "One")
    since = _iso(-1)
    await store.upsert(user_id, _draft("by user", kind="fact", bot_id=bot.id))
    await store.upsert(user_id, _draft("by bot", kind="fact", bot_id=bot.id, source="bot", created_by_bot=bot.id))
    await store.upsert(user_id, _draft("by bot two", source="bot", created_by_bot=bot.id))
    assert await store.count_bot_saved_since(user_id, since) == 2
    assert await store.count_bot_saved_since(user_id, _iso(1)) == 0


async def test_a_user_save_takes_over_a_bots_row_but_not_the_other_way(cfg, user_id):
    store = MemoryStore(cfg)
    bot = await make_bot(cfg, user_id, "Scout")
    base = dict(kind="decision", text="same words", bot_id=bot.id)
    first, _ = await store.upsert(user_id, MemoryDraft(**base, source="bot", created_by_bot=bot.id,
                                                       pinned=False, tainted=False))
    assert first.source == "bot"
    mine, created = await store.upsert(user_id, MemoryDraft(**base, source="user", created_by_bot=None,
                                                            pinned=False, tainted=False))
    assert not created and mine.id == first.id and mine.source == "user"
    again, _ = await store.upsert(user_id, MemoryDraft(**base, source="bot", created_by_bot=bot.id,
                                                       pinned=False, tainted=False))
    assert again.id == first.id and again.source == "user"
