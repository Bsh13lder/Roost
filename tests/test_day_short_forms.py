"""Short day and word forms, English and Spanish (user rulings 2026-10-20): whole words only; "mar" is
Tuesday only in a Spanish line or before a time, otherwise March / plain text."""

from __future__ import annotations

from datetime import date, datetime, time

import pytest
from fastapi.testclient import TestClient

from roost.gateway.app import create_app
from tz_helpers import MADRID_TZ
from roost.tasks.day_words import find_day

NOW = datetime(2026, 10, 20, 14, 0, tzinfo=MADRID_TZ)        # a Tuesday
O = {"Origin": "http://127.0.0.1:18800"}


def _day(text: str) -> date | None:
    found = find_day(text, now=NOW)
    return None if found is None else found.day


@pytest.mark.parametrize(("word", "day"), [
    ("mon", 26), ("tue", 27), ("tues", 27), ("wed", 21), ("thu", 22), ("thur", 22), ("thurs", 22), ("fri", 23),
    ("sat", 24), ("sun", 25), ("MON", 26),
    ("lun", 26), ("mie", 21), ("mié", 21), ("jue", 22), ("vie", 23), ("sab", 24), ("sáb", 24), ("dom", 25),
])
def test_short_days_are_whole_words(word, day):
    assert _day(f"Call Ana {word}") == date(2026, 10, day)
    assert _day(f"{word} call Ana") == date(2026, 10, day)


@pytest.mark.parametrize(("word", "day"), [
    ("tom", 21), ("tmr", 21), ("tmrw", 21), ("TMRW", 21), ("mnn", 21), ("mñn", 21), ("tod", 20),
    ("nxt wk", 26), ("nxt week", 26), ("next wk", 26),
])
def test_short_words(word, day):
    assert _day(f"Call Ana {word}") == date(2026, 10, day)


@pytest.mark.parametrize("text", [
    "Call Tomas", "Fix the monitor", "Sunny walk", "Saturn", "tomato soup", "todo list", "Wedding", "dominio",
    "Thursdays", "Satellite", "Luna", "tmrwx",
])
def test_not_inside_longer_words(text):
    assert _day(text) is None


def test_mar_is_tuesday_in_a_spanish_line():
    assert _day("Reunión el mar") == date(2026, 10, 27)
    assert _day("Llamar a Ana mañana mar") == date(2026, 10, 21)       # tomorrow wins; mar is left over
    assert _day("Comprar pan para el mar") == date(2026, 10, 27)
    assert _day("Cena con Ana mar") == date(2026, 10, 27)              # "con" is a Spanish clue


def test_mar_before_a_time_is_tuesday():
    assert _day("Meeting mar 9:00") == date(2026, 10, 27)
    assert _day("Meeting mar 5pm") == date(2026, 10, 27)
    assert _day("Meeting mar at 9") == date(2026, 10, 27)


def test_mar_alone_stays_text_or_is_march():
    assert _day("Pay mar") is None
    assert _day("Pay mar 5") == date(2027, 3, 5)
    assert _day("Beach mar") is None


def test_the_short_forms_over_the_wire():
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    read = c.post("/api/tasks/parse", json={"text": "Call Ana tmrw 9am"}, headers=O).json()
    assert read["title"] == "Call Ana" and read["due_date"].endswith("T09:00:00+01:00") or read["due_date"].endswith("T09:00:00+02:00")
    read = c.post("/api/tasks/parse", json={"text": "Water plants every mon"}, headers=O).json()
    assert read["recurring"] == "0 9 * * 1" and read["title"] == "Water plants"
    read = c.post("/api/tasks/parse", json={"text": "Regar cada vie y dom"}, headers=O).json()
    assert read["recurring"] == "0 9 * * 0,5"
