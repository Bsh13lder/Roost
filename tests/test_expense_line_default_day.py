"""``default_day`` on ``POST /api/money/parse`` (G12): the money calendar's "+" on a day."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from roost.gateway.app import create_app
from roost.money.months import today_madrid

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _day(offset: int) -> str:
    return (date.fromisoformat(today_madrid()) + timedelta(days=offset)).isoformat()


def _parse(c: TestClient, text: str, **body):
    return c.post("/api/money/parse", json={"text": text, **body}, headers=O)


def test_default_day_fills_only_when_the_line_names_no_day():
    c = _client()
    plain = _parse(c, "€12 lunch", default_day=_day(-3))
    assert plain.status_code == 200, plain.text
    line = plain.json()
    assert (line["spent_at"], line["day_words"], line["day_problem"], line["ready"]) == (_day(-3), None, None, True)
    assert line["spent_text"] == date.fromisoformat(_day(-3)).strftime("%a %-d %b")
    named = _parse(c, "€12 lunch yesterday", default_day=_day(-3)).json()
    assert (named["spent_at"], named["day_words"]) == (_day(-1), "yesterday")
    assert _parse(c, "€12 lunch").json()["spent_at"] == _day(0)
    assert _parse(c, "€12 lunch", default_day=_day(0)).json()["spent_at"] == _day(0)


def test_a_future_default_day_is_a_problem():
    c = _client()
    line = _parse(c, "€12 lunch", default_day=_day(2)).json()
    assert line["day_problem"] and "future day" in line["day_problem"]
    assert line["spent_at"] == _day(0)
    assert line["ready"] is False
    # a day typed in the line still wins over a future default
    assert _parse(c, "€12 lunch yesterday", default_day=_day(2)).json()["day_problem"] is None


def test_default_day_must_be_an_iso_day():
    c = _client()
    for bad in ("21/10/2026", "2026-13-40", "2026-2-3", "tomorrow", "", "2026-10-21T09:00"):
        response = _parse(c, "€12 lunch", default_day=bad)
        assert response.status_code == 422, bad
    assert _parse(c, "€12 lunch", default_day=None).status_code == 200
