"""Money in (schema v21): income is stored, shown, exported and totalled apart, and never counted as spent."""

from __future__ import annotations

import csv
import io
from decimal import Decimal

from money_http import O, two_users

from roost.config import load_config
from roost.constants import DEFAULT_PROJECT_COLOR
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.money.expense_store import ExpenseStore
from roost.money.format import expense_line, summary_text
from roost.money.models import Expense, Project
from roost.money.reports import CSV_HEADERS, csv_text, trend
from roost.money.summary import expense_out, summarize, summary_out
from roost.projects.numbers import counted, money_in, project_numbers, task_money
from roost.tasks.models import Task
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle

_AT = "2026-10-01T09:00:00+00:00"
PROJECT = Project(
    id="p", user_id="u", name="Home", budget=Decimal("100.00"), currency="EUR", created_at=_AT, updated_at=_AT,
    created_by_bot=None, tainted=False, color=DEFAULT_PROJECT_COLOR, start_date=None, due_date=None,
    monthly_budget=Decimal("100.00"), lead_bot_id=None, status="active")


def _e(amount: str, *, kind: str = "expense", currency: str = "EUR", status: str = "posted", task_id=None,
       day: str = "2026-10-10", starred: bool = False) -> Expense:
    return Expense(id=f"{kind}-{amount}-{currency}-{status}", user_id="u", project_id="p", amount=Decimal(amount),
                   currency=currency, description="x", vendor=None, spent_at=day, status=status, created_at=_AT,
                   updated_at=_AT, created_by_bot=None, tainted=False, task_id=task_id, kind=kind,
                   is_favorite=starred)


MIXED = (_e("20.00"), _e("500.00", kind="income"), _e("40.00", kind="income", currency="USD"),
         _e("9.00", kind="income", status="void"), _e("7.00", kind="income", starred=True))


def test_income_is_never_counted():
    assert counted(_e("5", kind="income"), "EUR") is False and counted(_e("5"), "EUR") is True


def test_project_numbers_keep_income_out_of_spending_and_total_it_apart():
    numbers = project_numbers(PROJECT, MIXED, "2026-10")
    assert numbers.total.spent == Decimal("20.00") and numbers.total.tone == "ok"
    assert numbers.total.remaining == Decimal("80.00") and numbers.month.spent == Decimal("20.00")
    assert numbers.starred_total == Decimal("0.00") and dict(numbers.other_currencies) == {}
    assert dict(numbers.money_in) == {"EUR": Decimal("507.00"), "USD": Decimal("40.00")}      # void income is out


def test_money_in_helper_is_per_currency_and_posted_only():
    assert dict(money_in(MIXED)) == {"EUR": Decimal("507.00"), "USD": Decimal("40.00")}
    assert dict(money_in(())) == {}


def test_task_money_ignores_income():
    task = Task(id="t", user_id="u", title="t", description=None, category=None, priority="medium", status="todo",
                owner="user", due_date=None, reminder_at=None, pre_reminders=(), recurring=None, recur_until=None,
                tags=(), steps=(), created_at=_AT, updated_at=_AT, completed_at=None, created_by_bot=None,
                tainted=False, project_id="p", allocated_budget=Decimal("50"))
    sums = task_money(task, (_e("10", task_id="t"), _e("300", kind="income", task_id="t")), "EUR")
    assert (sums.spent, sums.left) == (Decimal("10.00"), Decimal("40.00"))


def test_summary_counts_spending_and_lists_money_in_apart():
    summary = summarize("2026-10", (PROJECT,), MIXED)
    assert summary.total == Decimal("20.00") and summary.expense_count == 1
    assert dict(summary.money_in) == {"EUR": Decimal("507.00"), "USD": Decimal("40.00")}
    row = summary.by_project[0]
    assert row.spent == Decimal("20.00") and dict(row.money_in) == {"EUR": Decimal("507.00"), "USD": Decimal("40.00")}
    assert dict(row.other_currencies) == {}
    out = summary_out(summary)
    assert out["money_in"] == {"EUR": "507.00", "USD": "40.00"} and out["by_project"][0]["money_in"] == out["money_in"]
    assert "Money in: 507.00 EUR" in summary_text(summary)


def test_a_project_with_only_income_still_shows_in_the_summary():
    summary = summarize("2026-10", (PROJECT,), (_e("50", kind="income"),))
    assert [r.project for r in summary.by_project] == ["Home"] and summary.total == Decimal("0.00")


def test_trend_leaves_income_out():
    rows = trend(MIXED, ("2026-10",))
    assert dict(rows[0].totals) == {"EUR": Decimal("20.00")}


def test_csv_has_a_kind_column():
    assert CSV_HEADERS[-1] == "Kind" or "Kind" in CSV_HEADERS
    rows = list(csv.DictReader(io.StringIO(csv_text(MIXED[:2], {"p": "Home"}))))
    assert [(r["Kind"], r["Amount"]) for r in rows] == [("expense", "20.00"), ("income", "500.00")]


def test_expense_rows_and_lines_carry_the_kind():
    assert expense_out(_e("5", kind="income"), "Home")["kind"] == "income"
    assert expense_out(_e("5"), "Home")["kind"] == "expense"
    assert "[money in]" in expense_line(_e("5", kind="income"), "Home")
    assert "[money in]" not in expense_line(_e("5"), "Home")


async def test_the_line_posts_and_lists_money_in_over_http():
    async with two_users() as (alice, _bob, _app):
        home = (await alice.post("/api/projects", json={"name": "Home", "budget": "100"}, headers=O)).json()
        line = (await alice.post("/api/money/parse", json={"text": "+€500 salary /Home"}, headers=O)).json()
        assert (line["income"], line["ready"], line["income_problem"], line["amount"]) == (True, True, None, "500.00")
        assert (await alice.post("/api/money/parse", json={"text": "+€5 gift /Home monthly"}, headers=O)
                ).json()["ready"] is False
        posted = await alice.post("/api/money/expenses", headers=O, json={
            "amount": "500", "project": "Home", "note": "salary", "income": True})
        assert posted.status_code == 201 and posted.json()["kind"] == "income"
        spent = await alice.post("/api/money/expenses", json={"amount": "30", "project": "Home"}, headers=O)
        assert spent.json()["kind"] == "expense"
        listed = (await alice.get("/api/money/expenses")).json()
        assert sorted((e["kind"], e["amount"]) for e in listed) == [("expense", "30.00"), ("income", "500.00")]
        summary = (await alice.get("/api/money/summary")).json()
        assert (summary["total"], summary["money_in"]) == ("30.00", {"EUR": "500.00"})
        page = (await alice.get(f"/api/projects/{home['id']}")).json()
        assert page["total"]["spent"] == "30.00" and page["total"]["remaining"] == "70.00"
        assert page["money_in"] == {"EUR": "500.00"}
        export = (await alice.get("/api/money/export.csv")).text
        assert "Kind" in export.splitlines()[0] and "income" in export
        repeat = await alice.post("/api/money/expenses", headers=O, json={
            "amount": "5", "income": True, "cadence": "monthly"})
        assert repeat.status_code == 422


async def test_log_expense_tool_takes_income():
    cfg = load_config()
    await init_db(cfg)
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Life admin")
    call = ToolCallRequested(id="e", name="log_expense", arguments={"amount": "500", "project": "Home",
                                                                     "note": "salary", "income": True})
    rig = make_rig(cfg, team_model({"Life admin": [[call, TurnDone("tool_use")], say("ok")]}))
    thread = await rig.talk.create_thread(user.id, bot.id)
    await send(rig, user.id, bot.id, thread.id, "I got paid 500")
    await wait_idle(rig.runner)
    [stored] = await ExpenseStore(cfg).list_month(user.id, __import__("roost.money.months", fromlist=["x"]).current_month())
    assert (stored.kind, stored.amount) == ("income", Decimal("500.00"))
    told = [t.text for t in rig.model.requests[-1].turns if t.role == "tool"][0]
    assert told.startswith("Logged money in 500.00 EUR")
