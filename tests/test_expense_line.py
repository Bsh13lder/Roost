"""The expense quick line over HTTP (Task 6): ``POST /api/money/parse`` and the exact-or-ask project names."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from roost.gateway.app import create_app
from roost.money.months import today_madrid

O = {"Origin": "http://127.0.0.1:18800"}


def _client(name: str = "alice") -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": name, "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _project(c: TestClient, name: str, **body) -> dict:
    r = c.post("/api/projects", json={"name": name, **body}, headers=O)
    assert r.status_code == 201, r.text
    return r.json()


def _parse(c: TestClient, text: str, **body) -> dict:
    r = c.post("/api/money/parse", json={"text": text, **body}, headers=O)
    assert r.status_code == 200, r.text
    return r.json()


def _yesterday() -> str:
    return (date.fromisoformat(today_madrid()) - timedelta(days=1)).isoformat()


def test_expense_line_en():
    c = _client()
    trip = _project(c, "Trip")
    line = _parse(c, "€12 lunch /Trip yesterday vendor:Mercadona *")
    assert (line["amount"], line["currency"], line["note"]) == ("12.00", "EUR", "lunch")
    assert (line["project"]["id"], line["project"]["name"]) == (trip["id"], "Trip")
    assert (line["spent_at"], line["vendor"], line["starred"], line["ready"]) == (_yesterday(), "Mercadona", True, True)
    assert line["income"] is False and line["cadence"] is None


def test_expense_line_es():
    c = _client()
    viaje = _project(c, "Viaje")
    line = _parse(c, '12,50€ comida /Viaje ayer tienda:"El Corte Inglés"')
    assert (line["amount"], line["note"], line["vendor"]) == ("12.50", "comida", "El Corte Inglés")
    assert (line["project"]["id"], line["spent_at"], line["ready"]) == (viaje["id"], _yesterday(), True)


def test_a_future_day_is_a_problem():
    line = _parse(_client(), "€5 taxi tomorrow")
    assert line["day_problem"] and "future" in line["day_problem"]
    assert line["ready"] is False


def test_unknown_project_is_a_question_never_made():
    c = _client()
    line = _parse(c, "€5 coffee /Nowhere")
    assert line["project"] is None and "Nowhere" in line["project_question"] and line["ready"] is False
    assert c.get("/api/projects").json() == []


def test_project_page_default_and_currency_from_project():
    c = _client()
    usd = _project(c, "States", currency="USD")
    line = _parse(c, "12 lunch", project_id=usd["id"])
    assert (line["project"]["id"], line["currency"], line["amount"], line["note"]) == (usd["id"], "USD", "12.00", "lunch")
    explicit = _parse(c, "€12 lunch", project_id=usd["id"])
    assert explicit["currency"] == "EUR"                    # a typed sign wins
    gone = _parse(c, "12 lunch", project_id="not-a-project")
    assert gone["project"] is None and gone["project_question"] and gone["ready"] is False


def test_a_repeat_word_reads_as_a_cadence():
    c = _client()
    _project(c, "Casa")
    line = _parse(c, "€9,99 Netflix /Casa monthly")
    assert (line["amount"], line["note"], line["cadence"], line["repeat_words"]) == ("9.99", "Netflix", "monthly", "monthly")
    assert line["ready"] is True
    daily = _parse(c, "€1 gum every day")
    assert daily["cadence"] is None and daily["repeat_problem"] and daily["ready"] is False


def test_hash_is_not_a_project_on_the_expense_line():
    c = _client()
    _project(c, "Trip")
    line = _parse(c, "€12 lunch #Trip")
    assert line["project"] is None and line["project_question"] is None
    assert line["note"] == "lunch #Trip"


def test_maths_and_income_in_the_amount():
    c = _client()
    worked = _parse(c, "€2x31 shirts")
    assert (worked["amount"], worked["amount_math"], worked["income"]) == ("62.00", "2×31", False)
    bad = _parse(c, "€5/0 oops")
    assert bad["amount"] is None and bad["amount_problem"] and bad["ready"] is False
    money_in = _parse(c, "+€500 salary")
    assert (money_in["amount"], money_in["income"], money_in["note"]) == ("500.00", True, "salary")
    assert money_in["ready"] is True and money_in["income_problem"] is None      # money in is saved as income (v21)


def test_skip_keeps_the_words_in_the_note():
    c = _client()
    _project(c, "Trip")
    line = _parse(c, "€12 lunch /Trip", skip=["project"])
    assert line["project"] is None and line["note"] == "lunch /Trip"


def test_parse_needs_login_origin_and_a_text():
    assert TestClient(create_app()).post("/api/money/parse", json={"text": "€1"}, headers=O).status_code == 401
    c = _client()
    assert c.post("/api/money/parse", json={"text": "€1"}, headers={"Origin": "http://evil.example"}).status_code == 403
    assert c.post("/api/money/parse", json={"text": "€1", "skip": ["bogus"]}, headers=O).status_code == 422
    assert c.post("/api/money/parse", json={"text": "x" * 1000}, headers=O).status_code == 422


async def test_another_users_project_id_reads_as_gone():
    from money_http import two_users

    async with two_users() as (alice, bob, _):
        shed = (await bob.post("/api/projects", json={"name": "Shed"}, headers=O)).json()
        line = (await alice.post("/api/money/parse", json={"text": "€3 nails", "project_id": shed["id"]},
                                 headers=O)).json()
    assert line["project"] is None and line["project_question"]


def test_typed_project_name_never_creates_a_project_on_the_web():
    c = _client()
    r = c.post("/api/money/expenses", json={"amount": "5", "project": "ghost"}, headers=O)
    assert r.status_code == 422 and "ghost" in r.json()["detail"]
    assert c.get("/api/projects").json() == []
    trip = _project(c, "Trip")
    ok = c.post("/api/money/expenses", json={"amount": "5", "project": "trip"}, headers=O)
    assert ok.status_code == 201 and ok.json()["project_id"] == trip["id"]
    general = c.post("/api/money/expenses", json={"amount": "5"}, headers=O)
    assert general.status_code == 201 and general.json()["project"] == "General"


def test_vendor_and_star_are_saved():
    c = _client()
    r = c.post("/api/money/expenses", json={"amount": "5", "vendor": "Mercadona", "starred": True}, headers=O)
    assert r.status_code == 201
    assert (r.json()["vendor"], r.json()["is_favorite"]) == ("Mercadona", True)
    assert c.post("/api/money/expenses", json={"amount": "5", "vendor": "v" * 81}, headers=O).status_code == 422
    assert c.post("/api/money/expenses", json={"amount": "5", "starred": "yes"}, headers=O).status_code == 422
