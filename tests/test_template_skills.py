"""Templates carry skills (Skills Task 7): Share includes the bot's on skills; importing asks before adding them."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from roost.bots.template_file import (
    SecretInTemplate, TemplateFileError, read_template_file, template_file_for,
)
from roost.constants import TEMPLATE_SKILLS_MAX
from roost.gateway.app import create_app
from roost.skills.template_skills import TemplateSkill, import_plan, skills_for_template
from test_template_file import _bot

O = {"Origin": "http://127.0.0.1:18800"}
SECRET = "sk-ant-abcdefghijklmnopqrstuv0123"


def _client(app=None) -> tuple[TestClient, str]:
    c = TestClient(app or create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c, c.get("/api/bots").json()[0]["id"]


def _skill(c, name, body="1. step"):
    r = c.post("/api/skills", json={"name": name, "use_when": f"use {name}", "body": body}, headers=O)
    assert r.status_code == 201, r.text
    return r.json()


def _file(**extra):
    base = {"format": "roost-bot", "version": 1, "name": "Scout", "job": "finds things", "instructions": "",
            "avatar": {"shape": "mochi", "color": "#22c55e"}}
    return base | extra


def _file_skill(name="Post on X", steps="1. Open X"):
    return {"name": name, "use_when": "posting", "steps": steps}


def test_share_includes_the_bots_on_skills():
    c, bot = _client()
    _skill(c, "Beta")
    alpha = _skill(c, "Alpha")
    off = _skill(c, "Gamma")
    c.put(f"/api/bots/{bot}/skills/{off['id']}", json={"on": False}, headers=O)
    shared = c.get(f"/api/bots/{bot}/template").json()
    assert shared["skills"] == [{"name": "Alpha", "use_when": "use Alpha", "steps": alpha["body"]},
                                {"name": "Beta", "use_when": "use Beta", "steps": "1. step"}]
    assert read_template_file(shared).skills[0].name == "Alpha"


def test_a_file_without_skills_reads_and_writes_as_before():
    c, bot = _client()
    shared = c.get(f"/api/bots/{bot}/template").json()
    assert "skills" not in shared
    assert "skills" not in template_file_for(_bot()).model_dump()
    assert read_template_file(_file()).skills == ()


def test_an_old_roost_file_still_reads():
    old = _file()
    parsed = read_template_file(old)
    assert parsed.name == "Scout" and parsed.skills == ()


def test_a_secret_in_a_skill_blocks_share():
    with pytest.raises(SecretInTemplate) as caught:
        template_file_for(_bot(), (TemplateSkill(name="Keys", use_when="always", steps=f"use {SECRET}"),))
    assert str(caught.value) == ("Not shared: an API key or token seems to be in the skill “Keys”. "
                                 "Remove it, then share again.")
    with pytest.raises(SecretInTemplate) as named:
        template_file_for(_bot(), (TemplateSkill(name=f"token={SECRET}", use_when="x", steps="y"),))
    assert SECRET not in str(named.value) and "skill 1" in str(named.value)
    c, bot = _client()
    _skill(c, "Keys")
    assert c.get(f"/api/bots/{bot}/template").status_code == 200


def test_check_returns_skills_and_writes_nothing():
    c, _ = _client()
    _skill(c, "Post on X")
    r = c.post("/api/templates/check", json={"file": _file(skills=[_file_skill("post on x"),
                                                                    _file_skill("Weekly SEO")])}, headers=O)
    assert r.status_code == 200, r.text
    assert r.json()["skills"] == [
        {"name": "post on x", "use_when": "posting", "body": "1. Open X", "have": True},
        {"name": "Weekly SEO", "use_when": "posting", "body": "1. Open X", "have": False}]
    assert [s["name"] for s in c.get("/api/skills").json()] == ["Post on X"]


def test_import_adds_ticked_skills_marked_from_outside():
    c, bot = _client()
    r = c.post("/api/skills/import", json={"skills": [_file_skill("Weekly SEO")], "bot_id": bot}, headers=O)
    assert r.status_code == 200, r.text
    [added] = r.json()["added"]
    assert (added["name"], added["origin"], added["tainted"], added["body"]) == ("Weekly SEO", "file", True,
                                                                                 "1. Open X")
    assert r.json()["have"] == []
    assert c.post("/api/skills/import", json={"skills": []}).status_code == 403
    assert c.post("/api/skills/import", json={"skills": [], "bot_id": "nope"}, headers=O).status_code == 404


def test_import_skips_names_you_have():
    c, _ = _client()
    _skill(c, "Post on X", body="mine")
    r = c.post("/api/skills/import", json={"skills": [_file_skill("POST ON X"), _file_skill("New one")]}, headers=O)
    assert [s["name"] for s in r.json()["added"]] == ["New one"] and r.json()["have"] == ["POST ON X"]
    assert c.get("/api/skills").json()[1]["body"] == "mine"


def test_import_refuses_a_secret_and_adds_nothing():
    c, _ = _client()
    r = c.post("/api/skills/import", json={"skills": [_file_skill("Fine"), _file_skill("Keys", f"use {SECRET}")]},
               headers=O)
    assert r.status_code == 422 and SECRET not in r.text and r.json()["detail"].startswith("Not saved")
    assert c.get("/api/skills").json() == []


def test_import_respects_the_cap(monkeypatch):
    monkeypatch.setattr("roost.skills.service.SKILLS_PER_USER_MAX", 2)
    c, _ = _client()
    _skill(c, "One")
    r = c.post("/api/skills/import", json={"skills": [_file_skill("Two"), _file_skill("Three")]}, headers=O)
    assert r.status_code == 422 and "Delete one to add another" in r.json()["detail"]
    assert len(c.get("/api/skills").json()) == 1


def test_too_many_skills_in_a_file_is_a_plain_error():
    many = [_file_skill(f"Skill {i}") for i in range(TEMPLATE_SKILLS_MAX + 1)]
    with pytest.raises(TemplateFileError) as caught:
        read_template_file(_file(skills=many))
    assert str(caught.value) == f"This file has more than {TEMPLATE_SKILLS_MAX} skills."
    with pytest.raises(TemplateFileError):
        read_template_file(_file(skills=[{"name": "x", "use_when": "y", "steps": "z", "run": "rm -rf"}]))


def test_the_plan_marks_duplicates_inside_the_file_too():
    lines = import_plan(["Have"], [TemplateSkill(name=n, use_when="w", steps="s") for n in ("have", "New", "new")])
    assert [line.state for line in lines] == ["have", "add", "have"]
    assert len(skills_for_template([])) == 0
