"""Vault: cards (the Pay card, P6): a saved card is sealed, listed only as brand and last 4, one row per card,
and never holds a security code. Another user's card is not found."""

from __future__ import annotations

import sqlite3

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.gateway.auth import register_user
from roost.payments.cards import CardNotFound, CardStore, CardsFull, NewCard

_VISA = NewCard(number="4242424242424242", exp="12/28", name="Ana Garcia")


@pytest.fixture
async def rig():
    cfg = load_config()
    await init_db(cfg)
    alice = await register_user(cfg, "alice", "pw-123456")
    bob = await register_user(cfg, "bob", "pw-123456")
    return cfg, CardStore(cfg), alice.id, bob.id


def _rows(cfg) -> list[sqlite3.Row]:
    with sqlite3.connect(get_db_path(cfg)) as db:
        db.row_factory = sqlite3.Row
        return db.execute("SELECT * FROM payment_cards").fetchall()


async def test_a_saved_card_is_sealed_and_listed_as_brand_and_last4(rig):
    cfg, store, alice, _ = rig
    saved = await store.save(alice, _VISA)
    assert (saved.brand, saved.last4) == ("visa", "4242")
    listed = await store.list(alice)
    assert [(c.id, c.brand, c.last4) for c in listed] == [(saved.id, "visa", "4242")]
    raw = dict(_rows(cfg)[0])
    for column in ("number", "exp", "name", "brand", "last4"):
        assert str(raw[column]).startswith("enc:v2"), column
    blob = " ".join(str(v) for v in raw.values())
    assert "4242424242424242" not in blob and "Ana" not in blob and "12/28" not in blob


async def test_the_same_card_twice_is_one_row(rig):
    cfg, store, alice, _ = rig
    first = await store.save(alice, _VISA)
    again = await store.save(alice, NewCard(number="4242424242424242", exp="01/30", name="Ana G"))
    assert again.id == first.id and len(_rows(cfg)) == 1
    assert (await store.secret(alice, first.id)).exp == "01/30"


async def test_the_full_card_is_read_only_by_its_owner(rig):
    _, store, alice, bob = rig
    saved = await store.save(alice, _VISA)
    full = await store.secret(alice, saved.id)
    assert (full.number, full.exp, full.name) == ("4242424242424242", "12/28", "Ana Garcia")
    with pytest.raises(CardNotFound):
        await store.secret(bob, saved.id)
    assert await store.list(bob) == ()


async def test_delete_removes_only_your_own_card(rig):
    cfg, store, alice, bob = rig
    saved = await store.save(alice, _VISA)
    with pytest.raises(CardNotFound):
        await store.delete(bob, saved.id)
    await store.delete(alice, saved.id)
    assert _rows(cfg) == []


async def test_used_marks_the_time(rig):
    _, store, alice, _ = rig
    saved = await store.save(alice, _VISA)
    await store.mark_used(alice, saved.id)
    assert (await store.list(alice))[0].last_used_at


async def test_no_more_than_the_cap(rig, monkeypatch):
    _, store, alice, _ = rig
    monkeypatch.setattr("roost.payments.cards.PAYMENT_CARDS_MAX", 1)
    await store.save(alice, _VISA)
    with pytest.raises(CardsFull):
        await store.save(alice, NewCard(number="5555555555554444", exp="12/28", name="Ana Garcia"))
