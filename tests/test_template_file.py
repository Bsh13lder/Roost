"""Share as Template and From a file (S1.7): a bot file carries name, job,
instructions and look only, never a secret, and reading one creates nothing."""

from __future__ import annotations

import httpx
import pytest

from roost.bots.models import Avatar, Bot, BotStatus
from roost.bots.redact import find_secret_kinds
from roost.bots.store import BotStore
from roost.bots.template_file import (
    SecretInTemplate, TemplateFileError, read_template_file, template_file_for, template_filename,
)
from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}
GOOD = {"format": "roost-bot", "version": 1, "name": "Scout", "job": "finds prices", "instructions": "Be brief.",
        "avatar": {"shape": "egg", "color": "#14b8a6", "screen": "glow"}}


def _bot(**overrides) -> Bot:
    values = dict(id="b1", user_id="u1", name="Scout", job="finds prices", instructions="Be brief.",
                  avatar=Avatar("egg", "#14b8a6", "tasks"), template_id=None, status=BotStatus.RESTING,
                  model_override="claude-haiku-4-5-20251001", created_at="x", updated_at="x")
    return Bot(**{**values, **overrides})


def test_share_holds_name_job_instructions_and_look_only():
    assert template_file_for(_bot()).model_dump() == GOOD


def test_share_refuses_instructions_that_hold_a_key():
    with pytest.raises(SecretInTemplate) as caught:
        template_file_for(_bot(instructions="Call it with sk-ant-api03-abcdefghijklmnopqrstuv please"))
    assert str(caught.value) == "Not shared: an API key or token seems to be in the instructions. Remove it, then share again."


@pytest.mark.parametrize("text", [
    "password: hunter2hunter2", "OPENAI_API_KEY=abc123", "https://bob:s3cret@example.com/x",
    "-----BEGIN RSA PRIVATE KEY-----", "Authorization: Bearer abcdefghijklmnop", "run it --token abcdef123",
    "ghp_abcdefghijklmnopqrstuvwxyz0123", "AKIAABCDEFGHIJKLMNOP",
])
def test_secret_shapes_are_found(text):
    assert find_secret_kinds(text)


@pytest.mark.parametrize("text", [
    "password: leave blank for now", "Use the token you get from settings", "hotkey=ctrl",
    "Read https://example.com/a and summarize", "Keep answers under 200 words.",
])
def test_ordinary_text_is_not_a_secret(text):
    assert find_secret_kinds(text) == ()


def test_a_file_with_parts_roost_does_not_read_is_refused():
    with pytest.raises(TemplateFileError) as caught:
        read_template_file({**GOOD, "chats": [], "model": "x"})
    assert str(caught.value) == "This file has parts Roost does not read: chats, model."


def test_a_file_that_is_not_a_roost_bot_file_is_refused():
    for bad in ({"format": "other"}, {**GOOD, "job": "a\nb"}, {**GOOD, "avatar": {"shape": "hexagon", "color": "#000000"}}, []):
        with pytest.raises(TemplateFileError) as caught:
            read_template_file(bad)
        assert str(caught.value).startswith("This is not a Roost bot file")


def test_the_file_name_is_safe():
    assert template_filename("HiMap SEO") == "HiMap SEO.roost-bot.json"
    assert template_filename("../../etc") == "etc.roost-bot.json"
    assert template_filename("...") == "bot.roost-bot.json"


@pytest.fixture
async def client_and_user():
    cfg = load_config()
    await init_db(cfg)
    app = create_app()
    await register_user(cfg, "alice", "pw-123456")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await client.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
    user_id = (await client.get("/api/auth/me")).json()["id"]
    yield cfg, client, user_id
    await client.aclose()


async def test_share_downloads_the_file_and_never_caches_it(client_and_user):
    cfg, client, user_id = client_and_user
    bot = await make_bot(cfg, user_id, "HiMap SEO")
    r = await client.get(f"/api/bots/{bot.id}/template")
    assert r.status_code == 200
    assert r.headers["content-disposition"] == 'attachment; filename="HiMap SEO.roost-bot.json"'
    assert r.headers["cache-control"] == "no-store"
    assert set(r.json()) == {"format", "version", "name", "job", "instructions", "avatar"}


async def test_share_of_a_bot_holding_a_secret_is_a_plain_422(client_and_user):
    cfg, client, user_id = client_and_user
    bot = await make_bot(cfg, user_id, "Leaky")
    from roost.bots.models import BotPatch
    await BotStore(cfg).update(user_id, bot.id, BotPatch(instructions="token=abcdefgh12345678"))
    r = await client.get(f"/api/bots/{bot.id}/template")
    assert r.status_code == 422 and "Remove it, then share again." in r.json()["detail"]


async def test_checking_a_file_creates_no_bot(client_and_user):
    cfg, client, user_id = client_and_user
    r = await client.post("/api/templates/check", json={"file": GOOD}, headers=O)
    assert r.json() == {"name": "Scout", "job": "finds prices", "instructions": "Be brief.",
                        "avatar": {"shape": "egg", "color": "#14b8a6", "badge": "none", "screen": "glow"},
                        "skills": []}
    assert await BotStore(cfg).list(user_id) == []
    bad = await client.post("/api/templates/check", json={"file": {**GOOD, "chats": []}}, headers=O)
    assert (bad.status_code, bad.json()["detail"]) == (422, "This file has parts Roost does not read: chats.")


async def test_another_users_bot_cannot_be_shared(client_and_user):
    cfg, client, user_id = client_and_user
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bobs = await make_bot(cfg, bob, "Secret")
    assert (await client.get(f"/api/bots/{bobs.id}/template")).status_code == 404


def test_share_carries_the_screen_and_an_older_file_reads_as_glow():
    shared = template_file_for(_bot(avatar=Avatar("monitor", "#3b82f6", "none", "pixel")))
    assert shared.avatar.model_dump() == {"shape": "monitor", "color": "#3b82f6", "screen": "pixel"}
    older = {**GOOD, "avatar": {"shape": "egg", "color": "#14b8a6"}}
    assert read_template_file(older).avatar.screen == "glow"
