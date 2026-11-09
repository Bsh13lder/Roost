"""The New bot form stores structured instructions; your own edit (PATCH) stores what you typed."""

from __future__ import annotations

from fastapi.testclient import TestClient

from roost.gateway.app import create_app

ORIGIN = {"Origin": "http://127.0.0.1:18800"}
AVATAR = {"shape": "mochi", "color": "#22c55e", "badge": "none"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"},
                  headers=ORIGIN).status_code == 201
    return c


def test_post_stores_the_five_sections():
    c = _client()
    body = {"name": "Penny", "job": "keeps the books", "avatar": AVATAR,
            "instructions": "Log every receipt.\nNever pay a bill."}
    r = c.post("/api/bots", json=body, headers=ORIGIN)
    assert r.status_code == 201
    text = r.json()["instructions"]
    assert text.startswith("## Who you are and context\n\nYou are Penny. Your job: keeps the books.")
    assert "## What you do\n\nLog every receipt." in text and "## Rules\n\nNever pay a bill." in text
    assert "## Tone" in text and "## Team" in text


def test_patch_keeps_your_own_words():
    c = _client()
    bot_id = c.post("/api/bots", json={"name": "Penny", "job": "books", "avatar": AVATAR}, headers=ORIGIN).json()["id"]
    r = c.patch(f"/api/bots/{bot_id}", json={"instructions": "just this"}, headers=ORIGIN)
    assert r.status_code == 200 and r.json()["instructions"] == "just this"
