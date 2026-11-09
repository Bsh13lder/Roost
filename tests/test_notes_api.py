"""Notes over HTTP (the Board's Notes tab, M2 D4) and the notes_changed frame."""

from __future__ import annotations

import sqlite3

import httpx
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _frames() -> list[str]:
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        return [row[0] for row in con.execute("SELECT kind FROM events ORDER BY seq")]
    finally:
        con.close()


def test_create_search_read_save_and_delete():
    c = _client()
    garden = c.post("/api/notes", json={"title": "Garden", "content": "roses"}, headers=O).json()
    created = c.post("/api/notes", json={"content": "# Ana\nBirthday 3 May. Likes #orchids, see [[Garden]] and [[Lisbon]]."},
                     headers=O)
    assert created.status_code == 201
    ana = created.json()
    assert (ana["title"], ana["tags"], ana["revision"], ana["tainted"]) == ("Ana", ["orchids"], 1, False)
    assert ana["links"] == [{"target": "garden", "title": "Garden", "note_id": garden["id"]},
                            {"target": "lisbon", "title": "Lisbon", "note_id": None}]
    [hit] = c.get("/api/notes", params={"q": "ORCHIDS"}).json()
    assert hit["id"] == ana["id"] and "orchids" in hit["snippet"] and "content" not in hit
    saved = c.put(f"/api/notes/{ana['id']}", json={"base_revision": 1, "content": "# Ana\nLikes #roses"}, headers=O)
    assert (saved.json()["revision"], saved.json()["tags"]) == (2, ["orchids", "roses"])
    assert c.delete(f"/api/notes/{ana['id']}", headers=O).status_code == 204
    assert c.get(f"/api/notes/{ana['id']}").status_code == 404


def test_an_empty_tag_query_param_is_not_a_filter():
    """GET /api/notes?tag= (every field present) must still list the user's
    notes, not hide them (M2 Task 1 review, finding #1)."""
    c = _client()
    c.post("/api/notes", json={"title": "Ana", "content": "likes orchids"}, headers=O)
    assert len(c.get("/api/notes", params={"tag": ""}).json()) == 1
    assert len(c.get("/api/notes", params={"tag": "#"}).json()) == 1


def test_a_stale_note_save_is_409_with_the_current_note():
    c = _client()
    note = c.post("/api/notes", json={"title": "List", "content": "eggs"}, headers=O).json()
    assert c.put(f"/api/notes/{note['id']}", json={"base_revision": 1, "content": "eggs, milk"}, headers=O).status_code == 200
    stale = c.put(f"/api/notes/{note['id']}", json={"base_revision": 1, "content": "eggs, bread"}, headers=O)
    assert stale.status_code == 409
    assert (stale.json()["current"]["content"], stale.json()["current"]["revision"]) == ("eggs, milk", 2)
    assert c.get(f"/api/notes/{note['id']}").json()["content"] == "eggs, milk"


def test_every_change_publishes_notes_changed():
    c = _client()
    note = c.post("/api/notes", json={"title": "A", "content": "x"}, headers=O).json()
    c.put(f"/api/notes/{note['id']}", json={"base_revision": 1, "title": "B"}, headers=O)
    c.delete(f"/api/notes/{note['id']}", headers=O)
    assert _frames().count("notes_changed") == 3


def test_a_note_needs_a_title_or_text_and_stays_under_the_limit():
    c = _client()
    assert c.post("/api/notes", json={"content": ""}, headers=O).status_code == 422
    assert c.post("/api/notes", json={"content": "x" * 100_001}, headers=O).status_code == 422
    assert c.post("/api/notes", json={"title": "Untitled note"}, headers=O).status_code == 201


def test_mutations_need_the_origin_and_a_login():
    c = _client()
    assert c.post("/api/notes", json={"content": "x"}, headers={"Origin": "http://evil.example"}).status_code == 403
    assert TestClient(create_app()).get("/api/notes").status_code == 401


async def test_another_users_note_is_404():
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    for name in ("alice", "bob"):
        await register_user(cfg, name, "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        note = (await alice.post("/api/notes", json={"content": "mine"}, headers=O)).json()
        assert (await bob.get(f"/api/notes/{note['id']}")).status_code == 404
        assert (await bob.put(f"/api/notes/{note['id']}", json={"base_revision": 1, "content": "x"}, headers=O)).status_code == 404
        assert (await bob.delete(f"/api/notes/{note['id']}", headers=O)).status_code == 404
        assert (await bob.get("/api/notes")).json() == []


async def test_keep_vouches_for_a_web_made_note():
    from roost.notes.models import NoteDraft
    from roost.notes.store import NoteStore

    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    note = await NoteStore(cfg).create(alice_id, NoteDraft(title="Recipe", content="bake"), created_by_bot=None,
                                       tainted=True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice:
        await alice.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
        kept = await alice.post(f"/api/notes/{note.id}/keep", headers=O)
        assert (kept.status_code, kept.json()["tainted"]) == (200, False)


async def test_a_note_links_to_a_project_without_a_new_revision():
    """Hub H12: a note joins a project when it is created, or later through
    PUT …/project. The link keeps the revision, so an open editor's next save
    still lands, and null unlinks. ?project_id= lists only that project's
    notes. Each link publishes notes_changed "updated"."""
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as alice:
        await alice.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
        house = (await alice.post("/api/projects", json={"name": "House"}, headers=O)).json()
        ideas = await alice.post("/api/notes", json={"title": "Ideas", "content": "green tiles",
                                                     "project_id": house["id"]}, headers=O)
        loose = (await alice.post("/api/notes", json={"title": "Loose", "content": "eggs"}, headers=O)).json()
        filtered = (await alice.get("/api/notes", params={"project_id": house["id"]})).json()
        linked = await alice.put(f"/api/notes/{loose['id']}/project", json={"project_id": house["id"]}, headers=O)
        saved = await alice.put(f"/api/notes/{loose['id']}", json={"base_revision": 1, "content": "eggs, milk"},
                                headers=O)
        unlinked = await alice.put(f"/api/notes/{ideas.json()['id']}/project", json={"project_id": None}, headers=O)
        after = (await alice.get("/api/notes", params={"project_id": house["id"]})).json()
        unknown = await alice.put(f"/api/notes/{loose['id']}/project", json={"project_id": "no-such-project"},
                                  headers=O)
        empty = await alice.put(f"/api/notes/{loose['id']}/project", json={}, headers=O)
        frames = await app.state.events.since(alice_id, 0)
    assert (ideas.status_code, ideas.json()["project_id"], loose["project_id"]) == (201, house["id"], None)
    assert [(n["id"], n["project_id"]) for n in filtered] == [(ideas.json()["id"], house["id"])]
    assert (linked.status_code, linked.json()["project_id"], linked.json()["revision"]) == (200, house["id"], 1)
    assert (saved.status_code, saved.json()["revision"], saved.json()["project_id"]) == (200, 2, house["id"])
    assert (unlinked.json()["project_id"], [n["id"] for n in after]) == (None, [loose["id"]])
    assert (unknown.status_code, unknown.json()["detail"]) == (422, "No such project.")
    assert empty.status_code == 422
    updates = [f["note_id"] for f in frames if f["type"] == "notes_changed" and f["change"] == "updated"]
    assert updates == [loose["id"], loose["id"], ideas.json()["id"]]


async def test_a_note_cannot_link_to_another_users_project_or_be_linked_by_them():
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    for name in ("alice", "bob"):
        await register_user(cfg, name, "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        house = (await alice.post("/api/projects", json={"name": "House"}, headers=O)).json()
        shed = (await bob.post("/api/projects", json={"name": "Shed"}, headers=O)).json()
        note = (await alice.post("/api/notes", json={"content": "mine"}, headers=O)).json()
        link = f"/api/notes/{note['id']}/project"
        created = await alice.post("/api/notes", json={"content": "x", "project_id": shed["id"]}, headers=O)
        assert (created.status_code, created.json()["detail"]) == (422, "No such project.")
        assert (await alice.put(link, json={"project_id": shed["id"]}, headers=O)).status_code == 422
        assert (await bob.put(link, json={"project_id": shed["id"]}, headers=O)).status_code == 404
        assert (await bob.get("/api/notes", params={"project_id": house["id"]})).json() == []
        evil = {"Origin": "http://evil.example"}
        assert (await alice.put(link, json={"project_id": house["id"]}, headers=evil)).status_code == 403
        assert (await alice.get(f"/api/notes/{note['id']}")).json()["project_id"] is None


def test_a_link_that_meets_two_saves_is_409_with_the_current_note(monkeypatch):
    """Task 5: NoteStore.set_project raises RevisionConflict only when two saves
    land during one link. The route answers like a stale save: 409 with the
    current note."""
    from roost.gateway.routes.notes import NOTE_CONFLICT_TEXT
    from roost.records.revision import RevisionConflict

    app = create_app()
    c = TestClient(app)
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    house = c.post("/api/projects", json={"name": "House"}, headers=O).json()
    note = c.post("/api/notes", json={"title": "List", "content": "eggs"}, headers=O).json()
    notes = app.state.notes

    async def two_saves(user_id: str, note_id: str, project_id: str | None):
        raise RevisionConflict(await notes.get(user_id, note_id))

    monkeypatch.setattr(notes, "set_project", two_saves)
    clash = c.put(f"/api/notes/{note['id']}/project", json={"project_id": house["id"]}, headers=O)
    assert (clash.status_code, clash.json()["detail"]) == (409, NOTE_CONFLICT_TEXT)
    assert (clash.json()["current"]["id"], clash.json()["current"]["revision"]) == (note["id"], 1)
