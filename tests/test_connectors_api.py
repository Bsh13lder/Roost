"""Connectors over HTTP (design §5): the key is write-only, never in any response or 422, and another user's
connector is a 404."""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from roost.config import load_config
from roost.connectors import texts
from roost.db.connection import get_db_path
from roost.db.migrations import latest_version
from roost.gateway.app import create_app

ORIGIN = {"Origin": "http://127.0.0.1:18800"}
SECRET = "sk-live-0123456789abcdefWXYZ"
GOOD = {"name": "Search tool", "purpose": "keyword volumes", "base_url": "https://api.example.com/v1",
        "auth_style": "bearer", "secret": SECRET}


def _client(name="alice", app=None) -> tuple[TestClient, str]:
    c = TestClient(app or create_app())
    assert c.post("/api/auth/register", json={"username": name, "password": "pw-123456"}, headers=ORIGIN).status_code == 201
    return c, c.get("/api/bots").json()[0]["id"]


def _raw(sql: str) -> list[tuple]:
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _add(c, **fields):
    r = c.post("/api/connectors", json=GOOD | fields, headers=ORIGIN)
    assert r.status_code == 201, r.text
    return r.json()


def test_the_schema_has_connectors():
    _client()
    assert _raw("PRAGMA user_version")[0][0] == latest_version()
    columns = {row[1] for row in _raw("PRAGMA table_info(connectors)")}
    assert {"secret", "secret_hint", "base_url", "bot_ids", "user_id"} <= columns


def test_add_list_edit_delete_without_the_key():
    c, bot_id = _client()
    made = _add(c)
    assert made["key_hint"] == "key set ••••WXYZ" and made["host"] == "api.example.com"
    assert made["auth_name"] == "Authorization" and made["bot_ids"] is None and "secret" not in made
    listed = c.get("/api/connectors")
    assert [x["id"] for x in listed.json()] == [made["id"]] and SECRET not in listed.text
    changed = c.patch(f"/api/connectors/{made['id']}", json={"purpose": "rankings", "bot_ids": [bot_id]}, headers=ORIGIN)
    assert changed.status_code == 200 and changed.json()["purpose"] == "rankings"
    assert changed.json()["bot_ids"] == [bot_id] and SECRET not in changed.text
    back = c.patch(f"/api/connectors/{made['id']}", json={"all_bots": True}, headers=ORIGIN)
    assert back.json()["bot_ids"] is None
    assert c.delete(f"/api/connectors/{made['id']}", headers=ORIGIN).status_code == 204
    assert c.get("/api/connectors").json() == []
    assert c.delete(f"/api/connectors/{made['id']}", headers=ORIGIN).status_code == 404


def test_every_text_column_is_sealed():
    c, _ = _client()
    _add(c, allowed_prefixes=["/sites"])
    row = _raw("SELECT name, purpose, base_url, auth_name, secret, secret_hint, allowed_prefixes FROM connectors")[0]
    assert all(value.startswith("enc:v2:") for value in row)
    assert SECRET not in repr(_raw("SELECT * FROM connectors"))


def test_a_short_key_shows_no_characters_and_a_new_key_replaces_it():
    c, _ = _client()
    made = _add(c, secret="abc123")
    assert made["key_hint"] == "key set"
    changed = c.patch(f"/api/connectors/{made['id']}", json={"secret": "new-key-000000001234"}, headers=ORIGIN)
    assert changed.json()["key_hint"] == "key set ••••1234"


def test_refusals_are_plain_and_never_echo_the_key():
    c, _ = _client()
    bad = [
        ({"base_url": "http://api.example.com"}, texts.HTTPS_ONLY),
        ({"base_url": "https://127.0.0.1"}, texts.PRIVATE_HOST),
        ({"base_url": "https://localhost/v1"}, texts.PRIVATE_HOST),
        ({"base_url": "https://169.254.169.254/latest"}, texts.PRIVATE_HOST),
        ({"base_url": "https://[::1]/"}, texts.PRIVATE_HOST),
        ({"base_url": "https://10.1.2.3/"}, texts.PRIVATE_HOST),
        ({"base_url": "https://u:p@api.example.com"}, texts.NO_CREDENTIALS),
        ({"base_url": "https://api.example.com:8443"}, texts.NO_PORT),
        ({"secret": SECRET + " x"}, texts.BAD_SECRET),
        ({"secret": SECRET + "\n"}, texts.BAD_SECRET),
        ({"auth_style": "cookie"}, texts.BAD_STYLE),
        ({"auth_style": "header", "auth_name": "Host"}, texts.BAD_AUTH_NAME),
        ({"auth_style": "header", "auth_name": "X Key"}, texts.BAD_AUTH_NAME),
        ({"name": ""}, texts.BAD_NAME),
        ({"allowed_prefixes": ["../x"]}, texts.BAD_PREFIX),
        ({"bot_ids": ["not-mine"]}, texts.BAD_BOTS),
        ({"surprise": SECRET}, texts.BAD_BODY),
    ]
    for fields, sentence in bad:
        r = c.post("/api/connectors", json=GOOD | fields, headers=ORIGIN)
        assert r.status_code == 422, fields
        assert r.json() == {"detail": sentence}, fields
        assert SECRET not in r.text
    missing = c.post("/api/connectors", json={"secret": SECRET}, headers=ORIGIN)
    assert missing.status_code == 422 and SECRET not in missing.text
    no_key = c.post("/api/connectors", json={k: v for k, v in GOOD.items() if k != "secret"}, headers=ORIGIN)
    assert no_key.json() == {"detail": texts.NEEDS_SECRET}
    junk = c.post("/api/connectors", content=b"{not json " + SECRET.encode(), headers=ORIGIN | {"content-type": "application/json"})
    assert junk.status_code == 422 and SECRET not in junk.text
    assert c.get("/api/connectors").json() == []


def test_a_taken_name_and_a_new_site_without_the_key():
    c, _ = _client()
    made = _add(c)
    r = c.post("/api/connectors", json=GOOD | {"name": "SEARCH TOOL"}, headers=ORIGIN)
    assert r.json() == {"detail": texts.NAME_TAKEN}
    moved = c.patch(f"/api/connectors/{made['id']}", json={"base_url": "https://other.example.org"}, headers=ORIGIN)
    assert moved.status_code == 422 and moved.json() == {"detail": texts.NEW_HOST_NEEDS_KEY}
    same_host = c.patch(f"/api/connectors/{made['id']}", json={"base_url": "https://api.example.com/v2"}, headers=ORIGIN)
    assert same_host.status_code == 200 and same_host.json()["base_url"] == "https://api.example.com/v2"
    with_key = c.patch(f"/api/connectors/{made['id']}",
                       json={"base_url": "https://other.example.org", "secret": "fresh-key-12345678"}, headers=ORIGIN)
    assert with_key.status_code == 200 and with_key.json()["host"] == "other.example.org"


def test_switching_the_style_sets_its_name():
    c, _ = _client()
    made = _add(c)
    q = c.patch(f"/api/connectors/{made['id']}", json={"auth_style": "query", "auth_name": "key"}, headers=ORIGIN)
    assert (q.json()["auth_style"], q.json()["auth_name"]) == ("query", "key")
    h = c.patch(f"/api/connectors/{made['id']}", json={"auth_style": "bearer"}, headers=ORIGIN)
    assert h.json()["auth_name"] == "Authorization"
    bad = c.patch(f"/api/connectors/{made['id']}", json={"auth_style": "header"}, headers=ORIGIN)
    assert bad.json() == {"detail": texts.BAD_AUTH_NAME}


def test_another_users_connector_is_404():
    app = create_app()
    alice, _ = _client("alice", app)
    made = _add(alice)
    bob = TestClient(app)
    # Registration is closed after the first user; log bob in through a second account made directly.
    import asyncio

    from roost.gateway.auth import register_user
    asyncio.run(register_user(load_config(), "bob", "pw-123456"))
    assert bob.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"}, headers=ORIGIN).status_code == 200
    assert bob.get("/api/connectors").json() == []
    assert bob.patch(f"/api/connectors/{made['id']}", json={"purpose": "x"}, headers=ORIGIN).status_code == 404
    assert bob.delete(f"/api/connectors/{made['id']}", headers=ORIGIN).status_code == 404
    assert len(alice.get("/api/connectors").json()) == 1


def test_writes_need_the_origin_and_reads_need_a_login():
    c, _ = _client()
    assert c.post("/api/connectors", json=GOOD).status_code == 403
    assert TestClient(create_app()).get("/api/connectors").status_code == 401
