"""Money over HTTP (the Board's data, M1 D8) and the money_changed frame."""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import get_db_path
from roost.gateway.app import create_app
from roost.money.months import current_month, today_madrid

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _stored_project_ids() -> dict[str, str]:
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        return dict(con.execute("SELECT id, project_id FROM money_expenses").fetchall())
    finally:
        con.close()


def test_add_an_expense_and_see_it_in_the_month_and_the_summary():
    c = _client()
    c.post("/api/projects", json={"name": "food"}, headers=O)
    r = c.post("/api/money/expenses", json={"amount": "12,50", "project": "food", "note": "lunch"}, headers=O)
    assert r.status_code == 201
    expense = r.json()
    assert (expense["amount"], expense["project"], expense["currency"], expense["spent_at"]) == (
        "12.50", "food", "EUR", today_madrid())
    assert [e["id"] for e in c.get(f"/api/money/expenses?month={current_month()}").json()] == [expense["id"]]
    summary = c.get("/api/money/summary").json()
    assert (summary["month"], summary["total"], summary["expense_count"]) == (current_month(), "12.50", 1)
    assert summary["by_project"] == [{
        "project": "food", "project_id": expense["project_id"], "currency": "EUR",
        "spent": "12.50", "budget": None, "remaining": None,
        "month": {"budget": None, "spent": "12.50", "remaining": None, "used_percent": None, "tone": None},
        "other_currencies": {}, "money_in": {}, "color": "#64748b", "pinned": False,
        "total": {"budget": None, "spent": "12.50", "remaining": None, "used_percent": None, "tone": None},
    }]
    assert (expense["status"], expense["is_favorite"], expense["task_id"], expense["step_id"]) == (
        "posted", False, None, None)
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        assert [row[0] for row in con.execute("SELECT kind FROM events")][-1] == "money_changed"
    finally:
        con.close()


def test_the_summary_wire_uses_by_project():
    """H1: the month summary groups by project, and every expense row names
    its project and carries the project's id. The category keys are gone."""
    c = _client()
    for name in ("food", "travel"):       # a web-typed name is exact-or-ask: the projects exist first
        c.post("/api/projects", json={"name": name}, headers=O)
    food = c.post("/api/money/expenses", json={"amount": "12,50", "project": "food"}, headers=O).json()
    again = c.post("/api/money/expenses", json={"amount": "2", "project": "Food"}, headers=O).json()
    travel = c.post("/api/money/expenses", json={"amount": "5", "project": "travel"}, headers=O).json()
    assert (food["project"], again["project"], travel["project"]) == ("food", "food", "travel")
    assert food["project_id"] == again["project_id"] != travel["project_id"]
    assert "category" not in food
    assert _stored_project_ids() == {food["id"]: food["project_id"], again["id"]: again["project_id"],
                                     travel["id"]: travel["project_id"]}
    listed = {e["id"]: (e["project"], e["project_id"]) for e in c.get("/api/money/expenses").json()}
    assert listed[travel["id"]] == ("travel", travel["project_id"])
    summary = c.get("/api/money/summary").json()
    assert set(summary) == {"month", "currency", "total", "expense_count", "by_project", "other_currencies", "money_in",
                            "today", "previous", "change_percent", "limits", "top_project", "coming_up",
                            "pinned_projects", "pinned_expenses"}
    rows = summary["by_project"]
    assert [{key: row[key] for key in ("project", "spent", "budget", "remaining")} for row in rows] == [
        {"project": "food", "spent": "14.50", "budget": None, "remaining": None},
        {"project": "travel", "spent": "5.00", "budget": None, "remaining": None},
    ]
    assert set(rows[0]) == {"project", "project_id", "currency", "spent", "budget", "remaining", "month",
                            "other_currencies", "money_in", "color", "pinned",
                            "total"}
    assert [(row["project_id"], row["currency"]) for row in rows] == [
        (food["project_id"], "EUR"), (travel["project_id"], "EUR")]


def test_a_bad_amount_or_month_is_422():
    c = _client()
    assert c.post("/api/money/expenses", json={"amount": "abc"}, headers=O).status_code == 422
    assert c.get("/api/money/summary?month=2026-13").status_code == 422


def test_money_needs_a_login_and_the_origin():
    assert TestClient(create_app()).get("/api/money/summary").status_code == 401
    assert _client().post("/api/money/expenses", json={"amount": 1}, headers={"Origin": "http://evil.example"}).status_code == 403


async def test_keep_vouches_for_a_web_made_expense_and_the_project_it_shows():
    """Final review: a web-made expense (or a web-made project name its row
    shows) kept every list_expenses / money_summary over that month tainted.
    The row shows the chip, and Keep clears both, so the month reads clean."""
    import httpx

    from roost.db.connection import init_db
    from roost.gateway.auth import register_user
    from roost.money.amounts import parse_amount
    from roost.money.service import ExpenseEntry

    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    await register_user(cfg, "bob", "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        money = app.state.money
        web, _ = await money.log_expense(alice_id, ExpenseEntry(amount=parse_amount("9"), spent_at=today_madrid(),
                                                                project="gadgets"), tainted=True)
        mine, _ = await money.log_expense(alice_id, ExpenseEntry(amount=parse_amount("3"), spent_at=today_madrid(),
                                                                 project="gadgets"))
        listed = {e["id"]: e["tainted"] for e in (await alice.get("/api/money/expenses")).json()}
        assert listed == {web.id: True, mine.id: True}     # mine shows the web-made project name
        assert (await bob.post(f"/api/money/expenses/{web.id}/keep", headers=O)).status_code == 404
        assert (await alice.post(f"/api/money/expenses/{web.id}/keep",
                                 headers={"Origin": "http://evil.example"})).status_code == 403
        kept = await alice.post(f"/api/money/expenses/{web.id}/keep", headers=O)
        assert kept.status_code == 200 and kept.json()["tainted"] is False
        assert [e["tainted"] for e in (await alice.get("/api/money/expenses")).json()] == [False, False]
        _, tainted = await money.summary(alice_id, current_month())
        assert tainted is False
        assert (await alice.post("/api/money/expenses/no-such/keep", headers=O)).status_code == 404



async def test_a_void_expense_is_listed_but_left_out_of_the_summary():
    """H6: a void expense still shows in the month's list (with its status),
    and the summary leaves it out of the total, the count and its project's row."""
    import httpx

    from roost.db.connection import init_db
    from roost.gateway.auth import register_user
    from roost.money.expense_store import ExpenseStore
    from roost.money.models import ExpensePatch

    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as alice:
        await alice.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
        kept = (await alice.post("/api/money/expenses", json={"amount": "10"}, headers=O)).json()
        voided = (await alice.post("/api/money/expenses", json={"amount": "99"}, headers=O)).json()
        await ExpenseStore(cfg).update(alice_id, voided["id"], ExpensePatch({"status": "void"}))
        listed = {e["id"]: e["status"] for e in (await alice.get("/api/money/expenses")).json()}
        summary = (await alice.get("/api/money/summary")).json()
    assert listed == {kept["id"]: "posted", voided["id"]: "void"}
    assert (summary["total"], summary["expense_count"]) == ("10.00", 1)
    [row] = summary["by_project"]
    assert (row["project"], row["currency"], row["spent"], row["month"]["tone"]) == ("General", "EUR", "10.00", None)


async def test_star_and_void_an_expense_from_the_board():
    """Hub P6, H6: PUT …/star and …/void answer with the expense's row. A void
    expense stays listed and leaves the month's sums until it is posted again.
    Each change publishes money_changed "expense_updated"."""
    import httpx

    from roost.db.connection import init_db
    from roost.gateway.auth import register_user

    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as alice:
        await alice.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
        await alice.post("/api/projects", json={"name": "food"}, headers=O)
        lunch = (await alice.post("/api/money/expenses", json={"amount": "12", "project": "food"}, headers=O)).json()
        star, void = f"/api/money/expenses/{lunch['id']}/star", f"/api/money/expenses/{lunch['id']}/void"
        starred = await alice.put(star, json={"starred": True}, headers=O)
        voided = await alice.put(void, json={"void": True}, headers=O)
        summary = (await alice.get("/api/money/summary")).json()
        listed = (await alice.get("/api/money/expenses")).json()
        posted = await alice.put(void, json={"void": False}, headers=O)
        unstarred = await alice.put(star, json={"starred": False}, headers=O)
        not_a_bool = await alice.put(star, json={"starred": "yes"}, headers=O)
        missing = await alice.put("/api/money/expenses/no-such-expense/void", json={"void": True}, headers=O)
        frames = await app.state.events.since(alice_id, 0)
    assert (starred.status_code, starred.json()["is_favorite"], starred.json()["project"]) == (200, True, "food")
    assert (voided.json()["status"], voided.json()["is_favorite"]) == ("void", True)
    assert (summary["total"], summary["expense_count"]) == ("0.00", 0)
    assert [(e["id"], e["status"]) for e in listed] == [(lunch["id"], "void")]
    assert (posted.json()["status"], unstarred.json()["is_favorite"]) == ("posted", False)
    assert (not_a_bool.status_code, missing.status_code, missing.json()["detail"]) == (422, 404, "Expense not found")
    changes = [f["change"] for f in frames if f["type"] == "money_changed" and f["change"].startswith("expense_")]
    assert changes == ["expense_created"] + ["expense_updated"] * 4


async def test_an_expense_names_its_project_by_id_and_takes_its_currency():
    """A project's page adds an expense by the project's id. It lands in
    exactly that project. With no currency sent it takes the project's (H7),
    whether the project is named by id or by name. A project that isn't the
    user's is refused, and so is naming it twice. An archived project takes
    no new expense (H3)."""
    import httpx

    from roost.db.connection import init_db
    from roost.gateway.auth import register_user
    from roost.money.service import ARCHIVED_TEXT

    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    for name in ("alice", "bob"):
        await register_user(cfg, name, "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        trip = (await alice.post("/api/projects", json={"name": "Trip", "currency": "USD"}, headers=O)).json()
        shed = (await bob.post("/api/projects", json={"name": "Shed"}, headers=O)).json()
        taxi = await alice.post("/api/money/expenses", json={"amount": "30", "project_id": trip["id"]}, headers=O)
        tip = await alice.post("/api/money/expenses", json={"amount": "4", "project": "Trip"}, headers=O)
        euros = await alice.post("/api/money/expenses", json={"amount": "8", "project_id": trip["id"],
                                                               "currency": "EUR"}, headers=O)
        foreign = await alice.post("/api/money/expenses", json={"amount": "1", "project_id": shed["id"]}, headers=O)
        twice = await alice.post("/api/money/expenses", json={"amount": "1", "project": "Trip",
                                                               "project_id": trip["id"]}, headers=O)
        await alice.patch(f"/api/projects/{trip['id']}", json={"status": "archived"}, headers=O)
        archived = await alice.post("/api/money/expenses", json={"amount": "2", "project_id": trip["id"]}, headers=O)
        listed = (await alice.get("/api/money/expenses")).json()
        page = (await alice.get(f"/api/projects/{trip['id']}")).json()
    assert (taxi.status_code, taxi.json()["project"], taxi.json()["project_id"], taxi.json()["currency"]) == (
        201, "Trip", trip["id"], "USD")
    assert (tip.status_code, tip.json()["project_id"], tip.json()["currency"]) == (201, trip["id"], "USD")
    assert euros.json()["currency"] == "EUR"
    assert (foreign.status_code, foreign.json()["detail"]) == (422, "No such project.")
    assert twice.status_code == 422
    assert (archived.status_code, archived.json()["detail"]) == (422, ARCHIVED_TEXT.format(name="Trip"))
    assert sorted(e["amount"] for e in listed) == ["30.00", "4.00", "8.00"]
    assert (page["total"]["spent"], page["other_currencies"]) == ("34.00", {"EUR": "8.00"})


async def test_another_users_expense_cannot_be_starred_or_voided():
    import httpx

    from roost.db.connection import init_db
    from roost.gateway.auth import register_user

    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    for name in ("alice", "bob"):
        await register_user(cfg, name, "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        lunch = (await alice.post("/api/money/expenses", json={"amount": "12"}, headers=O)).json()
        for path, body in ((f"/api/money/expenses/{lunch['id']}/star", {"starred": True}),
                           (f"/api/money/expenses/{lunch['id']}/void", {"void": True})):
            assert (await bob.put(path, json=body, headers=O)).status_code == 404, path
            assert (await alice.put(path, json=body, headers={"Origin": "http://evil.example"})).status_code == 403
        [row] = (await alice.get("/api/money/expenses")).json()
    assert (row["status"], row["is_favorite"]) == ("posted", False)
