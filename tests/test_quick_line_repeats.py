"""The quick line's richer repeats (Amendment T): rules, starting / ending, and from completion."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from roost.gateway.app import create_app
from tz_helpers import MADRID_TZ
from roost.tasks.repeat_rule import RepeatRule, rule_json

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _parse(c: TestClient, text: str, **fields) -> dict:
    read = c.post("/api/tasks/parse", json={"text": text, **fields}, headers=O)
    assert read.status_code == 200, read.text
    return read.json()


def _today() -> str:
    return datetime.now(MADRID_TZ).date().isoformat()


def test_every_other_monday_starts_on_the_next_monday():
    read = _parse(_client(), "Gym every other Monday")
    assert read["title"] == "Gym"
    assert read["recurring"] == rule_json(RepeatRule(every=2, unit="week", weekday=0))
    assert read["repeat_text"] == "every other Monday" and read["repeat_problem"] is None
    due = datetime.fromisoformat(read["due_date"])
    assert due.weekday() == 0 and due.hour == 9


def test_every_3_days_starts_today():
    read = _parse(_client(), "Water plants every 3 days")
    assert read["recurring"] == rule_json(RepeatRule(every=3, unit="day"))
    assert read["due_date"] == _today() and read["repeat_text"] == "every 3 days"


def test_starting_a_date_is_the_first_occurrence():
    read = _parse(_client(), "Water plants every 2 weeks starting 2027-03-03")
    assert read["title"] == "Water plants" and read["due_date"] == "2027-03-03"
    assert read["recurring"] == rule_json(RepeatRule(every=2, unit="week"))


def test_starting_works_with_a_plain_repeat_too():
    read = _parse(_client(), "Water plants every Monday starting 2027-03-01")
    assert read["title"] == "Water plants" and read["due_date"].startswith("2027-03-01")
    assert read["recurring"] == "0 9 * * 1"


def test_ending_a_date_sets_the_end():
    read = _parse(_client(), "Water plants every week ending 2027-06-30")
    assert read["title"] == "Water plants" and read["recur_until"] == "2027-06-30"
    assert read["repeat_text"].endswith("until Wed 30 Jun 2027")


def test_until_and_hasta_end_it_too():
    c = _client()
    assert _parse(c, "Pills every day until 2027-01-31")["recur_until"] == "2027-01-31"
    assert _parse(c, "Pastillas cada día hasta 2027-01-31")["recur_until"] == "2027-01-31"


def test_start_and_end_together():
    read = _parse(_client(), "Course every 2 weeks starting 2027-02-01 ending 2027-05-31")
    assert (read["title"], read["due_date"], read["recur_until"]) == ("Course", "2027-02-01", "2027-05-31")


def test_ending_without_a_repeat_stays_in_the_title():
    read = _parse(_client(), "Plan ending 2027-06-30")
    assert read["recur_until"] is None and read["recurring"] is None


def test_from_completion():
    c = _client()
    read = _parse(c, "Water plants every! 3 days")
    assert read["recurring"] == rule_json(RepeatRule(every=3, unit="day", from_completion=True))
    assert read["repeat_text"] == "every 3 days, when done"
    read = _parse(c, "Water plants every week when done")
    assert read["recurring"] == rule_json(RepeatRule(every=1, unit="week", from_completion=True))
    assert read["title"] == "Water plants"


def test_a_repeat_a_rule_cannot_say_is_a_question():
    read = _parse(_client(), "Water every other weekday")
    assert read["ready"] is False and read["repeat_problem"]


def test_removing_the_repeat_chip_keeps_all_its_words():
    read = _parse(_client(), "Course every 2 weeks ending 2027-05-31", skip=["repeat"])
    assert read["recurring"] is None and read["recur_until"] is None and "every 2 weeks" in read["title"]


def test_a_rule_is_stored_and_ended_over_http():
    c = _client()
    rule = rule_json(RepeatRule(every=2, unit="week"))
    made = c.post("/api/tasks", json={"title": "Course", "due_date": "2027-02-01", "recurring": rule,
                                      "recur_until": "2027-05-31"}, headers=O)
    assert made.status_code in (200, 201), made.text
    assert made.json()["recur_until"] == "2027-05-31" and made.json()["recurring"] == rule
    assert c.post("/api/tasks", json={"title": "x", "recur_until": "nope"}, headers=O).status_code == 422
