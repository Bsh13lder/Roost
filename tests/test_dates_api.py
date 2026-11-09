"""GET /api/dates/parse (redesign P1): the date pickers' typed-text preview, read the way a task's
due is read (parse_due, Europe/Madrid). A picked wall time is Madrid's clock, never UTC."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from roost.gateway.app import create_app
from tz_helpers import MADRID_TZ

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    client = TestClient(create_app())
    assert client.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"},
                       headers=O).status_code == 201
    return client


def _read(client: TestClient, text: str, kind: str | None = None):
    params = {"text": text} if kind is None else {"text": text, "kind": kind}
    return client.get("/api/dates/parse", params=params)


def _madrid_day(offset: int) -> str:
    return (datetime.now(MADRID_TZ) + timedelta(days=offset)).date().isoformat()


def test_words_read_on_madrid_time():
    client = _client()
    tomorrow = (datetime.now(MADRID_TZ) + timedelta(days=1)).date().isoformat()
    timed = _read(client, "tomorrow at 9").json()["due_date"]
    assert re.fullmatch(rf"{tomorrow}T09:00:00\+0[12]:00", timed)
    assert _read(client, "tomorrow").json() == {"due_date": tomorrow}


def test_a_picked_wall_time_is_read_on_madrid_time():
    client = _client()
    assert _read(client, "2026-10-16 09:00").json() == {"due_date": "2026-10-16T09:00:00+02:00"}   # summer time
    assert _read(client, "2026-12-01 09:00").json() == {"due_date": "2026-12-01T09:00:00+01:00"}   # winter time
    assert _read(client, "2026-10-16").json() == {"due_date": "2026-10-16"}


def test_no_text_is_no_date_and_unreadable_text_says_why():
    client = _client()
    assert _read(client, "").json() == {"due_date": None}
    refused = _read(client, "someday")
    assert refused.status_code == 422
    assert refused.json()["detail"] == "I could not read a date in “someday”. Try “tomorrow at 9” or 2026-10-20."


def test_it_needs_a_login_and_refuses_a_novel():
    assert TestClient(create_app()).get("/api/dates/parse", params={"text": "tomorrow"}).status_code == 401
    assert _read(_client(), "x" * 101).status_code == 422


def test_a_day_past_the_end_of_the_calendar_is_refused_not_a_500():
    client = _client()
    for text in ("in 99999999 days", "9999-12-31T23:59:59+00:00", "0001-01-01T00:00:00+23:59"):
        refused = _read(client, text)
        assert refused.status_code == 422, text
        assert refused.json()["detail"] == f"I could not read a date in “{text}”. Try “tomorrow at 9” or 2026-10-20."


def test_the_spent_kind_reads_an_expenses_day_the_way_an_expense_does():
    client = _client()
    for text, back in (("yesterday", 1), ("ayer", 1), ("today", 0), ("2 days ago", 2), ("hace 3 días", 3),
                       ("yesterday at 9", 1)):
        assert _read(client, text, "spent").json() == {"due_date": _madrid_day(-back)}, text
    assert _read(client, "2026-10-01", "spent").json() == {"due_date": "2026-10-01"}
    assert _read(client, "", "spent").json() == {"due_date": None}
    assert _read(client, "  ", "spent").json() == {"due_date": None}


def test_the_default_kind_is_still_the_task_due_reading():
    client = _client()
    assert _read(client, "yesterday").status_code == 422                       # parse_due cannot read it
    assert _read(client, "yesterday", "due").status_code == 422
    assert _read(client, "2 days ago").json() == _read(client, "2 days ago", "due").json()
    assert _read(client, "tomorrow", "due").json() == {"due_date": _madrid_day(1)}


def test_the_spent_kind_refuses_with_the_expense_sentence_and_a_future_day():
    client = _client()
    unreadable = _read(client, "someday", "spent")
    assert unreadable.status_code == 422
    assert unreadable.json()["detail"] == "I could not read a date in “someday”. Try 2026-10-12 or yesterday."
    future = _read(client, _madrid_day(1), "spent")
    assert future.status_code == 422
    assert "future date" in future.json()["detail"]
    for text in ("99999999999 days ago", "hace 99999999999 días", "in 99999999 days"):
        assert _read(client, text, "spent").status_code == 422, text           # never a 500


def test_an_unknown_kind_is_refused():
    assert _read(_client(), "tomorrow", "birthday").status_code == 422
