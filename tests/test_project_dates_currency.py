"""Dates and currency codes of projects and expenses (polish round A, item 8).

- A project whose due date is before its start date is refused, on create and on update, whoever asks.
- A currency written in lower case ("usd") is accepted and kept in upper case, on every path."""

from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.money.expense_store import ExpenseStore
from roost.money.models import ExpenseDraft, ExpensePatch, ProjectDraft, ProjectPatch
from roost.money.project_store import ProjectStore
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle

O = {"Origin": "http://127.0.0.1:18800"}
DATES = "The due date can't be before the start date."
DATES_FOR_THE_MODEL = "The due date can&#x27;t be before the start date."


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@asynccontextmanager
async def _alice(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        assert (await client.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"},
                                  headers=O)).status_code == 200
        yield client


def _tool(call_id: str, name: str, /, **arguments):
    return [ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


async def _talk(cfg, user_id, script, text="go"):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": script}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, text)
    await wait_idle(rig.runner)
    return [t.text for t in rig.model.requests[-1].turns if t.role == "tool"]


# -- dates: the draft, the patch and the store ---------------------------------------------------


def test_a_draft_with_the_due_date_before_the_start_date_is_refused():
    with pytest.raises(ValueError, match=r"^The due date can't be before the start date\.$"):
        ProjectDraft(name="Trip", start_date="2026-10-14", due_date="2026-10-13")


@pytest.mark.parametrize(("start", "due"), [
    ("2026-10-14", "2026-10-14"), ("2026-10-14", "2026-10-15"), ("2026-10-14", None), (None, "2026-10-13"), (None, None),
])
def test_equal_dates_or_only_one_date_are_fine(start, due):
    draft = ProjectDraft(name="Trip", start_date=start, due_date=due)
    assert (draft.start_date, draft.due_date) == (start, due)


def test_a_patch_that_sends_both_dates_in_the_wrong_order_is_refused():
    with pytest.raises(ValueError, match=r"^The due date can't be before the start date\.$"):
        ProjectPatch({"start_date": "2026-10-14", "due_date": "2026-10-13"})
    assert ProjectPatch({"start_date": "2026-10-14", "due_date": None}).changes["due_date"] is None


async def test_the_store_refuses_an_update_that_leaves_the_due_date_before_the_start_date(cfg, user_id):
    store = ProjectStore(cfg)
    trip = await store.create(user_id, ProjectDraft(name="Trip", start_date="2026-10-14", due_date="2026-10-20"),
                              created_by_bot=None, tainted=False)
    with pytest.raises(ValueError, match=r"^The due date can't be before the start date\.$"):
        await store.update(user_id, trip.id, ProjectPatch({"due_date": "2026-10-01"}))
    with pytest.raises(ValueError, match=r"^The due date can't be before the start date\.$"):
        await store.update(user_id, trip.id, ProjectPatch({"start_date": "2026-11-01"}))
    unchanged = await store.get(user_id, trip.id)
    assert (unchanged.start_date, unchanged.due_date) == ("2026-10-14", "2026-10-20")
    moved = await store.update(user_id, trip.id, ProjectPatch({"start_date": "2026-10-01", "due_date": "2026-10-02"}))
    assert (moved.start_date, moved.due_date) == ("2026-10-01", "2026-10-02")
    cleared = await store.update(user_id, trip.id, ProjectPatch({"due_date": None}))
    assert cleared.due_date is None


# -- dates: the routes and the tools -------------------------------------------------------------


async def test_the_routes_refuse_a_due_date_before_the_start_date(cfg, user_id):
    app = create_app()
    async with _alice(app) as alice:
        created = await alice.post("/api/projects", json={"name": "Trip", "start_date": "2026-10-14",
                                                          "due_date": "2026-10-13"}, headers=O)
        trip = (await alice.post("/api/projects", json={"name": "Trip", "start_date": "2026-10-14",
                                                        "due_date": "2026-10-20"}, headers=O)).json()
        patched = await alice.patch(f"/api/projects/{trip['id']}", json={"due_date": "2026-10-01"}, headers=O)
        listed = (await alice.get("/api/projects")).json()
    assert (created.status_code, created.json()["detail"]) == (422, DATES)
    assert (patched.status_code, patched.json()["detail"]) == (422, DATES)
    assert [(p["start_date"], p["due_date"]) for p in listed] == [("2026-10-14", "2026-10-20")]


async def test_the_tools_refuse_a_due_date_before_the_start_date(cfg, user_id):
    texts = await _talk(cfg, user_id, [
        _tool("c", "create_project", name="Trip", start_date="2026-10-14", due_date="2026-10-13"),
        _tool("c2", "create_project", name="Garden", start_date="2026-10-14", due_date="2026-10-20"),
        _tool("u", "update_project", project="Garden", due_date="2026-10-01"),
        say("ok"),
    ])
    assert texts[0] == f"Refused: {DATES_FOR_THE_MODEL}"
    assert texts[1].startswith("Created project")
    assert texts[2] == f"Refused: {DATES_FOR_THE_MODEL}"


# -- currency: lower case is accepted and kept in upper case --------------------------------------


def test_the_draft_patch_and_expense_draft_keep_a_currency_in_upper_case():
    assert ProjectDraft(name="Trip", currency=" usd ").currency == "USD"
    assert ProjectPatch({"currency": "gbp"}).changes["currency"] == "GBP"
    assert ExpenseDraft("p1", Decimal("5"), currency="usd").currency == "USD"
    assert ExpensePatch({"currency": "gbp"}).changes["currency"] == "GBP"
    with pytest.raises(ValueError, match="three-letter"):
        ExpenseDraft("p1", Decimal("5"), currency="euro")


async def test_the_store_writes_an_expense_currency_in_upper_case(cfg, user_id):
    trip = await ProjectStore(cfg).create(user_id, ProjectDraft(name="Trip"), created_by_bot=None, tainted=False)
    expense = await ExpenseStore(cfg).add(user_id, ExpenseDraft(trip.id, Decimal("5"), currency="usd",
                                                                spent_at="2026-10-14"), created_by_bot=None, tainted=False)
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT currency FROM money_expenses WHERE id = ?", (expense.id,))).fetchone()
    assert (expense.currency, row["currency"]) == ("USD", "USD")


async def test_the_routes_accept_a_lower_case_currency(cfg, user_id):
    app = create_app()
    async with _alice(app) as alice:
        trip = await alice.post("/api/projects", json={"name": "Trip", "currency": "usd"}, headers=O)
        garden = (await alice.post("/api/projects", json={"name": "Garden"}, headers=O)).json()
        changed = await alice.patch(f"/api/projects/{garden['id']}", json={"currency": "gbp"}, headers=O)
        expense = await alice.post("/api/money/expenses", json={"amount": "5", "project": "Trip", "currency": "eur"},
                                   headers=O)
        bad = await alice.post("/api/projects", json={"name": "Bad", "currency": "euro"}, headers=O)
    assert (trip.status_code, trip.json()["currency"]) == (201, "USD")
    assert (changed.status_code, changed.json()["currency"]) == (200, "GBP")
    assert (expense.status_code, expense.json()["currency"]) == (201, "EUR")
    assert bad.status_code == 422


async def test_the_tools_accept_a_lower_case_currency(cfg, user_id):
    texts = await _talk(cfg, user_id, [
        _tool("c", "create_project", name="Trip", currency="usd"),
        _tool("u", "update_project", project="Trip", currency="gbp"),
        _tool("l", "log_expense", amount="5", project="Trip", currency="eur"),
        say("ok"),
    ])
    assert texts[0].startswith("Created project") and texts[1].startswith("Updated")
    projects = await ProjectStore(cfg).list(user_id)
    assert [(p.name, p.currency) for p in projects if p.name == "Trip"] == [("Trip", "GBP")]
    [logged] = [t for t in texts if t.startswith("Logged")]
    assert "5.00 EUR" in logged
