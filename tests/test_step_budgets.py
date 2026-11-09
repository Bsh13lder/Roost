"""A step's budget (owner request 2026-10-26): kept in the sealed steps JSON with its currency, read
leniently, set and cleared one step at a time, and reckoned per step only in the task's currency."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from roost.money.models import Expense
from roost.projects.numbers import step_lines
from roost.tasks.models import Step, Task
from roost.tasks.steps import StepNotFound, steps_from_json, steps_to_json, with_step_budget


def _task(*steps: Step) -> Task:
    return Task(id="t1", user_id="u1", title="Fix", description=None, category=None, priority="medium",
                status="todo", owner="user", due_date=None, reminder_at=None, pre_reminders=(), recurring=None,
                recur_until=None, tags=(), steps=steps, created_at="2026-10-26T08:00:00+00:00",
                updated_at="2026-10-26T08:00:00+00:00", completed_at=None, created_by_bot=None, tainted=False)


def _expense(amount: str, step_id: str | None, currency: str = "EUR") -> Expense:
    return Expense(id=f"e-{amount}-{step_id}", user_id="u1", project_id="p1", amount=Decimal(amount),
                   currency=currency, description=None, vendor=None, spent_at="2026-10-26", status="posted",
                   created_at="2026-10-26T08:00:00+00:00", updated_at="2026-10-26T08:00:00+00:00",
                   created_by_bot=None, tainted=False, task_id="t1", step_id=step_id)


def test_a_step_budget_round_trips_through_the_stored_json():
    steps = (Step(id="s1", title="Buy", done=False, budget=Decimal("20.00"), budget_currency="EUR"),
             Step(id="s2", title="Call", done=True))
    stored = json.loads(steps_to_json(steps))
    assert stored[0]["budget"] == "20.00" and stored[0]["budget_currency"] == "EUR"
    assert "budget" not in stored[1]
    back = steps_from_json(steps_to_json(steps))
    assert (back[0].budget, back[0].budget_currency, back[1].budget) == (Decimal("20.00"), "EUR", None)


@pytest.mark.parametrize("raw", (
    {"budget": "lots", "budget_currency": "EUR"}, {"budget": "-4", "budget_currency": "EUR"},
    {"budget": "5"}, {"budget": "5", "budget_currency": "euro"}, {"budget": 5, "budget_currency": "EUR"},
))
def test_a_damaged_step_budget_reads_as_none(raw):
    step = steps_from_json(json.dumps([{"id": "s1", "title": "Buy", "done": False, **raw}]))[0]
    assert (step.title, step.budget, step.budget_currency) == ("Buy", None, None)


def test_with_step_budget_sets_and_clears_one_step_only():
    steps = (Step(id="s1", title="Buy", done=False), Step(id="s2", title="Call", done=False))
    priced = with_step_budget(steps, "s2", Decimal("12.5"), "EUR")
    assert (priced[0].budget, priced[1].budget, priced[1].budget_currency) == (None, Decimal("12.50"), "EUR")
    assert with_step_budget(priced, "s2", None, "EUR")[1].budget is None
    with pytest.raises(StepNotFound):
        with_step_budget(steps, "nope", Decimal("1"), "EUR")
    with pytest.raises(ValueError, match="more than 0"):
        with_step_budget(steps, "s1", Decimal("0"), "EUR")


def test_step_lines_count_only_the_tasks_currency():
    task = _task(Step(id="s1", title="Buy", done=False, budget=Decimal("20"), budget_currency="EUR"),
                 Step(id="s2", title="Fly", done=False, budget=Decimal("50"), budget_currency="USD"),
                 Step(id="s3", title="Call", done=False))
    lines = step_lines(task, (_expense("25", "s1"), _expense("3", "s2"), _expense("9", "s1", "USD")), "EUR")
    assert (lines["s1"].budget, lines["s1"].spent, lines["s1"].remaining, lines["s1"].tone) == (
        Decimal("20"), Decimal("25"), Decimal("-5"), "over")
    assert (lines["s2"].budget, lines["s2"].spent) == (None, Decimal("3"))
    assert (lines["s3"].budget, lines["s3"].used_percent) == (None, None)
    assert list(lines) == ["s1", "s2", "s3"]
