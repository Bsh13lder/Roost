"""Vault: passwords over HTTP (docs/plans/2026-11-08-roost-vault-passwords.md V2, API): write-only passwords, a
refusal that never echoes what was sent, and another user's login is a 404."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user

O = {"Origin": "http://127.0.0.1:18800"}
SECRET = "Sup3r-secret-PW!"
PATH = "/api/vault/passwords"


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _save(c: TestClient, **fields) -> httpx.Response:
    body = {"host": "https://www.Upwork.com/login", "username": "ana@example.com", "password": SECRET, **fields}
    return c.post(PATH, json=body, headers=O)


def test_save_list_patch_delete_and_never_a_password():
    c = _client()
    saved = _save(c)
    assert saved.status_code == 201, saved.text
    row = saved.json()
    assert (row["host"], row["username"], row["always"]) == ("upwork.com", "ana@example.com", False)
    assert set(row) == {"id", "host", "username", "always", "created_at", "updated_at", "last_used_at"}
    listed = c.get(PATH)
    assert [r["id"] for r in listed.json()] == [row["id"]] and SECRET not in listed.text
    patched = c.patch(f"{PATH}/{row['id']}", json={"always": True}, headers=O)
    assert patched.status_code == 200 and patched.json()["always"] is True
    assert c.patch(f"{PATH}/{row['id']}", json={"password": "another-one"}, headers=O).status_code == 200
    assert c.delete(f"{PATH}/{row['id']}", headers=O).status_code == 204
    assert c.get(PATH).json() == []


@pytest.mark.parametrize("fields", [
    {"host": "not a site"}, {"password": ""}, {"password": "x" * 2000}, {"username": "u" * 500},
    {"always": "yes"}, {"extra": 1},
])
def test_a_bad_body_is_refused_without_echoing_it(fields):
    c = _client()
    refused = _save(c, **fields)
    assert refused.status_code == 422
    assert SECRET not in refused.text and "x" * 50 not in refused.text


def test_a_bad_patch_is_refused_without_echoing_it():
    c = _client()
    row = _save(c).json()
    refused = c.patch(f"{PATH}/{row['id']}", json={"password": SECRET * 200}, headers=O)
    assert refused.status_code == 422 and SECRET not in refused.text
    assert c.patch(f"{PATH}/{row['id']}", json={}, headers=O).status_code == 422


def test_a_missing_origin_is_refused():
    c = _client()
    body = {"host": "upwork.com", "username": "u", "password": SECRET}
    assert c.post(PATH, json=body).status_code in (401, 403)


async def test_another_users_login_is_404():
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    for name in ("alice", "bob"):
        await register_user(cfg, name, "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        row = (await alice.post(PATH, json={"host": "upwork.com", "username": "u", "password": SECRET},
                                headers=O)).json()
        assert (await bob.get(PATH)).json() == []
        assert (await bob.patch(f"{PATH}/{row['id']}", json={"always": True}, headers=O)).status_code == 404
        assert (await bob.delete(f"{PATH}/{row['id']}", headers=O)).status_code == 404
