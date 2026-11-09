"""Cancelling a match (user ruling 2026-10-20): the chip's words go back to the title as plain text, and
those words are not read again while the user keeps typing. ``keep`` names the words; ``matches`` says
which words each chip came from."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from roost.gateway.app import create_app

O = {"Origin": "http://127.0.0.1:18800"}


@pytest.fixture()
def client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    c.post("/api/projects", json={"name": "Reno"}, headers=O)
    c.post("/api/bots", json={"name": "Scout", "job": "helps", "instructions": "",
                              "avatar": {"shape": "round", "color": "#22c55e", "badge": "none"}}, headers=O)
    return c


def _parse(c: TestClient, text: str, **fields) -> dict:
    read = c.post("/api/tasks/parse", json={"text": text, **fields}, headers=O)
    assert read.status_code == 200, read.text
    return read.json()


@pytest.mark.parametrize(("line", "kind", "words"), [
    ("Call Ana tomorrow at 9 please", "date", ["tomorrow", "at 9"]),
    ("Call Ana tmrw", "date", ["tmrw"]),
    ("Pay rent p1", "priority", ["p1"]),
    ("Pay rent !!", "priority", ["!!"]),
    ("Pay urgent rent today", "date", ["today"]),
    ("Send invoice *", "star", ["*"]),
    ("Paint ~1h30", "estimate", ["~1h30"]),
    ("Call Ana tomorrow ^30m before", "reminder", ["^30m before"]),
    ("Water every Monday", "repeat", ["every Monday"]),
    ("Order /Reno", "project", ["/Reno"]),
    ("Plumber /Reno €200", "budget", ["€200"]),
    ("Book @Scout", "assignee", ["@Scout"]),
    ("Milk #shopping #home", "tag", ["#shopping", "#home"]),
])
def test_matches_name_the_words_of_each_chip(client, line, kind, words):
    assert _parse(client, line)["matches"][kind] == words


def test_no_match_no_words(client):
    assert _parse(client, "Just a title")["matches"] == {}


@pytest.mark.parametrize(("line", "keep", "field"), [
    ("Call Ana tomorrow at 9", ["tomorrow", "at 9"], "due_date"),
    ("Pay rent p1", ["p1"], "priority"),
    ("Send invoice *", ["*"], "starred"),
    ("Paint ~1h", ["~1h"], "estimate_minutes"),
    ("Call tmrw ^30m before", ["^30m before"], "reminder_at"),
    ("Order /Reno", ["/Reno"], "project"),
    ("Book @Scout", ["@Scout"], "assignee"),
])
def test_kept_words_are_plain_title_text(client, line, keep, field):
    read = _parse(client, line, keep=keep)
    assert not read[field]
    for word in keep:
        assert word in read["title"]


def test_a_kept_word_is_title_text_where_it_stands(client):
    read = _parse(client, "Call Ana tomorrow at the shop", keep=["tomorrow"])
    assert read["title"] == "Call Ana tomorrow at the shop" and read["due_date"] is None


def test_a_kept_word_does_not_stop_a_new_one_being_read(client):
    read = _parse(client, "Call Ana tomorrow on Friday", keep=["tomorrow"])
    assert read["title"] == "Call Ana tomorrow" and read["due_date"] is not None
    assert read["matches"]["date"] == ["on Friday"] or "Friday" in " ".join(read["matches"]["date"])


def test_kept_words_match_whole_words_in_any_case(client):
    read = _parse(client, "Tomorrow call Ana", keep=["tomorrow"])
    assert read["title"] == "Tomorrow call Ana" and read["due_date"] is None
    read = _parse(client, "Call Tomas tomorrow", keep=["tom"])          # "tom" is not a part of "Tomas"
    assert read["due_date"] is not None


def test_kept_words_survive_other_edits(client):
    keep = ["tomorrow"]
    first = _parse(client, "Call Ana tomorrow", keep=keep)
    second = _parse(client, "Call Ana tomorrow and Bob", keep=keep)
    third = _parse(client, "Hello. Call Ana tomorrow, and Bob. #x", keep=keep)
    assert [r["due_date"] for r in (first, second, third)] == [None, None, None]
    assert second["title"] == "Call Ana tomorrow and Bob" and third["tags"] == ["x"]


def test_a_phrase_that_is_not_there_is_ignored(client):
    assert _parse(client, "Call Ana tomorrow", keep=["friday"])["due_date"] is not None


def test_keep_is_bounded(client):
    too_many = client.post("/api/tasks/parse", json={"text": "x", "keep": ["a"] * 17}, headers=O)
    too_long = client.post("/api/tasks/parse", json={"text": "x", "keep": ["a" * 81]}, headers=O)
    assert too_many.status_code == 422 and too_long.status_code == 422


def test_odd_characters_in_keep_are_harmless(client):
    read = _parse(client, "Cost (a+b) [x] tomorrow", keep=["(a+b)", "[x]", "", ""])
    assert read["title"].startswith("Cost (a+b) [x]") and read["due_date"] is not None
