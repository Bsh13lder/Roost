"""Repeating expenses (Task 12): the pure rules, the lazy catch-up and the stores under the migration's AADs."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from roost.config import load_config
from roost.constants import RECURRING_CATCH_UP_MAX
from roost.db.connection import get_db_path, init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.money.expense_store import ExpenseStore
from roost.money.models import ExpensePatch
from roost.money.project_store import ProjectStore
from roost.money.recurring import next_occurrence
from roost.money.recurring_service import RecurringService
from roost.money.recurring_store import RecurringStore

TODAY = date(2026, 10, 20)


def test_monthly_on_the_31st_lands_on_the_last_day():
    anchor = date(2026, 1, 31)
    days = [anchor]
    for _ in range(4):
        days.append(next_occurrence("monthly", anchor, days[-1]))
    assert days == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30), date(2026, 5, 31)]
    assert next_occurrence("monthly", date(2026, 1, 15), date(2026, 12, 20)) == date(2027, 1, 15)
    assert next_occurrence("monthly", date(2026, 3, 10), date(2026, 1, 1)) == date(2026, 3, 10)    # never before the anchor


def test_weekly_and_yearly_next_occurrence():
    assert next_occurrence("weekly", date(2026, 10, 5), date(2026, 10, 5)) == date(2026, 10, 12)
    assert next_occurrence("weekly", date(2026, 10, 5), date(2026, 10, 14)) == date(2026, 10, 19)
    assert next_occurrence("yearly", date(2024, 2, 29), date(2024, 2, 29)) == date(2025, 2, 28)       # common year
    assert next_occurrence("yearly", date(2024, 2, 29), date(2027, 3, 1)) == date(2028, 2, 29)
    assert next_occurrence("yearly", date(2026, 10, 20), date(2026, 10, 20)) == date(2027, 10, 20)
    with pytest.raises(ValueError):
        next_occurrence("daily", date(2026, 1, 1), date(2026, 1, 1))


@pytest.fixture
async def rig():
    cfg = load_config()
    await init_db(cfg)
    user_id = (await register_user(cfg, "alice", "pw-123456")).id
    other_id = (await register_user(cfg, "bob", "pw-123456")).id
    projects, expenses = ProjectStore(cfg), ExpenseStore(cfg)
    service = RecurringService(RecurringStore(cfg, expenses), projects, EventHub(cfg))
    food = await projects.find_or_create(user_id, "Food", created_by_bot=None, tainted=False)
    return type("Rig", (), dict(cfg=cfg, user_id=user_id, other_id=other_id, projects=projects, expenses=expenses,
                                service=service, food=food))


async def _rule(rig, cadence="monthly", anchor=date(2026, 7, 15), **kw):
    return await rig.service.create(
        rig.user_id, rig.food, amount=Decimal("9.99"), currency=None, note=kw.pop("note", "Netflix"), vendor=None,
        cadence=cadence, anchor_day=anchor, ends_on=kw.pop("ends_on", None), **kw)


async def _charges(rig) -> list:
    found = []
    for month in ("2026-07", "2026-08", "2026-09", "2026-10", "2026-11"):
        found += list(await rig.expenses.list_month(rig.user_id, month))
    return sorted(found, key=lambda e: e.spent_at)


def _sql(query: str, *params):
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        rows = con.execute(query, params).fetchall()
        con.commit()
        return rows
    finally:
        con.close()


async def test_catch_up_makes_each_missed_charge_once(rig):
    rule = await _rule(rig)
    assert await rig.service.catch_up(rig.user_id, TODAY) == (rule.id,)
    made = await _charges(rig)
    assert [e.spent_at for e in made] == ["2026-07-15", "2026-08-15", "2026-09-15", "2026-10-15"]
    assert {(e.amount, e.currency, e.description, e.recurring_id) for e in made} == {
        (Decimal("9.99"), "EUR", "Netflix", rule.id)}
    assert [e.occurrence for e in made] == [e.spent_at for e in made]
    assert await rig.service.catch_up(rig.user_id, TODAY) == ()           # nothing left to make
    assert len(await _charges(rig)) == 4
    assert (await rig.service.get(rig.user_id, rule.id)).next_due == "2026-11-15"


async def test_catch_up_is_idempotent_under_two_reads(rig):
    await _rule(rig)
    twin = RecurringService(RecurringStore(rig.cfg, rig.expenses), rig.projects, EventHub(rig.cfg))
    await asyncio.gather(*(s.catch_up(rig.user_id, TODAY) for s in (rig.service, twin, rig.service, twin)))
    assert len(await _charges(rig)) == 4


async def test_a_second_process_with_a_stale_rule_cannot_duplicate(rig):
    """Even when a reader still holds the old ``next_due`` the unique index keeps one row per occurrence."""
    rule = await _rule(rig)
    await rig.service.catch_up(rig.user_id, TODAY)
    _sql("UPDATE money_recurring SET next_due = '2026-07-15' WHERE id = ?", rule.id)       # as if it never moved
    await rig.service.catch_up(rig.user_id, TODAY)
    assert len(await _charges(rig)) == 4


async def test_catch_up_is_capped(rig):
    await _rule(rig, cadence="weekly", anchor=date(2021, 10, 20))        # about 260 weeks behind
    await rig.service.catch_up(rig.user_id, TODAY)
    first = len(await rig.expenses.list_project(rig.user_id, rig.food.id))
    assert first == RECURRING_CATCH_UP_MAX
    await rig.service.catch_up(rig.user_id, TODAY)
    assert len(await rig.expenses.list_project(rig.user_id, rig.food.id)) == 2 * RECURRING_CATCH_UP_MAX


async def test_a_voided_or_deleted_charge_is_not_remade(rig):
    rule = await _rule(rig)
    await rig.service.catch_up(rig.user_id, TODAY)
    july, august, *_ = await _charges(rig)
    await rig.expenses.update(rig.user_id, july.id, ExpensePatch({"status": "void"}))
    await rig.expenses.delete(rig.user_id, august.id)
    _sql("UPDATE money_recurring SET next_due = '2026-07-15' WHERE id = ?", rule.id)
    await rig.service.catch_up(rig.user_id, TODAY)
    rows = _sql("SELECT occurrence, status, deleted_at IS NOT NULL FROM money_expenses WHERE recurring_id = ? "
                "ORDER BY occurrence", rule.id)
    assert [(r[0], r[1], r[2]) for r in rows] == [("2026-07-15", "void", 0), ("2026-08-15", "posted", 1),
                                                    ("2026-09-15", "posted", 0), ("2026-10-15", "posted", 0)]


async def test_ends_on_stops_the_rule(rig):
    rule = await _rule(rig, ends_on=date(2026, 8, 31))
    await rig.service.catch_up(rig.user_id, TODAY)
    assert [e.spent_at for e in await _charges(rig)] == ["2026-07-15", "2026-08-15"]
    assert await rig.service.catch_up(rig.user_id, TODAY) == ()
    assert await rig.service.upcoming(rig.user_id, today=TODAY) == ()
    with pytest.raises(ValueError):
        await _rule(rig, anchor=date(2026, 9, 1), ends_on=date(2026, 8, 1))
    assert rule.ends_on == "2026-08-31"


async def test_upcoming_charges_lists_the_next_31_days(rig):
    await _rule(rig, anchor=date(2026, 7, 15))
    await _rule(rig, cadence="weekly", anchor=date(2026, 10, 1), note="Gym")
    await _rule(rig, cadence="yearly", anchor=date(2026, 12, 25), note="Gift")      # outside 31 days
    coming = await rig.service.upcoming(rig.user_id, today=TODAY)
    assert [(c.day, c.note, c.amount) for c in coming] == [
        ("2026-10-22", "Gym", Decimal("9.99")), ("2026-10-29", "Gym", Decimal("9.99")),
        ("2026-11-05", "Gym", Decimal("9.99")), ("2026-11-12", "Gym", Decimal("9.99")),
        ("2026-11-15", "Netflix", Decimal("9.99")), ("2026-11-19", "Gym", Decimal("9.99"))]
    assert await rig.service.upcoming(rig.user_id, "no-such-project", today=TODAY) == ()


async def test_rule_amount_and_note_are_sealed(rig):
    await _rule(rig, note="very private note")
    amount, desc, vendor, cadence, anchor = _sql(
        "SELECT amount, description, vendor, cadence, anchor_day FROM money_recurring")[0]
    for sealed in (amount, desc, cadence):
        assert sealed.startswith("enc:v2:")
    assert "private" not in desc and "9.99" not in amount and vendor is None and anchor == "2026-07-15"


async def test_a_row_the_migration_wrote_reads_back_and_repeats(rig):
    """The LazyClaw migration seals amount, description, vendor and cadence under ``money_recurring:<column>``."""
    from roost.crypto.key_manager import get_user_dek
    from roost.migrate.lazyclaw.models import ImportedRecurring
    from roost.migrate.lazyclaw.writer_rows import Sealer, insert_recurring

    dek = await get_user_dek(rig.cfg, rig.user_id)
    imported = ImportedRecurring(
        id="imp-1", project_id=rig.food.id, amount=Decimal("45.00"), currency="EUR", description="Gym",
        vendor="Fit SL", cadence="monthly", anchor_day="2026-08-31", next_due="2026-09-30",
        created_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:00+00:00", deleted_at=None)
    con = sqlite3.connect(get_db_path(rig.cfg))
    insert_recurring(con, Sealer(dek, rig.user_id), imported)
    con.commit()
    con.close()
    rule = (await rig.service.list(rig.user_id))[0]
    assert (rule.amount, rule.description, rule.vendor, rule.cadence, rule.next_due) == (
        Decimal("45.00"), "Gym", "Fit SL", "monthly", "2026-09-30")
    await rig.service.catch_up(rig.user_id, TODAY)
    assert [e.spent_at for e in await rig.expenses.list_project(rig.user_id, rig.food.id)] == ["2026-09-30"]
    assert (await rig.service.get(rig.user_id, "imp-1")).next_due == "2026-10-31"
    assert [(c.day, c.vendor if hasattr(c, "vendor") else None) for c in await rig.service.upcoming(
        rig.user_id, today=TODAY)] == [("2026-10-31", None)]
