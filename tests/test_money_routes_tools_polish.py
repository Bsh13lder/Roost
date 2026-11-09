"""Money routes and tools, polish round A (item 11): JSON booleans are not amounts, an expense never lands
in a project deleted a moment ago, ``update_expense`` says when nothing changed, and sending a task again
keeps its step."""

from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal

import httpx
import pytest

import roost.gateway.routes.money as money_routes
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.events.hub import EventHub
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.money.expense_store import ExpenseStore
from roost.money.models import ExpenseDraft, ProjectDraft
from roost.money.months import current_month, today_madrid
from roost.money.project_store import ProjectStore
from roost.projects.service import ProjectService
from roost.projects.tools import ProjectTools
from roost.notes.store import NoteStore
from roost.documents.store import DocumentStore
from roost.talk.domain_tools import RecordContext
from roost.tasks.models import TaskDraft
from roost.tasks.store import TaskStore
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle

O = {"Origin": "http://127.0.0.1:18800"}


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


def _tool(call_id: str, name: str, **arguments):
    return [ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


async def _talk(cfg, user_id, script):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": script}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "go")
    await wait_idle(rig.runner)
    return [t.text for t in rig.model.requests[-1].turns if t.role == "tool"]


# -- JSON booleans are not amounts ---------------------------------------------------------------


async def test_a_json_boolean_is_not_an_amount_on_any_route(cfg, user_id):
    app = create_app()
    async with _alice(app) as alice:
        trip = (await alice.post("/api/projects", json={"name": "Trip", "budget": "100"}, headers=O)).json()
        topup = (await alice.post(f"/api/projects/{trip['id']}/topups", json={"amount": "10"}, headers=O)).json()
        task = (await alice.post("/api/tasks", json={"title": "Pay", "project_id": trip["id"]}, headers=O)).json()
        refused = {
            "project budget": await alice.post("/api/projects", json={"name": "A", "budget": True}, headers=O),
            "project monthly": await alice.post("/api/projects", json={"name": "B", "monthly_budget": False}, headers=O),
            "patch monthly": await alice.patch(f"/api/projects/{trip['id']}", json={"monthly_budget": True}, headers=O),
            "topup": await alice.post(f"/api/projects/{trip['id']}/topups", json={"amount": True}, headers=O),
            "topup edit": await alice.patch(f"/api/topups/{topup['id']}", json={"amount": True}, headers=O),
            "task slice": await alice.post("/api/tasks", json={"title": "x", "project_id": trip["id"],
                                                               "allocated_budget": True}, headers=O),
            "task patch slice": await alice.patch(f"/api/tasks/{task['id']}", json={"allocated_budget": True}, headers=O),
            "expense": await alice.post("/api/money/expenses", json={"amount": True}, headers=O),
        }
        listed = (await alice.get("/api/projects")).json()
    assert {name: r.status_code for name, r in refused.items()} == {name: 422 for name in refused}
    assert [p["name"] for p in listed] == ["Trip"]


@pytest.mark.parametrize("amount", ["12,50", "12.5", 12, 12.5])
async def test_text_and_numbers_are_still_amounts(cfg, user_id, amount):
    app = create_app()
    async with _alice(app) as alice:
        added = await alice.post("/api/money/expenses", json={"amount": amount}, headers=O)
        topped = await alice.post("/api/projects", json={"name": "Trip", "budget": amount}, headers=O)
    assert (added.status_code, topped.status_code) == (201, 201)


# -- an expense never lands in a project deleted a moment ago --------------------------------------


async def test_the_store_refuses_an_expense_for_a_project_that_is_gone_or_not_yours(cfg, user_id):
    projects = ProjectStore(cfg)
    gone = await projects.create(user_id, ProjectDraft(name="Gone"), created_by_bot=None, tainted=False)
    await projects.delete(user_id, gone.id)
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    theirs = await projects.create(bob, ProjectDraft(name="Shed"), created_by_bot=None, tainted=False)
    store = ExpenseStore(cfg)
    for project_id in (gone.id, theirs.id, "no-such-project"):
        with pytest.raises(ValueError, match=r"^No such project\.$"):
            await store.add(user_id, ExpenseDraft(project_id, Decimal("5"), spent_at=today_madrid()),
                            created_by_bot=None, tainted=False)
    assert await store.list_month(user_id, current_month()) == ()
    assert await store.list_month(bob, current_month()) == ()


async def test_a_project_deleted_between_the_check_and_the_insert_gets_no_expense(cfg, user_id, monkeypatch):
    app = create_app()
    real = money_routes._project_by_id

    async def _then_deleted(service, uid, project_id):
        found = await real(service, uid, project_id)          # the check passes ...
        await ProjectStore(cfg).delete(uid, project_id)       # ... and the project goes before the insert
        return found

    monkeypatch.setattr(money_routes, "_project_by_id", _then_deleted)
    async with _alice(app) as alice:
        trip = (await alice.post("/api/projects", json={"name": "Trip"}, headers=O)).json()
        r = await alice.post("/api/money/expenses", json={"amount": "5", "project_id": trip["id"]}, headers=O)
    assert (r.status_code, r.json()["detail"]) == (422, "No such project.")
    assert await ExpenseStore(cfg).list_month(user_id, current_month()) == ()


async def test_moving_an_expense_into_a_project_that_is_gone_is_refused_in_the_same_write(cfg, user_id):
    projects = ProjectStore(cfg)
    food = await projects.create(user_id, ProjectDraft(name="Food"), created_by_bot=None, tainted=False)
    gone = await projects.create(user_id, ProjectDraft(name="Gone"), created_by_bot=None, tainted=False)
    store = ExpenseStore(cfg)
    expense = await store.add(user_id, ExpenseDraft(food.id, Decimal("5"), spent_at=today_madrid()),
                              created_by_bot=None, tainted=False)
    await projects.delete(user_id, gone.id)
    from roost.money.models import ExpensePatch
    with pytest.raises(ValueError, match=r"^No such project\.$"):
        await store.update(user_id, expense.id, ExpensePatch({"project_id": gone.id}))
    assert (await store.get(user_id, expense.id)).project_id == food.id


# -- the Keep route's not-found text ------------------------------------------------------------


async def test_keep_of_an_unknown_expense_says_the_routes_not_found_text(cfg, user_id):
    app = create_app()
    async with _alice(app) as alice:
        r = await alice.post("/api/money/expenses/no-such/keep", headers=O)
    assert (r.status_code, r.json()["detail"]) == (404, money_routes.EXPENSE_NOT_FOUND_TEXT)


# -- update_expense -----------------------------------------------------------------------------


async def test_update_expense_with_nothing_to_change_says_so(cfg, user_id):
    food = await ProjectStore(cfg).create(user_id, ProjectDraft(name="Food"), created_by_bot=None, tainted=False)
    expense = await ExpenseStore(cfg).add(user_id, ExpenseDraft(food.id, Decimal("5"), spent_at=today_madrid()),
                                          created_by_bot=None, tainted=False)
    texts = await _talk(cfg, user_id, [
        _tool("u1", "update_expense", expense=expense.id, project=""),
        _tool("u2", "update_expense", expense=expense.id),
        _tool("u3", "update_expense", expense=expense.id, project="", starred=True),
        say("ok"),
    ])
    nothing, bare, starred = texts
    assert nothing == bare == "Refused: nothing to change."
    assert starred == f"Updated: 5.00 EUR on {today_madrid()} [starred]."
    stored = await ExpenseStore(cfg).get(user_id, expense.id)
    assert stored.is_favorite is True


async def test_sending_the_same_task_again_keeps_the_step(cfg, user_id):
    food = await ProjectStore(cfg).create(user_id, ProjectDraft(name="Food"), created_by_bot=None, tainted=False)
    paint = await TaskStore(cfg).create(user_id, TaskDraft(title="Paint the hall", steps=("Buy paint", "Paint")),
                                        created_by_bot=None, tainted=False)
    hotel = await TaskStore(cfg).create(user_id, TaskDraft(title="Book the hotel"), created_by_bot=None, tainted=False)
    [buy_paint] = [step for step in paint.steps if step.title == "Buy paint"]
    store = ExpenseStore(cfg)
    expense = await store.add(user_id, ExpenseDraft(food.id, Decimal("30"), spent_at=today_madrid(),
                                                    task_id=paint.id, step_id=buy_paint.id),
                              created_by_bot=None, tainted=False)

    texts = await _talk(cfg, user_id, [
        _tool("same", "update_expense", expense=expense.id, task="Paint the hall"),
        _tool("same-id", "update_expense", expense=expense.id, task=paint.id, note="white"),
        say("ok"),
    ])
    assert all(text.startswith("Updated") for text in texts)
    kept = await store.get(user_id, expense.id)
    assert (kept.task_id, kept.step_id, kept.description) == (paint.id, buy_paint.id, "white")

    await _talk_again(cfg, user_id, [_tool("other", "update_expense", expense=expense.id, task="Book the hotel"),
                                     say("ok")])
    moved = await store.get(user_id, expense.id)
    assert (moved.task_id, moved.step_id) == (hotel.id, None)               # another task: its step is not ours


async def _talk_again(cfg, user_id, script):
    bot = (await BotStore(cfg).list(user_id))[0]
    rig = make_rig(cfg, team_model({bot.name: script}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "again")
    await wait_idle(rig.runner)


async def test_an_empty_step_unlinks_the_step_and_keeps_the_task(cfg, user_id):
    food = await ProjectStore(cfg).create(user_id, ProjectDraft(name="Food"), created_by_bot=None, tainted=False)
    paint = await TaskStore(cfg).create(user_id, TaskDraft(title="Paint the hall", steps=("Buy paint",)),
                                        created_by_bot=None, tainted=False)
    store = ExpenseStore(cfg)
    expense = await store.add(user_id, ExpenseDraft(food.id, Decimal("30"), spent_at=today_madrid(),
                                                    task_id=paint.id, step_id=paint.steps[0].id),
                              created_by_bot=None, tainted=False)
    await _talk(cfg, user_id, [_tool("u", "update_expense", expense=expense.id, task="Paint the hall", step=""),
                               say("ok")])
    kept = await store.get(user_id, expense.id)
    assert (kept.task_id, kept.step_id) == (paint.id, None)


# -- list_projects reads each project's expenses once ----------------------------------------------


class _CountingExpenses(ExpenseStore):
    def __init__(self, config) -> None:
        super().__init__(config)
        self.project_reads: list[str] = []

    async def list_project(self, user_id, project_id):
        self.project_reads.append(project_id)
        return await super().list_project(user_id, project_id)


async def test_list_projects_reads_the_expenses_of_each_project_once_and_still_sees_web_money(cfg, user_id):
    projects, expenses = ProjectStore(cfg), _CountingExpenses(cfg)
    house = await projects.create(user_id, ProjectDraft(name="House"), created_by_bot=None, tainted=False)
    trip = await projects.create(user_id, ProjectDraft(name="Trip"), created_by_bot=None, tainted=False)
    service = ProjectService(projects, expenses, TaskStore(cfg), NoteStore(cfg), DocumentStore(cfg),
                             BotStore(cfg), EventHub(cfg))
    tools = ProjectTools(service, BotStore(cfg))
    ctx = RecordContext(user_id=user_id, bot_id="bot", tainted=False)

    clean = await tools.run("list_projects", {}, ctx)
    assert clean.tainted is False
    assert sorted(expenses.project_reads) == sorted([house.id, trip.id])

    await ExpenseStore(cfg).add(user_id, ExpenseDraft(trip.id, Decimal("9"), spent_at=today_madrid()),
                                created_by_bot=None, tainted=True)
    expenses.project_reads.clear()
    dirty = await tools.run("list_projects", {}, ctx)
    assert dirty.tainted is True
    assert sorted(expenses.project_reads) == sorted([house.id, trip.id])
