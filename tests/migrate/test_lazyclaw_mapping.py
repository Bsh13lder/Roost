import copy
import json
from datetime import date
from decimal import Decimal

import pytest

from roost.constants import PROJECT_COLORS
from roost.migrate.lazyclaw.mapping import map_lazyclaw
from roost.migrate.lazyclaw.models import LazyData, RoostContext

CTX = RoostContext(user_id="new-user", import_day=date(2026, 10, 20), imported_at="2026-10-20T10:00:00+00:00",
                   general_project_id="roost-general", main_bot_id="main-bot")
STAMP = "2026-03-04 05:06:07"


def proj(id="p1", name="Kitchen", **kw):
    row = dict(id=id, name=name, name_key=name.casefold(), budget=0.0, currency="EUR", status="active",
               description=None, start_date=None, due_date=None, created_at=STAMP, updated_at=STAMP,
               deleted_at=None, color=None, is_favorite=0, lazybrain_note_id=None)
    return {**row, **kw}


def task(id="t1", **kw):
    row = dict(id=id, title="Buy tiles", description=None, category=None, priority="medium", status="todo",
               owner="user", due_date=None, reminder_at=None, recurring=None, tags=None, steps=None,
               comments=None, pre_reminders=None, allocated_budget=None, recur_until=None, created_at=STAMP,
               updated_at=None, completed_at=None, deleted_at=None, progress_log=None)
    return {**row, **kw}


def expense(id="e1", project_id="p1", **kw):
    row = dict(id=id, project_id=project_id, task_id=None, subtask_id=None, amount=10.0, currency="EUR",
               description="x", vendor=None, notes=None, spent_at="2026-03-01", status="posted",
               recurring_expense_id=None, created_at=STAMP, updated_at=STAMP, deleted_at=None, is_favorite=0)
    return {**row, **kw}


def topup(id="b1", project_id="p1", **kw):
    row = dict(id=id, project_id=project_id, amount=100.0, currency="EUR", source="gift", kind="credit",
               created_at=STAMP, updated_at=None, deleted_at=None)
    return {**row, **kw}


def recurring(id="r1", project_id="p1", **kw):
    row = dict(id=id, project_id=project_id, amount=9.99, currency="EUR", description="Hosting", vendor="Acme",
               cron_expression="0 0 1 * *", last_charged_at=None, status="active", created_at=STAMP,
               updated_at=STAMP)
    return {**row, **kw}


def run(**kw):
    return map_lazyclaw(LazyData(**{k: tuple(v) if k != "settings_timezone" else v for k, v in kw.items()}), CTX)


def kinds(result, blocking=None):
    return {a.kind for a in result.anomalies if blocking is None or a.blocking == blocking}


# --- projects and the budget ledger -------------------------------------------------------

def test_project_basics_and_color():
    out = run(projects=[proj(budget=250.0, color="#FF0000", start_date="2026-01-01", description="d")],
              topups=[topup(amount=250.0)])
    p = out.projects[0]
    assert (p.id, p.target_id, p.name, p.budget, p.currency, p.status) == ("p1", "p1", "Kitchen", Decimal("250.00"), "EUR", "active")
    assert p.color == "#ef4444" and p.color in PROJECT_COLORS
    assert p.created_at == "2026-03-04T05:06:07+00:00" and p.updated_at == p.created_at
    assert not out.blocked and out.anomalies == ()


def test_zero_budget_without_ledger_is_no_budget():
    out = run(projects=[proj(budget=0.0)])
    assert out.projects[0].budget is None and out.topups == ()


def test_opening_budget_gap_row():
    out = run(projects=[proj(budget=150.0)], topups=[topup(amount=100.0)])
    opening = [t for t in out.topups if t.opening]
    assert len(opening) == 1
    assert opening[0].amount == Decimal("50.00") and opening[0].kind == "edit"
    assert opening[0].source == "Opening budget (from LazyClaw)"
    assert opening[0].created_at == "2026-03-04T05:06:07+00:00" and opening[0].project_id == "p1"
    live = sum(t.amount for t in out.topups if t.deleted_at is None)
    assert live == out.projects[0].budget
    assert "budget_gap" in kinds(out, blocking=False)


def test_opening_budget_without_any_topups():
    out = run(projects=[proj(budget=80.0)])
    assert [t.amount for t in out.topups] == [Decimal("80.00")] and out.topups[0].opening


def test_deleted_topup_is_history_and_not_counted():
    out = run(projects=[proj(budget=100.0)],
              topups=[topup(), topup(id="b2", amount=40.0, deleted_at="2026-03-05 00:00:00")])
    assert len(out.topups) == 2 and not any(t.opening for t in out.topups)
    assert [t.deleted_at for t in out.topups if t.id == "b2"] == ["2026-03-05T00:00:00+00:00"]


def test_negative_gap_listed():
    out = run(projects=[proj(budget=0.0)], topups=[topup(amount=30.0)])
    assert out.projects[0].budget == Decimal("0.00")
    assert [t.amount for t in out.topups if t.opening] == [Decimal("-30.00")]
    assert "budget_gap" in kinds(out)


def test_topup_other_currency_blocks():
    out = run(projects=[proj(budget=10.0)], topups=[topup(currency="USD", amount=10.0)])
    assert out.blocked and "topup_currency" in kinds(out, blocking=True)


def test_general_merges_into_roost_general():
    g = proj(id="lc-general", name="General", budget=0.0)
    out = run(projects=[g], expenses=[expense(project_id="lc-general")])
    assert out.projects[0].is_general and out.projects[0].target_id == "roost-general"
    assert out.expenses[0].project_id == "roost-general"


def test_deleted_project_skipped_and_expenses_go_to_general():
    out = run(projects=[proj(id="gone", name="Old", deleted_at="2026-04-01 00:00:00"), proj(id="g", name="General")],
              expenses=[expense(project_id="gone")], topups=[topup(project_id="gone")],
              tasks=[task(category="Old")])
    assert [p.id for p in out.projects] == ["g"]
    assert out.expenses[0].project_id == "roost-general"
    assert out.skipped["projects_deleted"] == 1 and out.skipped["topups_of_deleted_projects"] == 1
    assert out.tasks[0].project_id is None and out.tasks[0].category == "Old"


def test_deleted_project_without_a_general_project_still_routes_to_roost_general():
    out = run(projects=[proj(id="gone", deleted_at="2026-04-01 00:00:00")], expenses=[expense(project_id="gone")])
    assert out.expenses[0].project_id == "roost-general"


@pytest.mark.parametrize("patch", [{"status": "paused"}, {"currency": "eur"}, {"budget": 1.234}])
def test_project_bad_values_block(patch):
    assert run(projects=[proj(**patch)]).blocked


# --- tasks ------------------------------------------------------------------------------

def test_task_category_becomes_project_or_stays_a_list():
    out = run(projects=[proj(name="Kitchen")], tasks=[task(id="a", category=" kitchen "), task(id="b", category="Errands"), task(id="c")])
    by = {t.id: t for t in out.tasks}
    assert (by["a"].project_id, by["a"].category) == ("p1", None)
    assert (by["b"].project_id, by["b"].category) == (None, "Errands")
    assert (by["c"].project_id, by["c"].category) == (None, None)


def test_task_fields_copied_trusted_and_stamped():
    t = task(priority="urgent", status="in_progress", owner="agent", due_date="2026-05-01T09:00:00",
             reminder_at="2026-05-01T08:00:00+00:00", recurring="0 9 * * 1", recur_until="2026-12-31",
             tags='["a","b"]', pre_reminders='["2026-04-30T08:00:00+00:00"]', completed_at="2026-03-05 01:02:03",
             updated_at="2026-03-06 01:02:03")
    m = run(tasks=[t]).tasks[0]
    assert (m.priority, m.status, m.owner) == ("urgent", "in_progress", "agent")
    assert m.tainted == 0 and m.starred == 0 and m.estimate is None and m.created_by_bot is None
    assert m.due_date == "2026-05-01T09:00:00" and m.reminder_at == "2026-05-01T08:00:00+00:00"
    assert m.recurring == "0 9 * * 1" and m.recur_until == "2026-12-31" and m.tags == '["a","b"]'
    assert m.completed_at == "2026-03-05T01:02:03+00:00" and m.updated_at == "2026-03-06T01:02:03+00:00"


@pytest.mark.parametrize("patch", [{"priority": "critical"}, {"status": "blocked"}, {"owner": "bot"},
                                   {"recurring": "not a cron"}, {"due_date": "someday"}, {"steps": "{broken"},
                                   {"allocated_budget": 0.005}, {"title": None}])
def test_task_bad_values_block(patch):
    out = run(projects=[proj()], tasks=[task(**patch)])
    assert out.blocked and out.tasks == ()


def test_deleted_task_not_imported_but_counted():
    out = run(tasks=[task(deleted_at="2026-04-01 00:00:00"), task(id="t2")])
    assert [t.id for t in out.tasks] == ["t2"] and out.skipped["tasks_deleted"] == 1


def test_allocated_budget_needs_a_project():
    out = run(projects=[proj()], tasks=[task(id="a", category="Kitchen", allocated_budget=40.5),
                                        task(id="b", allocated_budget=12.0)])
    by = {t.id: t for t in out.tasks}
    assert by["a"].allocated_budget == Decimal("40.50") and by["b"].allocated_budget is None
    assert [a.ref for a in out.anomalies if a.kind == "allocated_budget_dropped"] == ["b"]


def test_steps_and_comments():
    steps = [{"id": "s1", "title": "Measure", "done": True, "created_at": "2026-03-04T01:00:00+00:00"},
             {"id": "s2", "title": "Order", "done": False}]
    comments = [{"id": "c1", "ts": "2026-03-04T02:00:00+00:00", "author": "user", "text": "hi", "subtask_id": "s1"},
                {"id": "c2", "ts": "2026-03-04T03:00:00+00:00", "author": "agent", "text": "done", "subtask_id": None},
                {"id": "c3", "ts": "2026-03-04T03:00:00+00:00", "author": "user", "text": "ghost", "subtask_id": "zz"},
                {"id": "c4", "text": "   "}]
    out = run(tasks=[task(steps=json.dumps(steps), comments=json.dumps(comments))])
    assert [s["id"] for s in out.tasks[0].steps] == ["s1", "s2"] and out.tasks[0].steps[0]["done"] is True
    by = {c.id: c for c in out.comments}
    assert set(by) == {"c1", "c2", "c3"}
    assert (by["c1"].step_id, by["c1"].author, by["c1"].body) == ("s1", "user", "hi")
    assert (by["c2"].author, by["c2"].tainted) == ("main-bot", 0)
    assert by["c3"].step_id is None
    assert {"comment_step_missing", "comment_skipped"} <= kinds(out, blocking=False)


def test_agent_comment_without_main_bot_falls_back_to_user():
    ctx = RoostContext(user_id="n", import_day=date(2026, 10, 20), imported_at="x")
    cm = json.dumps([{"id": "c", "ts": STAMP, "author": "agent", "text": "t"}])
    out = map_lazyclaw(LazyData(tasks=(task(comments=cm),)), ctx)
    assert out.comments[0].author == "user"


def test_progress_log_counted_as_lost():
    log = json.dumps([{"ts": 1}, {"ts": 2}, {"ts": 3}])
    out = run(tasks=[task(progress_log=log), task(id="t2", progress_log="not json")])
    assert out.lost["progress_log_entries"] == 4


# --- expenses ----------------------------------------------------------------------------

def test_expense_links_and_demotion():
    steps = json.dumps([{"id": "s1", "title": "x", "done": False}])
    out = run(projects=[proj()], tasks=[task(steps=steps)],
              expenses=[expense(id="ok", task_id="t1", subtask_id="s1"),
                        expense(id="demoted", task_id="t1", subtask_id="nope"),
                        expense(id="orphan", task_id="missing", subtask_id="s1")])
    by = {e.id: e for e in out.expenses}
    assert (by["ok"].task_id, by["ok"].step_id) == ("t1", "s1")
    assert (by["demoted"].task_id, by["demoted"].step_id) == ("t1", None)
    assert (by["orphan"].task_id, by["orphan"].step_id) == (None, None)
    assert {"expense_step_demoted", "expense_task_missing"} <= kinds(out, blocking=False)


def test_expense_defaults_and_void():
    out = run(projects=[proj(currency="USD")],
              expenses=[expense(currency=None, spent_at=None, status="void", is_favorite=1, amount=0.1 + 0.2)])
    e = out.expenses[0]
    assert (e.currency, e.spent_at, e.status, e.is_favorite, e.amount) == ("USD", "2026-03-04", "void", 1, Decimal("0.30"))
    assert "expense_no_date" in kinds(out)


@pytest.mark.parametrize("patch", [{"amount": 0.0}, {"amount": -5.0}, {"status": "pending"}, {"amount": 0.004},
                                   {"project_id": "nowhere"}, {"currency": "euro"}])
def test_expense_bad_values_block(patch):
    out = run(projects=[proj()], expenses=[expense(**patch)])
    assert out.blocked and out.expenses == ()


def test_deleted_expense_not_imported():
    out = run(projects=[proj()], expenses=[expense(deleted_at="2026-04-01 00:00:00")])
    assert out.expenses == () and out.skipped["expenses_deleted"] == 1


def test_recurring_occurrence_and_duplicates():
    out = run(projects=[proj()], recurring=[recurring()],
              expenses=[expense(id="e1", recurring_expense_id="r1", spent_at="2026-09-01"),
                        expense(id="e2", recurring_expense_id="r1", spent_at="2026-09-01", created_at="2026-09-02 00:00:00"),
                        expense(id="e3", recurring_expense_id="ghost", spent_at="2026-08-01")])
    by = {e.id: e for e in out.expenses}
    assert (by["e1"].recurring_id, by["e1"].occurrence) == ("r1", "2026-09-01")
    assert (by["e2"].recurring_id, by["e2"].occurrence) == (None, None)
    assert by["e3"].recurring_id is None
    assert {"expense_duplicate_occurrence", "expense_recurring_missing"} <= kinds(out)


# --- recurring rules -------------------------------------------------------------------

def test_recurring_rules():
    out = run(projects=[proj()], recurring=[
        recurring(id="m", last_charged_at="2026-10-01T00:00:05+00:00"),
        recurring(id="w", cron_expression="0 9 * * 1"),
        recurring(id="y", cron_expression="0 0 5 3 *"),
        recurring(id="x", cron_expression="*/5 * * * *"),
        recurring(id="p", status="paused")])
    by = {r.id: r for r in out.recurring}
    assert set(by) == {"m", "w", "y", "p"}
    assert (by["m"].cadence, by["m"].anchor_day, by["m"].next_due) == ("monthly", "2026-11-01", "2026-11-01")
    assert (by["w"].cadence, by["w"].anchor_day, by["w"].next_due) == ("weekly", "2026-10-26", "2026-10-26")
    assert (by["y"].cadence, by["y"].anchor_day, by["y"].next_due) == ("yearly", "2027-03-05", "2027-03-05")
    assert by["m"].deleted_at is None and by["p"].deleted_at == CTX.imported_at
    assert by["m"].amount == Decimal("9.99")
    assert [a.ref for a in out.anomalies if a.kind == "recurring_not_convertible"] == ["x"]
    assert not out.blocked


def test_recurring_of_deleted_project_skipped():
    out = run(projects=[proj(deleted_at="2026-04-01 00:00:00")], recurring=[recurring()])
    assert out.recurring == () and out.skipped["recurring_of_deleted_projects"] == 1


# --- whole-run properties --------------------------------------------------------------------

def test_timezone_anomaly():
    assert "timezone" in kinds(run(settings_timezone="America/New_York"))
    assert "timezone" not in kinds(run(settings_timezone="Europe/Madrid"))
    assert "timezone" not in kinds(run())


def test_mapping_is_pure_and_deterministic():
    rows = dict(projects=[proj(budget=70.0)], tasks=[task(steps=json.dumps([{"id": "s", "title": "t"}]))],
                expenses=[expense()], topups=[topup(amount=50.0)], recurring=[recurring()])
    data = LazyData(**{k: tuple(v) for k, v in rows.items()})
    snapshot = copy.deepcopy(data)
    assert map_lazyclaw(data, CTX) == map_lazyclaw(data, CTX)
    assert data == snapshot


def test_no_general_id_uses_the_lazyclaw_one():
    ctx = RoostContext(user_id="n", import_day=date(2026, 10, 20), imported_at="x")
    out = map_lazyclaw(LazyData(projects=(proj(id="lc-g", name="General"),)), ctx)
    assert out.projects[0].target_id == "lc-g"
