"""The money maths (Amendment T): €2x31, €12+8, €100/4. Decimal, at most 6 terms, no division by zero."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from roost.gateway.app import create_app
from roost.money.expression import ExpressionError, evaluate
from roost.tasks.line_tokens import read_amount_words, read_tokens

O = {"Origin": "http://127.0.0.1:18800"}


@pytest.mark.parametrize(("typed", "value", "shown"), [
    ("2x31", "62.00", "2×31"), ("2X31", "62.00", "2×31"), ("2×31", "62.00", "2×31"), ("2*31", "62.00", "2×31"),
    ("12+8", "20.00", "12+8"), ("100/4", "25.00", "100/4"), ("2+3x4", "14.00", "2+3×4"),
    ("100/3", "33.33", "100/3"), ("200/3", "66.67", "200/3"), ("1.200,50+3", "1203.50", "1200.5+3"),
    ("2.5x4", "10.00", "2.5×4"), ("1+1+1+1+1+1", "6.00", "1+1+1+1+1+1"), ("12,50", "12.50", None),
    ("7", "7.00", None),
])
def test_evaluate(typed, value, shown):
    result = evaluate(typed)
    assert (result.value, result.shown) == (Decimal(value), shown)
    assert isinstance(result.value, Decimal) and result.value == result.value.quantize(Decimal("0.01"))


@pytest.mark.parametrize(("typed", "why"), [
    ("5/0", "divide by zero"), ("5/(2-2)", "read"), ("1+1+1+1+1+1+1", "at most 6"), ("2x", "read"), ("x2", "read"),
    ("2xx3", "read"), ("0x5", "more than 0"), ("1x1000000000", "at most"), ("", "read"), ("2+-3", "read"),
])
def test_evaluate_refuses_in_plain_words(typed, why):
    with pytest.raises(ExpressionError, match=why):
        evaluate(typed)


def test_the_maths_is_exact_not_float():
    assert evaluate("0.1+0.2").value == Decimal("0.30") and evaluate("19.99x3").value == Decimal("59.97")


def test_the_amount_token_does_the_maths():
    tokens = read_tokens("Paint walls €3x45 !high")
    assert (tokens.amount, tokens.amount_math, tokens.currency, tokens.amount_words) == (
        Decimal("135.00"), "3×45", "EUR", "€3x45")
    assert (tokens.rest, tokens.income) == ("Paint walls", False)
    after = read_tokens("Paint 2x31€ walls")
    assert (after.amount, after.currency, after.amount_math, after.rest) == (Decimal("62.00"), "EUR", "2×31", "Paint walls")
    assert read_tokens("Pay €200").amount_math is None
    assert read_amount_words("Pay €12+8 now") == (Decimal("20.00"), "EUR", "€12+8")


def test_a_broken_sum_is_a_problem_and_leaves_the_line():
    tokens = read_tokens("Split €100/0 now")
    assert tokens.amount is None and tokens.amount_problem == "Can't divide by zero." and tokens.rest == "Split now"
    assert tokens.amount_words == "€100/0"


def test_plain_words_with_x_or_plus_are_not_money():
    assert read_tokens("Call 5x per day").amount is None
    assert read_tokens("Plan 2+2 things").amount is None


def test_a_plus_sign_marks_money_in():
    tokens = read_tokens("+€500 salary")
    assert (tokens.amount, tokens.income, tokens.rest, tokens.amount_words) == (Decimal("500.00"), True, "salary", "+€500")
    assert read_tokens("salary +500€").income is True
    assert read_tokens("salary €500").income is False
    both = read_tokens("bonus +€2x250")
    assert (both.amount, both.income, both.amount_math) == (Decimal("500.00"), True, "2×250")


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def test_a_task_budget_token_shows_the_maths():
    c = _client()
    c.post("/api/projects", json={"name": "Reno"}, headers=O)
    read = c.post("/api/tasks/parse", json={"text": "Paint walls /Reno €3x45"}, headers=O).json()
    assert (read["title"], read["budget"], read["budget_math"], read["ready"]) == ("Paint walls", "135.00", "3×45", True)
    plain = c.post("/api/tasks/parse", json={"text": "Paint walls /Reno €50"}, headers=O).json()
    assert plain["budget_math"] is None


def test_a_task_budget_refuses_a_broken_sum_and_money_in():
    c = _client()
    c.post("/api/projects", json={"name": "Reno"}, headers=O)
    bad = c.post("/api/tasks/parse", json={"text": "Paint /Reno €3/0"}, headers=O).json()
    assert bad["ready"] is False and bad["budget_problem"] == "Can't divide by zero." and bad["budget"] is None
    income = c.post("/api/tasks/parse", json={"text": "Paint /Reno +€30"}, headers=O).json()
    assert income["ready"] is False and "money in" in income["budget_problem"]
