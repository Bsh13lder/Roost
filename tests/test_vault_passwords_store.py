"""Vault: passwords (docs/plans/2026-11-08-roost-vault-passwords.md V1, V2, V4): a saved login is sealed, listed
without its password, one row per site and user name, found for its own site or a sub-site, and never another
user's."""

from __future__ import annotations

import sqlite3

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.gateway.auth import register_user
from roost.vault.passwords import (
    VAULT_PASSWORDS_MAX, NewLogin, PasswordNotFound, PasswordsFull, VaultPasswordStore, host_serves,
)

_UPWORK = NewLogin(host="upwork.com", username="ana@example.com", password="s3cret-Pass!")


@pytest.fixture
async def rig():
    cfg = load_config()
    await init_db(cfg)
    alice = await register_user(cfg, "alice", "pw-123456")
    bob = await register_user(cfg, "bob", "pw-123456")
    return cfg, VaultPasswordStore(cfg), alice.id, bob.id


def _rows(cfg) -> list[sqlite3.Row]:
    with sqlite3.connect(get_db_path(cfg)) as db:
        db.row_factory = sqlite3.Row
        return db.execute("SELECT * FROM vault_passwords").fetchall()


async def test_a_saved_login_is_sealed_and_listed_without_its_password(rig):
    cfg, store, alice, _ = rig
    saved = await store.save(alice, _UPWORK)
    assert (saved.host, saved.username, saved.always) == ("upwork.com", "ana@example.com", False)
    assert not hasattr(saved, "password")
    raw = dict(_rows(cfg)[0])
    for column in ("host", "username", "password"):
        assert raw[column].startswith("enc:v2:"), column
    assert "s3cret" not in repr(raw) and "ana@example.com" not in repr(raw) and "upwork" not in repr(raw)


async def test_the_same_site_and_user_replaces_the_password(rig):
    _, store, alice, _ = rig
    first = await store.save(alice, _UPWORK)
    again = await store.save(alice, NewLogin(host="upwork.com", username="ana@example.com", password="new-one"))
    assert again.id == first.id and len(await store.list(alice)) == 1
    assert (await store.secret(alice, first.id)).password == "new-one"


async def test_found_for_its_site_and_sub_sites_never_the_reverse(rig):
    _, store, alice, _ = rig
    await store.save(alice, _UPWORK)
    assert [s.username for s in await store.for_host(alice, "www.upwork.com")] == ["ana@example.com"]
    assert [s.username for s in await store.for_host(alice, "upwork.com")] == ["ana@example.com"]
    assert await store.for_host(alice, "evilupwork.com") == ()
    sub = NewLogin(host="accounts.example.org", username="u", password="p")
    await store.save(alice, sub)
    assert await store.for_host(alice, "example.org") == ()


@pytest.mark.parametrize(("saved", "page", "serves"), [
    ("upwork.com", "upwork.com", True), ("upwork.com", "www.upwork.com", True),
    ("upwork.com", "a.b.upwork.com", True), ("upwork.com", "notupwork.com", False),
    ("a.upwork.com", "upwork.com", False), ("upwork.com", "upwork.com.evil.io", False), ("", "x.com", False),
])
def test_host_serves(saved, page, serves):
    assert host_serves(saved, page) is serves


async def test_another_users_login_is_never_found(rig):
    _, store, alice, bob = rig
    saved = await store.save(alice, _UPWORK)
    assert await store.list(bob) == () and await store.for_host(bob, "upwork.com") == ()
    with pytest.raises(PasswordNotFound):
        await store.secret(bob, saved.id)
    with pytest.raises(PasswordNotFound):
        await store.delete(bob, saved.id)
    with pytest.raises(PasswordNotFound):
        await store.patch(bob, saved.id, password="x", always=None)


async def test_patch_always_and_password_then_delete(rig):
    _, store, alice, _ = rig
    saved = await store.save(alice, _UPWORK)
    patched = await store.patch(alice, saved.id, password=None, always=True)
    assert patched.always is True and (await store.secret(alice, saved.id)).password == "s3cret-Pass!"
    await store.patch(alice, saved.id, password="changed", always=None)
    assert (await store.secret(alice, saved.id)).password == "changed"
    await store.mark_used(alice, saved.id)
    assert (await store.list(alice))[0].last_used_at is not None
    await store.delete(alice, saved.id)
    assert await store.list(alice) == ()


async def test_a_full_vault_refuses_a_new_site(rig, monkeypatch):
    import roost.vault.passwords as passwords

    _, store, alice, _ = rig
    monkeypatch.setattr(passwords, "VAULT_PASSWORDS_MAX", 1)
    await store.save(alice, _UPWORK)
    await store.save(alice, NewLogin(host="upwork.com", username="ana@example.com", password="still fits"))
    with pytest.raises(PasswordsFull):
        await store.save(alice, NewLogin(host="b.com", username="x", password="y"))
    assert VAULT_PASSWORDS_MAX == 200


async def test_the_repr_of_a_login_hides_its_password(rig):
    _, store, alice, _ = rig
    saved = await store.save(alice, _UPWORK)
    full = await store.secret(alice, saved.id)
    assert "s3cret" not in repr(full) and "s3cret" not in repr(_UPWORK)
