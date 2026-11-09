"""The month summary by project (M1 D7, hub H7/H8): each row in its own currency,
against its monthly limit; voids are shown in lists but never summed."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from roost.constants import DEFAULT_PROJECT_COLOR
from roost.money.format import expense_line, summary_text
from roost.money.models import Expense, Project
from roost.money.summary import expense_out, summarize, summary_out
from roost.projects.numbers import BudgetLine

_AT = "2026-10-01T09:00:00+00:00"


def _dec(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def _project(name: str, *, currency: str = "EUR", budget: str | None = None, monthly: str | None = None,
             status: str = "active") -> Project:
    return Project(
        id=str(uuid4()), user_id="u1", name=name, budget=_dec(budget), currency=currency, created_at=_AT,
        updated_at=_AT, created_by_bot=None, tainted=False, color=DEFAULT_PROJECT_COLOR, start_date=None,
        due_date=None, monthly_budget=_dec(monthly), lead_bot_id=None, status=status,
    )


def _expense(project: Project, amount: str, *, currency: str | None = None, status: str = "posted",
             starred: bool = False, task_id: str | None = None, step_id: str | None = None,
             description: str | None = None) -> Expense:
    return Expense(
        id=str(uuid4()), user_id="u1", project_id=project.id, amount=Decimal(amount),
        currency=currency or project.currency, description=description, vendor=None, spent_at="2026-10-10",
        status=status, created_at=_AT, updated_at=_AT, created_by_bot=None, tainted=False, task_id=task_id,
        step_id=step_id, is_favorite=starred,
    )


def test_each_project_row_is_in_its_own_currency_with_its_other_currencies_apart():
    food = _project("Food", monthly="200.00")
    trip = _project("Trip", currency="USD")
    expenses = (
        _expense(food, "50.00"), _expense(food, "10.00", currency="USD"), _expense(trip, "300.00"),
        _expense(trip, "40.00", currency="EUR"), _expense(food, "99.00", status="void"),
    )
    summary = summarize("2026-10", (food, trip), expenses)
    assert (summary.currency, summary.total, summary.expense_count) == ("EUR", Decimal("90.00"), 4)
    assert dict(summary.other_currencies) == {"USD": Decimal("310.00")}
    trip_row, food_row = summary.by_project
    assert (trip_row.project, trip_row.project_id, trip_row.currency, trip_row.spent) == (
        "Trip", trip.id, "USD", Decimal("300.00"))
    assert dict(trip_row.other_currencies) == {"EUR": Decimal("40.00")}
    assert trip_row.month == BudgetLine(None, Decimal("300.00"), None, None, None)
    assert (food_row.project, food_row.currency, dict(food_row.other_currencies)) == (
        "Food", "EUR", {"USD": Decimal("10.00")})
    assert food_row.month == BudgetLine(Decimal("200.00"), Decimal("50.00"), Decimal("150.00"), 25, "ok")


def test_the_month_row_is_measured_against_the_monthly_limit_not_the_total_budget():
    house = _project("House", budget="1000.00")       # a total budget only
    car = _project("Car", monthly="80.00")
    summary = summarize("2026-10", (house, car), (_expense(house, "100.00"), _expense(car, "100.00")))
    car_row, house_row = summary.by_project            # equal spending: by name
    assert (house_row.budget, house_row.remaining, house_row.month.tone) == (None, None, None)
    assert (car_row.budget, car_row.remaining, car_row.month.used_percent, car_row.month.tone) == (
        Decimal("80.00"), Decimal("-20.00"), 125, "over")


def test_a_void_expense_is_in_none_of_the_sums():
    food = _project("Food")
    summary = summarize("2026-10", (food,), (_expense(food, "12.00", status="void"),))
    assert (summary.total, summary.expense_count, summary.by_project, dict(summary.other_currencies)) == (
        Decimal("0.00"), 0, (), {})


def test_an_archived_project_shows_only_when_it_spent_that_month():
    old = _project("Old flat", monthly="50.00", status="archived")
    gym = _project("Gym", monthly="30.00")
    quiet = summarize("2026-10", (old, gym), ())
    assert [row.project for row in quiet.by_project] == ["Gym"]
    assert quiet.by_project[0].month == BudgetLine(Decimal("30.00"), Decimal("0.00"), Decimal("30.00"), 0, "ok")
    busy = summarize("2026-10", (old, gym), (_expense(old, "20.00"),))
    assert [row.project for row in busy.by_project] == ["Old flat", "Gym"]


def test_summary_out_sends_each_row_with_its_currency_month_bar_and_other_currencies():
    food = _project("Food", monthly="200.00")
    summary = summarize("2026-10", (food,), (_expense(food, "170.00"), _expense(food, "5.00", currency="GBP")))
    assert summary_out(summary) == {
        "month": "2026-10", "currency": "EUR", "total": "170.00", "expense_count": 2,
        "by_project": [{
            "project": "Food", "project_id": food.id, "currency": "EUR",
            "spent": "170.00", "budget": "200.00", "remaining": "30.00",
            "month": {"budget": "200.00", "spent": "170.00", "remaining": "30.00", "used_percent": 85, "tone": "warn"},
            "other_currencies": {"GBP": "5.00"}, "money_in": {}, "color": food.color, "pinned": False, "total": None,
        }],
        "other_currencies": {"GBP": "5.00"}, "money_in": {},
    }


def test_an_expense_row_carries_its_status_star_task_and_step():
    food = _project("Food")
    expense = _expense(food, "9.99", status="void", starred=True, task_id="t-1", step_id="s1-a1b2c3")
    out = expense_out(expense, "Food")
    assert {key: out[key] for key in ("project", "project_id", "amount", "status", "is_favorite", "task_id",
                                      "step_id", "tainted")} == {
        "project": "Food", "project_id": food.id, "amount": "9.99", "status": "void", "is_favorite": True,
        "task_id": "t-1", "step_id": "s1-a1b2c3", "tainted": False}
    assert expense_out(expense, "Food", project_tainted=True)["tainted"] is True


def test_the_summary_text_gives_each_row_its_currency_and_monthly_limit():
    food = _project("Food", monthly="100.00")
    trip = _project("Trip", currency="USD")
    gym = _project("Gym", monthly="50.00")
    expenses = (_expense(food, "120.00"), _expense(trip, "30.00"), _expense(trip, "4.00", currency="EUR"),
                _expense(gym, "20.00"))
    assert summary_text(summarize("2026-10", (food, trip, gym), expenses)) == "\n".join((
        "2026-10 — Total: 144.00 EUR (4 expenses)",
        "- Food: 120.00 EUR of a 100.00 EUR monthly limit, over by 20.00 EUR",
        "- Trip: 30.00 USD, also 4.00 EUR",
        "- Gym: 20.00 EUR of a 50.00 EUR monthly limit, 30.00 EUR left",
        "Also 30.00 USD (not in the total)",
    ))


def test_an_expense_line_marks_void_and_starred():
    food = _project("Food")
    marked = _expense(food, "9.99", status="void", starred=True, description="paint & tape")
    plain = _expense(food, "1.00")
    assert expense_line(marked, "Food") == (
        f"2026-10-10 · Food · 9.99 EUR · paint &amp; tape [void] [starred] id={marked.id}")
    assert expense_line(plain, "Food") == f"2026-10-10 · Food · 1.00 EUR id={plain.id}"
