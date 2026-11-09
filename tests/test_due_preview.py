"""The live date preview (Amendment T): the resolved date in Madrid time, e.g. "Wed 21 Oct 09:00"."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from roost.gateway.app import create_app
from tz_helpers import MADRID_TZ
from roost.tasks.due_preview import preview

NOW = datetime(2026, 10, 20, 14, 0, tzinfo=MADRID_TZ)


@pytest.mark.parametrize(("stamp", "text"), [
    ("2026-10-21T09:00:00+02:00", "Wed 21 Oct 09:00"),
    ("2026-10-21", "Wed 21 Oct"),
    ("2026-10-21T07:00:00+00:00", "Wed 21 Oct 09:00"),            # UTC is shown in Madrid time
    ("2026-10-26T23:30:00+00:00", "Tue 27 Oct 00:30"),            # across midnight, after the clocks change
    ("2026-10-28T08:05:00+01:00", "Wed 28 Oct 08:05"),
    ("2027-01-05", "Tue 5 Jan 2027"),                            # another year says its year
    ("2027-01-05T18:30:00+01:00", "Tue 5 Jan 2027 18:30"),
])
def test_preview(stamp, text):
    assert preview(stamp, now=NOW) == text


def test_preview_of_nothing_or_nonsense_is_none():
    assert preview(None, now=NOW) is None and preview("", now=NOW) is None and preview("soon", now=NOW) is None


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers={"Origin": "http://127.0.0.1:18800"}).status_code == 201
    return c


def test_the_parse_route_says_the_resolved_dates():
    c = _client()
    read = c.post("/api/tasks/parse", json={"text": "Call Ana 2030-03-06 at 9 ^1h before"},
                  headers={"Origin": "http://127.0.0.1:18800"}).json()
    assert read["due_text"] == "Wed 6 Mar 2030 09:00"
    assert read["reminder_text"] == "Wed 6 Mar 2030 08:00"
    none = c.post("/api/tasks/parse", json={"text": "Call Ana"}, headers={"Origin": "http://127.0.0.1:18800"}).json()
    assert none["due_text"] is None and none["reminder_text"] is None
