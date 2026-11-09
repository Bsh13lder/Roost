"""The profile's data routes (S1.9, S1.10): notify, links, made by."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.documents.service import DocumentService
from roost.documents.store import DocumentStore
from roost.events.hub import EventHub
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.money.expense_store import ExpenseStore
from roost.money.project_store import ProjectStore
from roost.money.service import ExpenseEntry, MoneyService
from roost.notes.models import NoteDraft
from roost.notes.service import NoteService
from roost.notes.store import NoteStore
from roost.talk.store import TalkStore
from roost.tasks.models import TaskDraft
from roost.tasks.service import TaskService
from roost.tasks.store import TaskStore
from team_helpers import frames_so_far, make_bot

O = {"Origin": "http://127.0.0.1:18800"}


async def _login(app, cfg, username: str) -> httpx.AsyncClient:
    await register_user(cfg, username, "pw-123456")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    r = await client.post("/api/auth/login", json={"username": username, "password": "pw-123456"}, headers=O)
    assert r.status_code == 200
    return client


@pytest.fixture
async def rig():
    cfg = load_config()
    await init_db(cfg)
    app = create_app()
    alice = await _login(app, cfg, "alice")
    user_id = (await alice.get("/api/auth/me")).json()["id"]
    yield cfg, app, alice, user_id
    await alice.aclose()


async def _make_everything(cfg, user_id, bot_id):
    events = EventHub(cfg)
    await TaskService(TaskStore(cfg), events).add(user_id, TaskDraft(title=f"task by {bot_id[:4]}"), created_by_bot=bot_id)
    money = MoneyService(ProjectStore(cfg), ExpenseStore(cfg), events)
    await money.log_expense(user_id, ExpenseEntry(amount=Decimal("9.99"), spent_at="2026-10-14", project="food"),
                            created_by_bot=bot_id)
    await NoteService(NoteStore(cfg), events).add(user_id, NoteDraft(title=f"note {bot_id[:4]}", content="x"),
                                                  created_by_bot=bot_id)
    await DocumentService(DocumentStore(cfg), events).create_doc(user_id, f"doc {bot_id[:4]}", "# x",
                                                                 created_by_bot=bot_id)


async def test_made_lists_only_what_that_bot_made(rig):
    cfg, app, alice, user_id = rig
    helper, other = await make_bot(cfg, user_id, "Helper"), await make_bot(cfg, user_id, "Other")
    await _make_everything(cfg, user_id, helper.id)
    await TaskService(TaskStore(cfg), EventHub(cfg)).add(user_id, TaskDraft(title="by Other"), created_by_bot=other.id)
    await TaskService(TaskStore(cfg), EventHub(cfg)).add(user_id, TaskDraft(title="by you"))
    made = (await alice.get(f"/api/bots/{helper.id}/made")).json()
    assert [t["title"] for t in made["tasks"]] == [f"task by {helper.id[:4]}"]
    assert [e["amount"] for e in made["expenses"]] == ["9.99"] and made["expenses"][0]["project"] == "food"
    assert [n["title"] for n in made["notes"]] == [f"note {helper.id[:4]}"]
    assert [d["title"] for d in made["documents"]] == [f"doc {helper.id[:4]}"]
    other_made = (await alice.get(f"/api/bots/{other.id}/made")).json()
    assert ([t["title"] for t in other_made["tasks"]], other_made["notes"]) == (["by Other"], [])


async def test_links_are_newest_first_with_their_real_host(rig):
    cfg, app, alice, user_id = rig
    bot = await make_bot(cfg, user_id, "Helper")
    talk = TalkStore(cfg)
    thread = await talk.create_thread(user_id, bot.id)
    await talk.add_message(user_id, thread.id, "user", "read https://example.com/a please")
    await talk.add_message(user_id, thread.id, "bot", "done: https://elpais.com/x and javascript:alert(1)",
                           author_bot_id=bot.id)
    links = (await alice.get(f"/api/bots/{bot.id}/links")).json()
    assert [(l["url"], l["host"]) for l in links] == [
        ("https://elpais.com/x", "elpais.com"), ("https://example.com/a", "example.com")]
    assert set(links[0]) == {"url", "host", "message_id", "thread_id", "created_at"}


async def test_notify_is_on_by_default_and_switches_off(rig):
    cfg, app, alice, user_id = rig
    bot = await make_bot(cfg, user_id, "Helper")
    assert (await alice.get(f"/api/bots/{bot.id}")).json()["notify"] is True
    subscription = app.state.events.subscribe(user_id)
    r = await alice.put(f"/api/bots/{bot.id}/notify", json={"notify": False}, headers=O)
    assert (r.status_code, r.json()["notify"]) == (200, False)
    assert (await BotStore(cfg).get(user_id, bot.id)).notify is False
    assert any(f["type"] == "bot_updated" and f["bot"]["notify"] is False for f in await frames_so_far(subscription))


async def test_another_users_bot_is_404_everywhere(rig):
    cfg, app, alice, user_id = rig
    bob = await _login(app, cfg, "bob")
    bot = await make_bot(cfg, user_id, "Helper")
    for path in (f"/api/bots/{bot.id}/links", f"/api/bots/{bot.id}/made"):
        assert (await bob.get(path)).status_code == 404
    assert (await bob.put(f"/api/bots/{bot.id}/notify", json={"notify": False}, headers=O)).status_code == 404
    assert (await alice.put(f"/api/bots/{bot.id}/notify", json={"notify": False})).status_code == 403
    await bob.aclose()
