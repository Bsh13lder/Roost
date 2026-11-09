"""``ExpenseStore.update`` writes only the columns the patch changes (polish round A, item 7), like
``TaskStore``, so a change made between its read and its write is never put back to the old value."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.money.expense_store import ExpenseStore
from roost.money.models import ExpenseDraft, ExpensePatch
from roost.money.project_store import ProjectStore


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


class _ReadsTogether(ExpenseStore):
    """Both updates read the expense before either writes: the stale-read race, made certain."""

    def __init__(self, config, barrier: asyncio.Barrier) -> None:
        super().__init__(config)
        self._barrier = barrier

    async def get(self, user_id, expense_id):
        found = await super().get(user_id, expense_id)
        await self._barrier.wait()
        return found


async def _expense(cfg, user_id, **fields):
    food = await ProjectStore(cfg).find_or_create(user_id, "Food", created_by_bot=None, tainted=False)
    draft = ExpenseDraft(food.id, Decimal("12.50"), spent_at="2026-10-13", description="lunch", **fields)
    return await ExpenseStore(cfg).add(user_id, draft, created_by_bot=None, tainted=False)


async def test_two_interleaved_updates_of_different_fields_both_stay(cfg, user_id):
    expense = await _expense(cfg, user_id)
    store = _ReadsTogether(cfg, asyncio.Barrier(2))

    await asyncio.gather(
        store.update(user_id, expense.id, ExpensePatch({"is_favorite": True})),
        store.update(user_id, expense.id, ExpensePatch({"status": "void"})),
    )

    stored = await ExpenseStore(cfg).get(user_id, expense.id)
    assert (stored.is_favorite, stored.status) == (True, "void")


async def test_an_update_of_one_field_leaves_the_others_as_the_database_has_them(cfg, user_id):
    expense = await _expense(cfg, user_id)
    store = ExpenseStore(cfg)
    stale = await store.get(user_id, expense.id)
    await store.update(user_id, expense.id, ExpensePatch({"amount": Decimal("99.00"), "description": "dinner"}))

    await store.update(user_id, expense.id, ExpensePatch({"is_favorite": True}))

    stored = await store.get(user_id, expense.id)
    assert (stored.amount, stored.description, stored.is_favorite) == (Decimal("99.00"), "dinner", True)
    assert stale.amount == Decimal("12.50")      # the read taken before the first update was stale


async def test_the_answer_shows_the_patch_and_a_new_updated_at(cfg, user_id):
    expense = await _expense(cfg, user_id)
    store = ExpenseStore(cfg)
    updated = await store.update(user_id, expense.id, ExpensePatch({"vendor": "Bar Pepe", "spent_at": "2026-10-14"}))
    assert (updated.vendor, updated.spent_at, updated.amount) == ("Bar Pepe", "2026-10-14", Decimal("12.50"))
    stored = await store.get(user_id, expense.id)
    assert (stored.vendor, stored.spent_at) == ("Bar Pepe", "2026-10-14")
    assert stored.updated_at == updated.updated_at and stored.updated_at >= expense.updated_at


async def test_an_expense_deleted_between_the_read_and_the_write_is_not_answered(cfg, user_id):
    expense = await _expense(cfg, user_id)

    class _DeletedMeanwhile(ExpenseStore):
        async def get(self, user_id, expense_id):
            found = await super().get(user_id, expense_id)
            await super().delete(user_id, expense_id)
            return found

    assert await _DeletedMeanwhile(cfg).update(user_id, expense.id, ExpensePatch({"is_favorite": True})) is None
    assert await ExpenseStore(cfg).get(user_id, expense.id) is None
