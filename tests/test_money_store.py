"""The user's money stores (M1 D2, D7): encrypted, per user, with provenance."""

from __future__ import annotations

from decimal import Decimal

import pytest

from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.money.expense_store import ExpenseStore
from roost.money.models import EXPENSE_PATCHABLE, ExpenseDraft, ExpensePatch
from roost.money.project_store import ProjectStore
from team_helpers import make_bot


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _food(cfg, user_id, **kw):
    return await ProjectStore(cfg).find_or_create(user_id, "Food", created_by_bot=None, tainted=False, **kw)


async def test_amounts_names_and_notes_are_ciphertext_on_disk(cfg, user_id):
    food = await _food(cfg, user_id)
    expense = await ExpenseStore(cfg).add(user_id, ExpenseDraft(food.id, Decimal("12.50"), spent_at="2026-10-13",
                                                                description="lunch"), created_by_bot=None, tainted=False)
    async with db_session(cfg) as db:
        project = await (await db.execute("SELECT name, name_key FROM money_projects WHERE id = ?", (food.id,))).fetchone()
        row = await (await db.execute("SELECT amount, description FROM money_expenses WHERE id = ?", (expense.id,))).fetchone()
    assert project["name"].startswith("enc:v2:") and "Food" not in project["name_key"]
    assert row["amount"].startswith("enc:v2:") and row["description"].startswith("enc:v2:")
    assert (await ExpenseStore(cfg).get(user_id, expense.id)).amount == Decimal("12.50")


async def test_a_project_is_found_again_whatever_its_case_and_spacing(cfg, user_id):
    store = ProjectStore(cfg)
    first = await store.find_or_create(user_id, "Food", created_by_bot=None, tainted=False)
    again = await store.find_or_create(user_id, "  food ", created_by_bot=None, tainted=True)
    assert again.id == first.id and again.tainted is False
    assert [p.name for p in await store.list(user_id)] == ["Food"]


async def test_set_budget_and_top_ups_keep_a_ledger(cfg, user_id):
    store = ProjectStore(cfg)
    food = await _food(cfg, user_id)
    assert (await store.set_budget(user_id, food.id, Decimal("300"), created_by_bot=None, tainted=False)).budget == Decimal("300.00")
    assert (await store.set_budget(user_id, food.id, Decimal("250"), created_by_bot=None, tainted=False)).budget == Decimal("250.00")
    topup = await store.add_topup(user_id, food.id, Decimal("20"), "birthday", created_by_bot=None, tainted=False)
    assert (topup.kind, topup.amount, topup.source) == ("credit", Decimal("20.00"), "birthday")
    assert (await store.get(user_id, food.id)).budget == Decimal("270.00")
    async with db_session(cfg) as db:
        rows = await (await db.execute("SELECT kind FROM money_topups WHERE project_id = ? ORDER BY created_at", (food.id,))).fetchall()
    assert [r["kind"] for r in rows] == ["edit", "edit", "credit"]


async def test_an_expense_keeps_its_project_and_a_patch_moves_it(cfg, user_id):
    """H1: ``Expense.project_id`` is the ``money_projects`` row; it is stored,
    read back and patched under that one name."""
    food = await _food(cfg, user_id)
    travel = await ProjectStore(cfg).find_or_create(user_id, "Travel", created_by_bot=None, tainted=False)
    store = ExpenseStore(cfg)
    expense = await store.add(user_id, ExpenseDraft(project_id=food.id, amount=Decimal("4"), spent_at="2026-10-13"),
                              created_by_bot=None, tainted=False)
    assert expense.project_id == food.id and (await store.get(user_id, expense.id)).project_id == food.id
    moved = await store.update(user_id, expense.id, ExpensePatch({"project_id": travel.id}))
    assert moved.project_id == travel.id
    assert (await store.get(user_id, expense.id)).project_id == travel.id
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT project_id FROM money_expenses WHERE id = ?", (expense.id,))).fetchone()
    assert row["project_id"] == travel.id


async def test_another_user_sees_no_money(cfg, user_id):
    food = await _food(cfg, user_id)
    expense = await ExpenseStore(cfg).add(user_id, ExpenseDraft(food.id, Decimal("5"), spent_at="2026-10-13"),
                                          created_by_bot=None, tainted=False)
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    assert await ExpenseStore(cfg).get(bob, expense.id) is None
    assert await ExpenseStore(cfg).list_month(bob, "2026-10") == ()
    assert await ProjectStore(cfg).list(bob) == ()
    assert await ExpenseStore(cfg).update(bob, expense.id, ExpensePatch({"amount": Decimal("1")})) is None
    assert await ExpenseStore(cfg).delete(bob, expense.id) is False


async def test_list_month_is_newest_first_and_skips_deleted_and_other_months(cfg, user_id):
    food = await _food(cfg, user_id)
    store = ExpenseStore(cfg)
    for day in ("2026-10-01", "2026-10-20", "2026-11-01"):
        await store.add(user_id, ExpenseDraft(food.id, Decimal("1"), spent_at=day), created_by_bot=None, tainted=False)
    gone = await store.add(user_id, ExpenseDraft(food.id, Decimal("9"), spent_at="2026-10-05"), created_by_bot=None, tainted=False)
    await store.delete(user_id, gone.id)
    assert [e.spent_at for e in await store.list_month(user_id, "2026-10")] == ["2026-10-20", "2026-10-01"]


async def test_retiring_the_bot_keeps_the_users_expenses(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    food = await ProjectStore(cfg).find_or_create(user_id, "Food", created_by_bot=bot.id, tainted=False)
    expense = await ExpenseStore(cfg).add(user_id, ExpenseDraft(food.id, Decimal("3"), spent_at="2026-10-13"),
                                          created_by_bot=bot.id, tainted=False)
    await BotStore(cfg).delete(user_id, bot.id)
    assert (await ExpenseStore(cfg).get(user_id, expense.id)).created_by_bot is None



def test_an_expense_patch_takes_posted_or_void_and_a_yes_or_no_star():
    assert {"task_id", "step_id", "is_favorite", "status"} <= EXPENSE_PATCHABLE
    with pytest.raises(ValueError, match="posted or void"):
        ExpensePatch({"status": "deleted"})
    with pytest.raises(ValueError, match="yes or no"):
        ExpensePatch({"is_favorite": None})


async def test_a_void_expense_stays_visible_and_can_be_posted_again(cfg, user_id):
    food = await _food(cfg, user_id)
    store = ExpenseStore(cfg)
    expense = await store.add(user_id, ExpenseDraft(food.id, Decimal("12.50"), spent_at="2026-10-13"),
                              created_by_bot=None, tainted=False)
    assert expense.status == "posted"
    assert (await store.update(user_id, expense.id, ExpensePatch({"status": "void"}))).status == "void"
    assert (await store.get(user_id, expense.id)).status == "void"
    assert [e.status for e in await store.list_month(user_id, "2026-10")] == ["void"]
    assert (await store.keep(user_id, expense.id)).status == "void"
    assert (await store.update(user_id, expense.id, ExpensePatch({"status": "posted"}))).status == "posted"
    assert (await store.get(user_id, expense.id)).status == "posted"
    await store.delete(user_id, expense.id)
    assert await store.get(user_id, expense.id) is None
    assert await store.update(user_id, expense.id, ExpensePatch({"status": "void"})) is None


async def test_the_star_and_the_task_and_step_links_are_kept_in_plaintext(cfg, user_id):
    food = await _food(cfg, user_id)
    store = ExpenseStore(cfg)
    draft = ExpenseDraft(food.id, Decimal("30"), spent_at="2026-10-13", task_id="t-1", step_id="s1-a1b2c3",
                         is_favorite=True)
    expense = await store.add(user_id, draft, created_by_bot=None, tainted=False)
    again = await store.get(user_id, expense.id)
    assert (again.task_id, again.step_id, again.is_favorite) == ("t-1", "s1-a1b2c3", True)
    await store.update(user_id, expense.id, ExpensePatch({"is_favorite": False, "step_id": None}))
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT task_id, step_id, is_favorite, status FROM money_expenses WHERE id = ?",
                                      (expense.id,))).fetchone()
    assert tuple(row) == ("t-1", None, 0, "posted")


async def test_list_project_returns_one_projects_expenses_voids_included_newest_first(cfg, user_id):
    food = await _food(cfg, user_id)
    travel = await ProjectStore(cfg).find_or_create(user_id, "Travel", created_by_bot=None, tainted=False)
    store = ExpenseStore(cfg)

    async def add(project_id: str, amount: str, day: str):
        return await store.add(user_id, ExpenseDraft(project_id, Decimal(amount), spent_at=day),
                               created_by_bot=None, tainted=False)

    old = await add(food.id, "1", "2026-09-02")
    new = await add(food.id, "2", "2026-10-02")
    void = await add(food.id, "3", "2026-10-01")
    gone = await add(food.id, "4", "2026-10-03")
    await add(travel.id, "5", "2026-10-04")
    await store.update(user_id, void.id, ExpensePatch({"status": "void"}))
    await store.delete(user_id, gone.id)
    assert [e.id for e in await store.list_project(user_id, food.id)] == [new.id, void.id, old.id]
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    assert await store.list_project(bob, food.id) == ()
