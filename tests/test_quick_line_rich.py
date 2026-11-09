"""The quick line reads everything (design 2026-10-20 §3): star, estimate, reminder, repeat and @bot."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from fastapi.testclient import TestClient

from roost.gateway.app import create_app
from tz_helpers import MADRID_TZ

O = {"Origin": "http://127.0.0.1:18800"}
AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _bot(c: TestClient, name: str) -> dict:
    return c.post("/api/bots", json={"name": name, "job": "helps", "instructions": "", "avatar": AVATAR},
                  headers=O).json()


def _parse(c: TestClient, text: str, **fields) -> dict:
    read = c.post("/api/tasks/parse", json={"text": text, **fields}, headers=O)
    assert read.status_code == 200, read.text
    return read.json()


def _tomorrow_at(hour: int) -> datetime:
    return datetime.combine(datetime.now(MADRID_TZ).date() + timedelta(days=1), time(hour, 0), tzinfo=MADRID_TZ)


def test_the_whole_rich_line():
    c = _client()
    project = c.post("/api/projects", json={"name": "Renovation"}, headers=O).json()
    scout = _bot(c, "Scout")
    read = _parse(c, "Call plumber tomorrow at 9 /Renovation €200 !! * ~1h ^30m before every Monday @Scout")
    nine = _tomorrow_at(9)
    assert read["title"] == "Call plumber"
    assert (read["priority"], read["starred"], read["estimate_minutes"]) == ("high", True, 60)
    assert read["project"]["id"] == project["id"] and read["budget"] == "200.00"
    assert read["due_date"] == nine.isoformat()
    assert read["reminder_at"] == (nine - timedelta(minutes=30)).astimezone(timezone.utc).isoformat()
    assert read["reminder_words"] == "^30m before"
    assert (read["recurring"], read["repeat_words"], read["repeat_text"], read["repeat_problem"]) == (
        "0 9 * * 1", "every Monday", "every Monday 09:00", None)
    assert read["assignee"] == {"id": scout["id"], "name": "Scout"} and read["assignee_words"] == "@Scout"
    assert (read["assignee_question"], read["warnings"], read["ready"]) == (None, [], True)


def test_spanish_rich_line():
    c = _client()
    project = c.post("/api/projects", json={"name": "Reforma"}, headers=O).json()
    scout = _bot(c, "Scout")
    read = _parse(c, "Llamar al fontanero mañana a las 9 /Reforma 200€ !alta * ~1,5h recuérdame 1h antes "
                     "todos los lunes y jueves @scout")
    assert read["title"] == "Llamar al fontanero"
    assert (read["priority"], read["starred"], read["estimate_minutes"]) == ("high", True, 90)
    assert (read["project"]["id"], read["budget"]) == (project["id"], "200.00")
    assert read["recurring"] == "0 9 * * 1,4" and read["assignee"]["id"] == scout["id"]
    assert read["due_date"] == _tomorrow_at(9).isoformat()


def test_skip_puts_each_kind_back():
    c = _client()
    _bot(c, "Scout")
    text = "Call plumber * ~1h ^9am every Monday @Scout !high"
    full = _parse(c, text)
    assert full["title"] == "Call plumber"
    for kind, words in (("star", "*"), ("estimate", "~1h"), ("reminder", "^9am"), ("repeat", "every Monday"),
                        ("assignee", "@Scout"), ("priority", "!high")):
        read = _parse(c, text, skip=[kind])
        assert words in read["title"], kind
    kept = _parse(c, text, skip=["repeat"])
    assert (kept["recurring"], kept["repeat_words"]) == (None, None)
    assert _parse(c, text, skip=["assignee"])["assignee"] is None


def test_unknown_bot_is_a_question():
    c = _client()
    _bot(c, "Scout")
    read = _parse(c, "Call plumber @Nobody")
    assert read["assignee"] is None and read["assignee_words"] == "@Nobody"
    assert read["assignee_question"] == "No bot is called “Nobody”."
    assert (read["title"], read["ready"]) == ("Call plumber", False)
    assert _parse(c, "Call plumber @Nobody", skip=["assignee"])["ready"] is True


def test_bot_names_match_whole_then_by_unique_prefix_and_may_have_spaces():
    c = _client()
    money = _bot(c, "Money Bot")
    _bot(c, "Scout")
    _bot(c, "Scooter")
    whole = _parse(c, "Pay rent @money bot soon")
    assert (whole["assignee"]["id"], whole["assignee_words"], whole["title"]) == (money["id"], "@money bot", "Pay rent soon")
    assert _parse(c, "Pay rent @mon")["assignee"]["id"] == money["id"]
    ambiguous = _parse(c, "Pay rent @sco")
    assert ambiguous["assignee"] is None and "sco" in ambiguous["assignee_question"] and ambiguous["ready"] is False
    assert _parse(c, "Mail a@b.com")["assignee"] is None            # an address is not a bot


def test_two_projects_last_wins_with_a_warning():
    c = _client()
    c.post("/api/projects", json={"name": "Alpha"}, headers=O)
    beta = c.post("/api/projects", json={"name": "Beta"}, headers=O).json()
    read = _parse(c, "Paint /Alpha /Beta")
    assert (read["project"]["id"], read["title"]) == (beta["id"], "Paint")
    assert read["warnings"] == ["Two projects: kept /Beta."]
    assert read["ready"] is True


def test_priority_warning_and_a_reminder_without_a_due():
    c = _client()
    read = _parse(c, "Dinner !high !low ^1h before")
    assert read["priority"] == "low" and read["title"] == "Dinner"
    assert read["warnings"][0] == "Two priorities: kept !low."
    assert "“^1h before” needs a due date." in read["warnings"]
    assert read["reminder_at"] is None and read["ready"] is True


def test_repeat_with_no_date_starts_on_the_first_occurrence():
    c = _client()
    read = _parse(c, "Water plants every Monday and Thursday at 7am")
    due = datetime.fromisoformat(read["due_date"])
    assert read["recurring"] == "0 7 * * 1,4" and read["title"] == "Water plants"
    assert due.weekday() in (0, 3) and (due.hour, due.minute) == (7, 0) and due > datetime.now(MADRID_TZ)
    assert due - datetime.now(MADRID_TZ) <= timedelta(days=7)
    dated = _parse(c, "Water plants tomorrow every Monday")
    assert dated["due_date"] == (datetime.now(MADRID_TZ).date() + timedelta(days=1)).isoformat()
    assert dated["recurring"] == "0 9 * * 1"


def test_an_unsayable_repeat_is_a_question_that_blocks():
    c = _client()
    read = _parse(c, "Clean the flat every other weekday")
    assert read["recurring"] is None and read["repeat_words"] == "every other weekday"
    assert read["repeat_problem"] and read["ready"] is False
    assert (read["title"], read["ready"]) == ("Clean the flat", False)
    back = _parse(c, "Clean the flat every other weekday", skip=["repeat"])
    assert back["title"] == "Clean the flat every other weekday" and back["ready"] is True


def test_priority_words_at_the_edges_and_amounts_with_thousands():
    c = _client()
    project = c.post("/api/projects", json={"name": "Reno"}, headers=O).json()
    read = _parse(c, "Pagar luz urgente mañana", project_id=project["id"])
    assert (read["priority"], read["title"]) == ("urgent", "Pagar luz")
    rent = _parse(c, "Pay 1.200€ rent /Reno")
    assert (rent["budget"], rent["title"]) == ("1200.00", "Pay rent")
