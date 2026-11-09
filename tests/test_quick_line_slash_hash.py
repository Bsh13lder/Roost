"""`/Project` is the project and `#tag` is a tag (user ruling 2026-10-20). `#Project` no longer picks one."""

from __future__ import annotations

from fastapi.testclient import TestClient

from roost.gateway.app import create_app

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _project(c: TestClient, name: str) -> dict:
    made = c.post("/api/projects", json={"name": name}, headers=O)
    assert made.status_code in (200, 201), made.text
    return made.json()


def _parse(c: TestClient, text: str, **fields) -> dict:
    read = c.post("/api/tasks/parse", json={"text": text, **fields}, headers=O)
    assert read.status_code == 200, read.text
    return read.json()


def test_slash_picks_the_project():
    c = _client()
    reno = _project(c, "Renovation")
    read = _parse(c, "Order tiles /Renovation €200")
    assert read["project"]["id"] == reno["id"] and read["title"] == "Order tiles" and read["budget"] == "200.00"
    assert read["project_words"] == "/Renovation" and read["tags"] == []


def test_slash_is_case_insensitive_and_takes_a_unique_start():
    c = _client()
    reno = _project(c, "Renovation")
    assert _parse(c, "Tiles /renovation")["project"]["id"] == reno["id"]
    assert _parse(c, "Tiles /Reno")["project"]["id"] == reno["id"]


def test_slash_takes_the_longest_multi_word_name():
    c = _client()
    _project(c, "Casa")
    nueva = _project(c, "Casa Nueva")
    read = _parse(c, "Pintar /Casa Nueva €20 mañana")
    assert read["project"]["id"] == nueva["id"] and read["title"] == "Pintar"


def test_slash_with_no_such_project_asks_and_never_creates():
    c = _client()
    _project(c, "Renovation")
    read = _parse(c, "Tiles /Renovaton")
    assert read["project"] is None and read["ready"] is False and "Renovation" in read["project_question"]
    assert len(c.get("/api/projects", headers=O).json()) == 1        # only Renovation: nothing was made


def test_hash_no_longer_picks_a_project():
    c = _client()
    _project(c, "Renovation")
    read = _parse(c, "Order tiles #Renovation")
    assert read["project"] is None and read["project_words"] is None and read["project_question"] is None
    assert read["tags"] == ["Renovation"] and read["title"] == "Order tiles" and read["ready"] is True


def test_hash_tags():
    c = _client()
    read = _parse(c, "Buy milk #shopping #home-life #Shopping tomorrow")
    assert read["tags"] == ["shopping", "home-life"] and read["title"] == "Buy milk" and read["due_date"]
    assert read["warnings"] == []


def test_a_hash_that_is_not_a_tag_stays_in_the_title():
    c = _client()
    for text in ("Fix issue #123", "Use C# today", "Press # key", "Mail a#b"):
        read = _parse(c, text)
        assert read["tags"] == [] and "#" in read["title"], text


def test_too_long_or_too_many_tags():
    c = _client()
    long = "#" + "a" * 41
    read = _parse(c, f"Thing {long}")
    assert read["tags"] == [] and long in read["title"] and read["warnings"]
    many = " ".join(f"#t{n}" for n in range(22))
    read = _parse(c, f"Thing {many}")
    assert len(read["tags"]) == 20 and read["warnings"]


def test_removed_chips_keep_their_words():
    c = _client()
    _project(c, "Renovation")
    assert "#shopping" in _parse(c, "Buy milk #shopping", skip=["tag"])["title"]
    read = _parse(c, "Buy milk /Renovation", skip=["project"])
    assert read["project"] is None and "/Renovation" in read["title"]


def test_a_short_day_never_beats_a_project_or_tag():
    c = _client()
    sat = _project(c, "Sat")
    trip = _project(c, "Mon Trip")
    read = _parse(c, "Plan /Sat")
    assert read["project"]["id"] == sat["id"] and read["due_date"] is None and read["title"] == "Plan"
    read = _parse(c, "Plan /Mon Trip")
    assert read["project"]["id"] == trip["id"] and read["due_date"] is None
    read = _parse(c, "Plan #tom #mon")
    assert read["tags"] == ["tom", "mon"] and read["due_date"] is None and read["title"] == "Plan"


def test_a_project_pages_own_project_and_a_slash_in_a_date():
    c = _client()
    reno = _project(c, "Renovation")
    read = _parse(c, "Tiles 5/3 #diy", project_id=reno["id"])
    assert read["project"]["id"] == reno["id"] and read["tags"] == ["diy"] and read["due_date"]


def test_tags_are_stored_with_the_task():
    c = _client()
    made = c.post("/api/tasks", json={"title": "Milk", "tags": ["shopping", "home"]}, headers=O)
    assert made.status_code in (200, 201), made.text
    assert made.json()["tags"] == ["shopping", "home"]
    assert c.post("/api/tasks", json={"title": "x", "tags": ["a" * 41]}, headers=O).status_code == 422
    assert c.post("/api/tasks", json={"title": "x", "tags": ["t"] * 21}, headers=O).status_code == 422


def test_a_pasted_list_carries_tags():
    c = _client()
    body = c.post("/api/tasks/parse-many", json={"text": "Milk #shopping\nEggs"}, headers=O).json()
    assert body["tasks"][0]["tags"] == ["shopping"] and body["tasks"][1]["tags"] == []
