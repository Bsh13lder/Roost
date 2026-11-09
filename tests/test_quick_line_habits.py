"""Todoist habits (Amendment T): p1-p4, "priority 1", the literal escape, and a removed chip's words."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from roost.gateway.app import create_app
from roost.tasks.line_tokens import read_tokens

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _parse(c: TestClient, text: str, **fields) -> dict:
    read = c.post("/api/tasks/parse", json={"text": text, **fields}, headers=O)
    assert read.status_code == 200, read.text
    return read.json()


@pytest.mark.parametrize(("typed", "level"), [
    ("Pay rent p1", "urgent"), ("Pay rent p2", "high"), ("Pay rent P3", "medium"), ("Pay rent p4", "low"),
    ("Pay rent priority 1", "urgent"), ("Pay rent Priority 2", "high"), ("Pay rent priority 4", "low"),
    ("p1 pay rent", "urgent"),
])
def test_todoist_priority_words(typed, level):
    tokens = read_tokens(typed)
    assert tokens.priority == level and tokens.rest.lower() == "pay rent"


@pytest.mark.parametrize("typed", ["Fix p5 bug", "Review p12", "priority 7 list", "Group p1x"])
def test_not_a_priority(typed):
    assert read_tokens(typed).priority is None and read_tokens(typed).rest == typed


def test_a_priority_word_is_skippable():
    tokens = read_tokens("Pay rent p1", frozenset({"priority"}))
    assert tokens.priority is None and tokens.rest == "Pay rent p1"


def test_p1_over_the_wire():
    c = _client()
    read = _parse(c, "Pay rent tomorrow p2")
    assert read["priority"] == "high" and read["title"] == "Pay rent"


@pytest.mark.parametrize("typed", ["'Call plumber tomorrow !! /Reno", '"Call plumber tomorrow !! /Reno"',
                                   "  'Call plumber tomorrow !! /Reno"])
def test_literal_escape_reads_nothing(typed):
    read = _parse(_client(), typed)
    assert read["title"] == "Call plumber tomorrow !! /Reno"
    assert (read["due_date"], read["priority"], read["project"], read["project_question"], read["budget"]) == (
        None, None, None, None, None)
    assert read["ready"] is True and read["warnings"] == []


def test_literal_escape_of_nothing_is_not_ready():
    c = _client()
    assert _parse(c, "'")["ready"] is False
    assert _parse(c, '""')["ready"] is False


def test_a_quote_only_at_the_start_is_not_an_escape():
    read = _parse(_client(), '"Call" plumber tomorrow')
    assert read["due_date"] is not None


def test_literal_escape_keeps_a_project_pages_own_project():
    c = _client()
    project = c.post("/api/projects", json={"name": "Reno"}, headers=O).json()
    read = _parse(c, "'buy tiles !!", project_id=project["id"])
    assert read["project"]["id"] == project["id"] and read["title"] == "buy tiles !!"


@pytest.mark.parametrize(("line", "skip", "words"), [
    ("Call Ana tomorrow at 9", "date", "tomorrow at 9"),
    ("Pay rent p1", "priority", "p1"),
    ("Pay rent !!", "priority", "!!"),
    ("Send invoice *", "star", "*"),
    ("Paint wall ~2h", "estimate", "~2h"),
    ("Call Ana tomorrow ^30m before", "reminder", "^30m before"),
    ("Water plants every Monday", "repeat", "every Monday"),
    ("Order tiles /Reno", "project", "/Reno"),
    ("Plumber €200 /Reno", "budget", "€200"),
    ("Book flights @Scout", "assignee", "@Scout"),
])
def test_a_removed_chip_puts_its_words_back_in_the_title(line, skip, words):
    c = _client()
    c.post("/api/projects", json={"name": "Reno"}, headers=O)
    c.post("/api/bots", json={"name": "Scout", "job": "helps", "instructions": "",
                              "avatar": {"shape": "round", "color": "#22c55e", "badge": "none"}}, headers=O)
    read = _parse(c, line, skip=[skip])
    assert words in read["title"]
