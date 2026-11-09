"""The Pay card's routes (P4, P6): a bad body is refused in fixed words that never echo it, another user's cards
and Ask cards are 404, and Vault: cards lists brand and last 4 only."""

from __future__ import annotations

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.gateway.routes.payments import PAY_BODY_TEXT
from roost.payments.cards import NewCard

ORIGIN = {"Origin": "http://127.0.0.1:18800"}
NUMBER = "4242424242424242"


@pytest.fixture
async def rig():
    cfg = load_config()
    await init_db(cfg)
    app = create_app()
    users = {}
    for name in ("alice", "bob"):
        users[name] = (await register_user(cfg, name, "pw-123456")).id
    clients = {}
    for name in users:
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
        await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=ORIGIN)
        clients[name] = client
    yield app, users, clients
    for client in clients.values():
        await client.aclose()


@pytest.mark.parametrize("body", [{"number": NUMBER, "cvc": "73712345"}, {"number": NUMBER, "extra": "x"},
                                  {"number": 4242424242424242}, ["nope"]])
async def test_a_bad_pay_body_never_echoes_what_was_sent(rig, body):
    _, _, clients = rig
    r = await clients["alice"].post("/api/approvals/any-card/pay", json=body, headers=ORIGIN)
    assert r.status_code == 422 and r.json()["detail"] == PAY_BODY_TEXT and NUMBER not in r.text


async def test_an_unknown_card_is_404(rig):
    _, _, clients = rig
    r = await clients["alice"].post("/api/approvals/nope/pay", json={"cvc": "123"}, headers=ORIGIN)
    assert r.status_code == 404
    assert (await clients["alice"].get("/api/approvals/nope/pay")).status_code == 404


async def test_vault_cards_show_brand_and_last4_and_only_yours(rig):
    app, users, clients = rig
    saved = await app.state.payment_cards.save(users["alice"], NewCard(number=NUMBER, exp="12/28", name="Ana"))
    r = await clients["alice"].get("/api/payment-cards")
    assert r.json() == [{"id": saved.id, "brand": "visa", "last4": "4242", "last_used_at": None}]
    assert NUMBER not in r.text and "12/28" not in r.text
    assert (await clients["bob"].get("/api/payment-cards")).json() == []
    assert (await clients["bob"].delete(f"/api/payment-cards/{saved.id}", headers=ORIGIN)).status_code == 404
    assert (await clients["alice"].delete(f"/api/payment-cards/{saved.id}")).status_code in (401, 403)
    assert (await clients["alice"].delete(f"/api/payment-cards/{saved.id}", headers=ORIGIN)).status_code == 204
    assert (await clients["alice"].get("/api/payment-cards")).json() == []
