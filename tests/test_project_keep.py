"""Keep on a project (polish round A, item 9).

Only the project's own Keep (``ProjectStore.keep``, ``ProjectService.keep``) vouches for the project's
"Budget set" history rows. The Keep of an expense vouches for the project *name* its row shows and
nothing in the ledger, and neither Keep touches a top-up row (a credit, or an edit of one)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.money.expense_store import ExpenseStore
from roost.money.models import ProjectDraft
from roost.money.months import today_madrid
from roost.money.project_store import ProjectStore
from roost.money.service import ExpenseEntry, MoneyService
from roost.events.hub import EventHub


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture
def store(cfg) -> ProjectStore:
    return ProjectStore(cfg)


async def _web_project(store, user_id, name="Trip"):
    """A project made in a run that read a web page: the project, its "Budget set" row and a top-up
    (with an edit of it) are all marked as web content."""
    project = await store.create(user_id, ProjectDraft(name=name, budget=Decimal("1000")), created_by_bot=None,
                                 tainted=True)
    credit = await store.add_topup(user_id, project.id, Decimal("200"), "gift", created_by_bot=None, tainted=True)
    await store.edit_topup(user_id, credit.id, Decimal("250"))
    return project


async def _marks(store, user_id, project_id) -> dict[str, list[bool]]:
    """The taint of each kind of history row: the "Budget set" rows, the top-ups, their edits."""
    rows = await store.topups(user_id, project_id)
    return {
        "budget_set": [r.tainted for r in rows if r.kind == "edit" and r.topup_id is None],
        "credit": [r.tainted for r in rows if r.kind == "credit"],
        "credit_edit": [r.tainted for r in rows if r.kind == "edit" and r.topup_id is not None],
    }


async def test_keep_vouches_for_the_budget_set_rows_and_leaves_every_top_up_row_alone(store, user_id):
    trip = await _web_project(store, user_id)
    before = await _marks(store, user_id, trip.id)
    assert before == {"budget_set": [True], "credit": [True], "credit_edit": [False]}   # an edit row carries no taint

    kept = await store.keep(user_id, trip.id)

    assert kept.tainted is False
    assert await _marks(store, user_id, trip.id) == {"budget_set": [False], "credit": [True], "credit_edit": [False]}


async def test_another_users_keep_or_a_keep_on_a_different_project_leaves_a_tainted_top_up_row_tainted(
    cfg, store, user_id,
):
    trip = await _web_project(store, user_id)
    garden = await _web_project(store, user_id, "Garden")
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    await _web_project(store, bob, "Shed")

    assert await store.keep(bob, trip.id) is None                      # not his project
    await store.keep(user_id, garden.id)                              # a different project of the same user
    await store.keep(bob, garden.id)                                  # a different project of a different user

    assert await _marks(store, user_id, trip.id) == {"budget_set": [True], "credit": [True], "credit_edit": [False]}
    assert (await store.get(user_id, trip.id)).tainted is True
    assert await _marks(store, user_id, garden.id) == {"budget_set": [False], "credit": [True], "credit_edit": [False]}


async def test_the_keep_of_an_expense_vouches_for_the_project_name_but_not_for_its_ledger(cfg, store, user_id):
    money = MoneyService(store, ExpenseStore(cfg), EventHub(cfg))
    trip = await _web_project(store, user_id)
    expense, _ = await money.log_expense(
        user_id, ExpenseEntry(amount=Decimal("9"), spent_at=today_madrid(), project=trip.name), tainted=True)

    kept = await money.keep_expense(user_id, expense.id)

    assert kept is not None and kept[0].tainted is False
    assert kept[1].tainted is False                                  # the name its row shows is the user's now
    assert (await store.get(user_id, trip.id)).tainted is False
    assert await _marks(store, user_id, trip.id) == {"budget_set": [True], "credit": [True], "credit_edit": [False]}


async def test_the_project_keep_still_clears_the_ledger_after_the_expense_keep(cfg, store, user_id):
    money = MoneyService(store, ExpenseStore(cfg), EventHub(cfg))
    trip = await _web_project(store, user_id)
    expense, _ = await money.log_expense(
        user_id, ExpenseEntry(amount=Decimal("9"), spent_at=today_madrid(), project=trip.name), tainted=True)
    await money.keep_expense(user_id, expense.id)

    await store.keep(user_id, trip.id)

    assert (await _marks(store, user_id, trip.id))["budget_set"] == [False]
