"""The quick-add line (redesign P3): the server reads `Call plumber tomorrow 9am /Renovation €200 !high`,
and the web draws its chips from that reading."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from tz_helpers import MADRID_TZ
from roost.tasks.quick_line import read_date, read_words

O = {"Origin": "http://127.0.0.1:18800"}


def _tomorrow() -> date:
    return datetime.now(MADRID_TZ).date() + timedelta(days=1)


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _parse(c: TestClient, text: str, **fields) -> dict:
    read = c.post("/api/tasks/parse", json={"text": text, **fields}, headers=O)
    assert read.status_code == 200, read.text
    return read.json()


@pytest.mark.parametrize(("text", "priority", "amount", "currency", "project", "rest"), [
    ("Call plumber /Renovation €200 !high", "high", "200", "EUR", "Renovation", "Call plumber"),
    ("Pay 12,50$ !LOW", "low", "12,50", "USD", None, "Pay"),
    ("Buy stamps £3", None, "3", "GBP", None, "Buy stamps"),
    ("wow!high stays, so does €", None, None, None, None, "wow!high stays, so does €"),
])
def test_the_words_each_kind_reads(text, priority, amount, currency, project, rest):
    words = read_words(text)
    assert (words.priority, words.amount, words.currency, words.project_ref) == (priority, amount, currency, project)
    assert " ".join(words.rest.split()) == rest


def test_a_skipped_kind_keeps_its_words():
    words = read_words("Book 2 tickets /Trip €20 !high", frozenset({"project", "budget", "priority"}))
    assert (words.priority, words.amount, words.project_ref) == (None, None, None)
    assert read_date("Book 2 tickets", frozenset({"date"})) == (read_date("", frozenset())[0], "Book 2 tickets")


def test_the_whole_line_becomes_chips():
    c = _client()
    project = c.post("/api/projects", json={"name": "Renovation"}, headers=O).json()
    read = _parse(c, "Call plumber tomorrow 9am /Renovation €200 !high")
    nine = datetime.combine(_tomorrow(), time(9, 0), tzinfo=MADRID_TZ).isoformat()
    expected = {
        "title": "Call plumber", "due_date": nine, "priority": "high",
        "project": {"id": project["id"], "name": "Renovation", "currency": "EUR", "color": project["color"]},
        "project_words": "/Renovation", "project_question": None, "budget": "200.00", "budget_words": "€200",
        "budget_problem": None, "budget_currency": "EUR", "ready": True,
    }
    assert {key: read[key] for key in expected} == expected          # the rich keys are additive (Tasks & Money)
    assert (read["starred"], read["recurring"], read["assignee"], read["warnings"]) == (False, None, None, [])


def test_a_near_project_name_asks_and_a_foreign_sign_or_no_project_explains():
    """Review Focus 3: never a silent wrong project, never a slice in the wrong currency."""
    c = _client()
    c.post("/api/projects", json={"name": "Renovation"}, headers=O)
    near = _parse(c, "Paint /Renovaton €20")
    assert (near["project"], near["ready"], near["budget"]) == (None, False, None)
    assert "Renovaton" in near["project_question"] and near["budget_words"] == "€20"
    foreign = _parse(c, "Paint /Renovation $20")
    assert foreign["budget_problem"] == "“Renovation” keeps its money in EUR: write the budget in EUR."
    unknown = _parse(c, "Paint /Garage")
    assert unknown["project_question"] == "No project is called “Garage”. Make it on the Projects tab first."
    c.post("/api/money/expenses", json={"amount": "5"}, headers=O)          # a loose expense makes General
    general = _parse(c, "Paint /General")
    assert general["project_question"].startswith("General is where expenses with no project go")


def test_a_line_in_no_project_takes_a_budget_in_generals_currency():
    """Owner, 2026-10-26: like the drawer, a task in no project takes a budget, counted in General's currency."""
    c = _client()
    loose = _parse(c, "Buy shoes €30")
    assert (loose["title"], loose["project"], loose["budget"], loose["budget_currency"]) == ("Buy shoes", None, "30.00", "EUR")
    assert (loose["budget_problem"], loose["ready"]) == (None, True)
    made = c.post("/api/tasks", json={"title": loose["title"], "allocated_budget": loose["budget"]}, headers=O)
    assert made.status_code == 201, made.text
    assert (made.json()["project_id"], made.json()["allocated_budget"]) == (None, "30.00")
    assert _parse(c, "Buy shoes")["budget_currency"] is None


def test_a_line_in_no_project_with_another_sign_asks_for_generals_currency():
    c = _client()
    foreign = _parse(c, "Buy shoes $30")
    assert (foreign["budget"], foreign["ready"]) == (None, False)
    assert foreign["budget_problem"] == "“General” keeps its money in EUR: write the budget in EUR."
    c.post("/api/money/expenses", json={"amount": "5"}, headers=O)          # General now exists, still in EUR
    assert _parse(c, "Buy shoes £30")["budget_problem"] == "“General” keeps its money in EUR: write the budget in EUR."
    assert _parse(c, "Buy shoes 30€")["budget"] == "30.00"


def test_a_project_page_passes_its_project_and_a_dismissed_date_stays_in_the_title():
    c = _client()
    garden = c.post("/api/projects", json={"name": "Garden", "currency": "GBP"}, headers=O).json()
    read = _parse(c, "Book 2 tickets £30", project_id=garden["id"], skip=["date"])
    assert (read["title"], read["due_date"], read["project"]["id"], read["budget"]) == ("Book 2 tickets", None, garden["id"], "30.00")


def test_an_empty_line_or_another_users_project_is_not_ready():
    c = _client()
    assert _parse(c, "   !high")["ready"] is False
    asyncio.run(register_user(load_config(), "bob", "pw-123456"))
    bob = TestClient(create_app())
    assert bob.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"}, headers=O).status_code == 200
    house = c.post("/api/projects", json={"name": "House"}, headers=O).json()
    sneaky = _parse(bob, "Paint", project_id=house["id"])
    assert (sneaky["project"], sneaky["project_question"]) == (None, "This project is gone.")


def test_parse_needs_the_origin_and_refuses_an_unknown_kind_or_a_long_line():
    c = _client()
    assert c.post("/api/tasks/parse", json={"text": "x"}, headers={"Origin": "http://evil.example"}).status_code == 403
    assert c.post("/api/tasks/parse", json={"text": "x", "skip": ["colour"]}, headers=O).status_code == 422
    assert c.post("/api/tasks/parse", json={"text": "x" * 301}, headers=O).status_code == 422


def test_a_project_name_of_several_words_is_taken_whole_and_leaves_the_title():
    names = ("ZZ", "ZZ smoke Reno", "Trip")
    words = read_words("Call plumber /zz  smoke reno €200 now", project_names=names)
    assert (words.project_ref, words.project_words) == ("ZZ smoke Reno", "/zz  smoke reno")
    assert " ".join(words.rest.split()) == "Call plumber now"
    one = read_words("Call plumber /ZZ smoke", project_names=names)      # no longer name matches: one word
    assert (one.project_ref, " ".join(one.rest.split())) == ("ZZ", "Call plumber smoke")
    assert read_words("Book /Trip to Rome", project_names=names).project_ref == "Trip"
    assert read_words("Book /Tri", project_names=names).project_ref == "Tri"


def test_the_longest_matching_name_wins_over_a_shorter_one():
    names = ("Home", "Home repairs", "Home repairs 2026")
    words = read_words("Fix door /Home repairs 2026 soon", project_names=names)
    assert (words.project_ref, " ".join(words.rest.split())) == ("Home repairs 2026", "Fix door soon")


def test_the_server_reads_a_multi_word_project_into_its_chip():
    c = _client()
    project = c.post("/api/projects", json={"name": "ZZ smoke Reno"}, headers=O).json()
    read = _parse(c, "Call plumber tomorrow 9am /ZZ smoke Reno €200 !high")
    assert read["title"] == "Call plumber"
    assert (read["project"]["id"], read["project_words"], read["project_question"]) == (
        project["id"], "/ZZ smoke Reno", None)
    assert (read["budget"], read["ready"]) == ("200.00", True)
