"""The projects hub's numbers (design §2, H6–H8, H11): pure, with fixed amounts."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from roost.constants import BUDGET_OVER_PERCENT, BUDGET_WARN_PERCENT, DEFAULT_PROJECT_COLOR
from roost.money.models import Expense, Project
from roost.money.months import current_month, parse_spent_at
from roost.projects.numbers import (
    BudgetLine, Progress, TaskMoney, budget_line, counted, progress, project_numbers, task_money,
)
from roost.tasks.models import Step, Task

_AT = "2026-10-01T09:00:00+00:00"
_STEP = Step(id="s1-a1b2c3", title="Buy paint", done=False)


def _dec(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def _project(*, currency: str = "EUR", budget: str | None = None, monthly: str | None = None,
             status: str = "active") -> Project:
    return Project(
        id="p-reno", user_id="u1", name="Renovation", budget=_dec(budget), currency=currency, created_at=_AT,
        updated_at=_AT, created_by_bot=None, tainted=False, color=DEFAULT_PROJECT_COLOR, start_date=None,
        due_date=None, monthly_budget=_dec(monthly), lead_bot_id=None, status=status,
    )


def _expense(amount: str, *, currency: str = "EUR", day: str = "2026-10-10", status: str = "posted",
             starred: bool = False, task_id: str | None = None, step_id: str | None = None,
             project_id: str = "p-reno") -> Expense:
    return Expense(
        id=str(uuid4()), user_id="u1", project_id=project_id, amount=Decimal(amount), currency=currency,
        description=None, vendor=None, spent_at=day, status=status, created_at=_AT, updated_at=_AT,
        created_by_bot=None, tainted=False, task_id=task_id, step_id=step_id, is_favorite=starred,
    )


def _task(status: str = "todo", *, budget: str | None = None, steps: tuple[Step, ...] = (),
          task_id: str = "t-paint") -> Task:
    return Task(
        id=task_id, user_id="u1", title="Paint the hall", description=None, category=None, priority="medium",
        status=status, owner="user", due_date=None, reminder_at=None, pre_reminders=(), recurring=None,
        recur_until=None, tags=(), steps=steps, created_at=_AT, updated_at=_AT, completed_at=None,
        created_by_bot=None, tainted=False, project_id="p-reno", allocated_budget=_dec(budget),
    )


def test_counted_means_posted_and_in_the_projects_currency():
    assert counted(_expense("5"), "EUR") is True
    assert counted(_expense("5", status="void"), "EUR") is False
    assert counted(_expense("5", currency="USD"), "EUR") is False
    assert counted(_expense("5", currency="USD"), "USD") is True


def test_mixed_currencies_stay_apart_and_voids_and_other_projects_are_left_out():
    expenses = (
        _expense("100.00"), _expense("50.50"), _expense("20.00", currency="USD"), _expense("30.00", currency="USD"),
        _expense("7.00", currency="GBP"), _expense("999.00", status="void"),
        _expense("5.00", currency="USD", status="void"), _expense("1000.00", project_id="p-other"),
    )
    numbers = project_numbers(_project(budget="500.00"), expenses, "2026-10")
    assert numbers.currency == "EUR"
    assert numbers.total == BudgetLine(Decimal("500.00"), Decimal("150.50"), Decimal("349.50"), 30, "ok")
    assert dict(numbers.other_currencies) == {"GBP": Decimal("7.00"), "USD": Decimal("50.00")}
    assert list(numbers.other_currencies) == ["GBP", "USD"]
    with pytest.raises(TypeError):
        numbers.other_currencies["EUR"] = Decimal("1")   # read-only, like every record here


def test_a_dollar_project_counts_dollars_and_lists_euros_apart():
    numbers = project_numbers(_project(currency="USD", budget="200.00"),
                              (_expense("80.00", currency="USD"), _expense("12.00")), "2026-10")
    assert (numbers.currency, numbers.total.spent, numbers.total.remaining) == (
        "USD", Decimal("80.00"), Decimal("120.00"))
    assert dict(numbers.other_currencies) == {"EUR": Decimal("12.00")}


def test_the_starred_total_counts_only_posted_starred_expenses_in_the_currency():
    expenses = (
        _expense("12.00", starred=True), _expense("8.50", starred=True), _expense("3.00", currency="USD", starred=True),
        _expense("40.00", status="void", starred=True), _expense("100.00"),
    )
    assert project_numbers(_project(), expenses, "2026-10").starred_total == Decimal("20.50")


def test_over_budget_shows_a_negative_remaining_and_the_over_tone():
    assert budget_line(Decimal("100.00"), Decimal("130.00")) == BudgetLine(
        Decimal("100.00"), Decimal("130.00"), Decimal("-30.00"), 130, "over")
    numbers = project_numbers(_project(budget="100.00"), (_expense("60.00"), _expense("70.00")), "2026-10")
    assert (numbers.total.remaining, numbers.total.tone) == (Decimal("-30.00"), "over")


def test_the_bar_turns_amber_at_80_percent_and_red_once_the_budget_is_spent():
    assert (BUDGET_WARN_PERCENT, BUDGET_OVER_PERCENT) == (80, 100)
    spent = ("0.00", "79.99", "80.00", "99.99", "100.00")
    assert [budget_line(Decimal("100.00"), Decimal(s)).tone for s in spent] == ["ok", "ok", "warn", "warn", "over"]
    assert budget_line(Decimal("100.00"), Decimal("100.00")).remaining == Decimal("0.00")


def test_used_percent_rounds_down_so_it_reads_100_only_once_the_budget_is_spent():
    assert budget_line(Decimal("300.00"), Decimal("199.99")).used_percent == 66     # 66.66…
    assert budget_line(Decimal("3.00"), Decimal("2.00")).used_percent == 66         # 66.66…, never 67
    almost = budget_line(Decimal("300.00"), Decimal("299.99"))                      # 99.99…
    assert (almost.used_percent, almost.tone, almost.remaining) == (99, "warn", Decimal("0.01"))
    assert budget_line(Decimal("100.00"), Decimal("250.00")).used_percent == 250    # it may pass 100


def test_a_budget_of_zero_is_used_up_by_any_spending():
    assert budget_line(Decimal("0.00"), Decimal("0.00")) == BudgetLine(
        Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), 0, "ok")
    assert budget_line(Decimal("0.00"), Decimal("5.00")) == BudgetLine(
        Decimal("0.00"), Decimal("5.00"), Decimal("-5.00"), 100, "over")


def test_no_budget_gives_no_remaining_percent_or_tone():
    assert budget_line(None, Decimal("12.00")) == BudgetLine(None, Decimal("12.00"), None, None, None)
    numbers = project_numbers(_project(), (_expense("12.00"),), "2026-10")
    assert (numbers.total.tone, numbers.month.tone, numbers.month.spent) == (None, None, Decimal("12.00"))


def test_the_month_line_counts_that_month_against_the_monthly_limit():
    expenses = (
        _expense("50.00", day="2026-10-01"), _expense("60.00", day="2026-10-31"), _expense("70.00", day="2026-09-30"),
        _expense("80.00", day="2026-11-01"), _expense("500.00", day="2026-10-15", status="void"),
    )
    numbers = project_numbers(_project(budget="1000.00", monthly="200.00"), expenses, "2026-10")
    assert numbers.month == BudgetLine(Decimal("200.00"), Decimal("110.00"), Decimal("90.00"), 55, "ok")
    assert numbers.total.spent == Decimal("260.00")
    with pytest.raises(ValueError, match="month"):
        project_numbers(_project(), expenses, "2026-13")


def test_an_expense_on_the_last_madrid_evening_counts_in_that_month():
    """Review Focus 3. Madrid runs ahead of UTC, so a month boundary is crossed
    two ways. At 23:59 on 31 October in Madrid (22:59 UTC) the expense is
    October's. At 00:30 on 1 November in Madrid, UTC still reads 31 October,
    yet the expense is November's. The day always comes from months.py, never
    from UTC."""
    last_evening = datetime(2026, 10, 31, 22, 59, tzinfo=timezone.utc)   # 23:59 CET on 31 Oct
    first_night = datetime(2026, 10, 31, 23, 30, tzinfo=timezone.utc)    # 00:30 CET on 1 Nov
    october = _expense("40.00", day=parse_spent_at(None, last_evening))
    november = _expense("15.00", day=parse_spent_at(None, first_night))
    assert (october.spent_at, november.spent_at) == ("2026-10-31", "2026-11-01")
    assert (current_month(last_evening), current_month(first_night)) == ("2026-10", "2026-11")
    project = _project(monthly="100.00")
    in_october = project_numbers(project, (october, november), current_month(last_evening))
    in_november = project_numbers(project, (october, november), current_month(first_night))
    assert (in_october.month.spent, in_october.month.remaining) == (Decimal("40.00"), Decimal("60.00"))
    assert (in_november.month.spent, in_november.month.remaining) == (Decimal("15.00"), Decimal("85.00"))


def test_a_task_shows_planned_spent_and_left_in_the_projects_currency():
    expenses = (
        _expense("100.00", task_id="t-paint"), _expense("50.00", task_id="t-paint", step_id=_STEP.id),
        _expense("20.00", currency="USD", task_id="t-paint"), _expense("70.00", status="void", task_id="t-paint"),
        _expense("999.00", task_id="t-other"), _expense("5.00"),
    )
    assert task_money(_task(budget="300.00", steps=(_STEP,)), expenses, "EUR") == TaskMoney(
        Decimal("300.00"), Decimal("150.00"), Decimal("150.00"))


def test_an_expense_whose_step_was_removed_still_counts_on_the_task():
    expenses = (_expense("10.00", task_id="t-paint", step_id=_STEP.id),
                _expense("25.00", task_id="t-paint", step_id="s2-gone00"))   # that step is no longer on the task
    assert task_money(_task(budget="40.00", steps=(_STEP,)), expenses, "EUR") == TaskMoney(
        Decimal("40.00"), Decimal("35.00"), Decimal("5.00"))


def test_a_task_without_a_slice_has_no_planned_or_left_and_an_overspent_one_goes_negative():
    spent = (_expense("12.00", task_id="t-paint"),)
    assert task_money(_task(), spent, "EUR") == TaskMoney(None, Decimal("12.00"), None)
    assert task_money(_task(budget="10.00"), spent, "EUR").left == Decimal("-2.00")


def test_progress_leaves_cancelled_out_and_counts_failed_apart():
    statuses = ("done", "done", "failed", "todo", "in_progress", "cancelled", "cancelled")
    tasks = tuple(_task(status, task_id=f"t{n}") for n, status in enumerate(statuses))
    assert progress(tasks) == Progress(done=2, failed=1, total=5, open=2)
    assert progress(()) == Progress(done=0, failed=0, total=0)
