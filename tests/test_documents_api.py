"""Documents over HTTP (the Board's Documents tab, M2 D2/D4) and documents_changed."""

from __future__ import annotations

import io
import json
import sqlite3

import httpx
import pdfplumber.page
from fastapi.testclient import TestClient
from pypdf import PdfWriter

import roost.gateway.routes.documents as documents_routes
from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.documents import pdf_ops
from roost.documents.models import DocumentDraft
from roost.documents.store import DocumentStore
from roost.gateway.app import create_app
from roost.gateway.auth import register_user

O = {"Origin": "http://127.0.0.1:18800"}
PDF = {**O, "Content-Type": "application/pdf"}


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


def _new_doc(c: TestClient, title: str = "My tasks", markdown: str = "# My tasks\n\n- Call the dentist") -> dict:
    created = c.post("/api/documents", json={"kind": "doc", "title": title, "markdown": markdown}, headers=O)
    assert created.status_code == 201
    return created.json()


def test_a_doc_from_markdown_reads_back_saves_and_deletes():
    c = _client()
    doc = _new_doc(c)
    assert (doc["kind"], doc["title"], doc["revision"], doc["tainted"], doc["pages"]) == ("doc", "My tasks", 1, False, None)
    assert "- Call the dentist" in c.get(f"/api/documents/{doc['id']}/text").json()["text"]
    detail = c.get(f"/api/documents/{doc['id']}").json()
    assert detail["payload"]["body"]["dataStream"].startswith("My tasks")
    body = {"dataStream": "Edited\r\n", "paragraphs": [{"startIndex": 6}], "textRuns": [],
            "sectionBreaks": [{"startIndex": 7}]}
    saved = c.put(f"/api/documents/{doc['id']}", json={"base_revision": 1, "payload": {**detail["payload"], "body": body}},
                  headers=O)
    assert saved.status_code == 200 and saved.json()["revision"] == 2
    assert c.get(f"/api/documents/{doc['id']}/text").json()["text"] == "Edited"
    assert c.delete(f"/api/documents/{doc['id']}", headers=O).status_code == 204
    assert c.get(f"/api/documents/{doc['id']}").status_code == 404


def test_a_sheet_from_rows_lists_with_its_kind():
    c = _client()
    sheet = c.post("/api/documents", json={"kind": "sheet", "title": "October expenses",
                                           "rows": [["Date", "Amount"], ["2026-10-03", 12.5]]}, headers=O).json()
    assert [d["title"] for d in c.get("/api/documents", params={"kind": "sheet"}).json()] == ["October expenses"]
    assert c.get("/api/documents", params={"kind": "doc"}).json() == []
    assert "12.5" in c.get(f"/api/documents/{sheet['id']}/text").json()["text"]


def test_a_sheet_with_nan_like_text_stores_it_as_text_and_reads_back():
    """Fix round 1, finding 1: a cell like "Nan" used to become float('nan'),
    and the GET response's json.dumps (Starlette's allow_nan=False) then
    raised — a 500, so the Board could never open the sheet. "Nan" must stay
    the string "Nan", and the GET must succeed."""
    c = _client()
    sheet = c.post("/api/documents", json={"kind": "sheet", "title": "Birthdays",
                                           "rows": [["Nan", "08001", "+34600123456"]]}, headers=O).json()
    detail = c.get(f"/api/documents/{sheet['id']}")
    assert detail.status_code == 200
    [sheet_id] = detail.json()["payload"]["sheets"]
    cell_data = detail.json()["payload"]["sheets"][sheet_id]["cellData"]
    assert [cell_data["0"][str(col)]["v"] for col in range(3)] == ["Nan", "08001", "+34600123456"]


def test_a_stale_document_save_is_409_with_the_current_copy():
    c = _client()
    doc = _new_doc(c)
    assert c.put(f"/api/documents/{doc['id']}", json={"base_revision": 1, "title": "Second"}, headers=O).status_code == 200
    stale = c.put(f"/api/documents/{doc['id']}", json={"base_revision": 1, "title": "Third"}, headers=O)
    assert stale.status_code == 409
    current = stale.json()["current"]
    assert (current["title"], current["revision"]) == ("Second", 2) and "dataStream" in current["payload"]["body"]


def test_a_blank_title_save_answers_with_the_title_it_actually_stored():
    c = _client()
    doc = _new_doc(c)
    saved = c.put(f"/api/documents/{doc['id']}", json={"base_revision": 1, "title": " "}, headers=O)
    assert saved.status_code == 200 and (saved.json()["title"], saved.json()["revision"]) == ("", 2)
    assert c.get(f"/api/documents/{doc['id']}").json()["title"] == saved.json()["title"]


def test_saving_a_payload_of_the_wrong_kind_is_422():
    c = _client()
    doc = _new_doc(c)
    sheet = c.post("/api/documents", json={"kind": "sheet", "title": "S"}, headers=O).json()
    assert c.put(f"/api/documents/{doc['id']}", json={"base_revision": 1, "payload": {"sheets": {}}}, headers=O).status_code == 422
    assert c.put(f"/api/documents/{sheet['id']}", json={"base_revision": 1, "payload": {"body": {}}}, headers=O).status_code == 422
    assert c.put(f"/api/documents/{doc['id']}", json={"base_revision": 1}, headers=O).status_code == 422


def test_a_pdf_upload_is_marked_from_web_content_and_reads_back():
    c = _client()
    data = pdf_ops.generate_from_text("The deposit is two months' rent.", title="Lease")
    up = c.post("/api/documents/pdf", params={"title": "Lease"}, content=data, headers=PDF)
    assert up.status_code == 201
    pdf = up.json()
    assert (pdf["kind"], pdf["pages"], pdf["tainted"]) == ("pdf", 1, True)
    raw = c.get(f"/api/documents/{pdf['id']}/pdf")
    assert raw.headers["content-type"] == "application/pdf" and raw.content == data
    assert "two months" in c.get(f"/api/documents/{pdf['id']}/text").json()["text"]
    assert c.get(f"/api/documents/{pdf['id']}").json()["payload"] is None
    assert c.put(f"/api/documents/{pdf['id']}", json={"base_revision": 1, "payload": {"body": {}}}, headers=O).status_code == 422
    assert c.post(f"/api/documents/{pdf['id']}/keep", headers=O).json()["tainted"] is False


def test_pdf_upload_limits(monkeypatch):
    c = _client()
    data = pdf_ops.generate_from_text("x")
    text = {**O, "Content-Type": "text/plain"}
    assert c.post("/api/documents/pdf", params={"title": "x"}, content=data, headers=text).status_code == 415
    assert c.post("/api/documents/pdf", params={"title": "x"}, content=b"hello", headers=PDF).status_code == 422
    monkeypatch.setattr(documents_routes, "MAX_PDF_BYTES", 100)
    assert c.post("/api/documents/pdf", params={"title": "x"}, content=data, headers=PDF).status_code == 413
    assert c.get("/api/documents").json() == []


def test_a_long_pdf_is_read_only_until_the_cap(monkeypatch):
    """A 200-page upload: /text reads the first pages, page by page, and stops at
    the cap. It never extracts all 200 pages (the gateway has mem_limit 1g)."""
    one = pdf_ops.generate_from_text("Clause. " * 300, title="Lease")   # about 2,400 characters
    writer = PdfWriter()
    for _ in range(200):
        writer.append(io.BytesIO(one), pages=(0, 1))
    buffer = io.BytesIO()
    writer.write(buffer)
    read: list[int] = []
    extract = pdfplumber.page.Page.extract_text

    def counted(page, *args, **kwargs):
        read.append(page.page_number)
        return extract(page, *args, **kwargs)

    monkeypatch.setattr(pdfplumber.page.Page, "extract_text", counted)
    c = _client()
    pdf = c.post("/api/documents/pdf", params={"title": "Lease"}, content=buffer.getvalue(), headers=PDF).json()
    assert pdf["pages"] == 200
    text = c.get(f"/api/documents/{pdf['id']}/text").json()["text"]
    assert 1 < len(read) <= 3 and read == sorted(read)
    assert text.startswith("Lease") and text.endswith("…(showing the start of a 200-page PDF)")


def test_a_sheet_payload_with_a_far_off_cell_is_422():
    c = _client()
    sheet = c.post("/api/documents", json={"kind": "sheet", "title": "S", "rows": [["a"]]}, headers=O).json()
    payload = c.get(f"/api/documents/{sheet['id']}").json()["payload"]
    [sheet_id] = payload["sheets"]
    far = {**payload, "sheets": {sheet_id: {**payload["sheets"][sheet_id], "cellData": {"9999998": {"0": {"v": 1}}}}}}
    saved = c.put(f"/api/documents/{sheet['id']}", json={"base_revision": 1, "payload": far}, headers=O)
    assert saved.status_code == 422 and "ZZ100000" in saved.json()["detail"]
    assert c.get(f"/api/documents/{sheet['id']}").json()["revision"] == 1


def test_a_sheet_payload_with_no_usable_worksheet_is_422():
    """Review Focus #5: a payload that passes the 'is a dict' and in-bounds
    checks but has no resolvable first worksheet (or a cell that isn't a
    dict) must still be 422 — not a 200 that every reader then crashes on."""
    c = _client()
    sheet = c.post("/api/documents", json={"kind": "sheet", "title": "S"}, headers=O).json()
    saved = c.put(f"/api/documents/{sheet['id']}", json={"base_revision": 1, "payload": {"sheets": {}}}, headers=O)
    assert saved.status_code == 422
    assert c.get(f"/api/documents/{sheet['id']}").json()["revision"] == 1


async def test_a_malformed_stored_sheet_reads_as_a_plain_422_not_a_crash():
    """A sheet with no usable worksheet in the DB — however it got there —
    must read as a plain 422 on /text, not a 500: render.document_text
    backstops the harvested readers' KeyError/AttributeError."""
    cfg = load_config()
    await init_db(cfg)
    user = await register_user(cfg, "alice", "pw-123456")
    meta = await DocumentStore(cfg).create(
        user.id, DocumentDraft(kind="sheet", title="Bad", body=json.dumps({"sheets": {}})),
        created_by_bot=None, tainted=False,
    )
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as client:
        await client.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
        resp = await client.get(f"/api/documents/{meta.id}/text")
        assert resp.status_code == 422 and "could not be read" in resp.json()["detail"]


def test_a_damaged_blob_is_a_plain_422():
    c = _client()
    doc = _new_doc(c)
    assert c.get(f"/api/documents/{doc['id']}/pdf").status_code == 404
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        con.execute("UPDATE documents SET payload = 'enc:v2:AAAA:BBBB'")
        con.commit()
    finally:
        con.close()
    broken = c.get(f"/api/documents/{doc['id']}")
    assert broken.status_code == 422 and "could not be read" in broken.json()["detail"]
    assert c.get(f"/api/documents/{doc['id']}/text").status_code == 422


def test_every_change_publishes_documents_changed():
    c = _client()
    doc = _new_doc(c)
    c.put(f"/api/documents/{doc['id']}", json={"base_revision": 1, "title": "B"}, headers=O)
    c.delete(f"/api/documents/{doc['id']}", headers=O)
    assert _frames().count("documents_changed") == 3


def test_mutations_need_the_origin_and_a_login():
    c = _client()
    evil = {"Origin": "http://evil.example"}
    assert c.post("/api/documents", json={"kind": "doc", "title": "x"}, headers=evil).status_code == 403
    assert TestClient(create_app()).get("/api/documents").status_code == 401


async def test_another_users_document_is_404():
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
        doc = (await alice.post("/api/documents", json={"kind": "doc", "title": "mine"}, headers=O)).json()
        for path in (f"/api/documents/{doc['id']}", f"/api/documents/{doc['id']}/text"):
            assert (await bob.get(path)).status_code == 404
        assert (await bob.put(f"/api/documents/{doc['id']}", json={"base_revision": 1, "title": "x"}, headers=O)).status_code == 404
        assert (await bob.delete(f"/api/documents/{doc['id']}", headers=O)).status_code == 404
        assert (await bob.get("/api/documents")).json() == []


async def test_a_document_links_to_a_project_without_a_new_revision():
    """Hub H12: a doc or sheet joins a project when it is created, or later
    through PUT …/project. The link keeps the revision, so an open editor's
    next autosave still lands, and null unlinks. ?project_id= filters, with or
    without ?kind=. Each link publishes documents_changed "updated"."""
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as alice:
        await alice.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
        house = (await alice.post("/api/projects", json={"name": "House"}, headers=O)).json()
        link = {"project_id": house["id"]}
        plan = await alice.post("/api/documents", json={"kind": "doc", "title": "Plan", **link}, headers=O)
        costs = (await alice.post("/api/documents", json={"kind": "sheet", "title": "Costs",
                                                          "rows": [["Tiles", 40]], **link}, headers=O)).json()
        loose = (await alice.post("/api/documents", json={"kind": "doc", "title": "Loose"}, headers=O)).json()
        listed = (await alice.get("/api/documents", params=link)).json()
        sheets = (await alice.get("/api/documents", params={"kind": "sheet", **link})).json()
        linked = await alice.put(f"/api/documents/{loose['id']}/project", json=link, headers=O)
        saved = await alice.put(f"/api/documents/{loose['id']}", json={"base_revision": 1, "title": "Loose plan"},
                                headers=O)
        unlinked = await alice.put(f"/api/documents/{plan.json()['id']}/project", json={"project_id": None},
                                   headers=O)
        unknown = await alice.put(f"/api/documents/{loose['id']}/project", json={"project_id": "no-such-project"},
                                  headers=O)
        frames = await app.state.events.since(alice_id, 0)
    assert (plan.status_code, plan.json()["project_id"], loose["project_id"]) == (201, house["id"], None)
    assert {d["id"] for d in listed} == {plan.json()["id"], costs["id"]}
    assert [d["id"] for d in sheets] == [costs["id"]]
    assert (linked.status_code, linked.json()["project_id"], linked.json()["revision"]) == (200, house["id"], 1)
    assert (saved.status_code, saved.json()["revision"]) == (200, 2)
    assert unlinked.json()["project_id"] is None
    assert (unknown.status_code, unknown.json()["detail"]) == (422, "No such project.")
    updates = [f["document_id"] for f in frames if f["type"] == "documents_changed" and f["change"] == "updated"]
    assert updates == [loose["id"], loose["id"], plan.json()["id"]]


async def test_a_document_cannot_link_to_another_users_project_or_be_linked_by_them():
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
        doc = (await alice.post("/api/documents", json={"kind": "doc", "title": "mine"}, headers=O)).json()
        link = f"/api/documents/{doc['id']}/project"
        created = await alice.post("/api/documents", json={"kind": "doc", "title": "x", "project_id": shed["id"]},
                                   headers=O)
        assert (created.status_code, created.json()["detail"]) == (422, "No such project.")
        assert (await alice.put(link, json={"project_id": shed["id"]}, headers=O)).status_code == 422
        assert (await bob.put(link, json={"project_id": shed["id"]}, headers=O)).status_code == 404
        assert (await bob.get("/api/documents", params={"project_id": house["id"]})).json() == []
        evil = {"Origin": "http://evil.example"}
        assert (await alice.put(link, json={"project_id": house["id"]}, headers=evil)).status_code == 403
        assert (await alice.get(f"/api/documents/{doc['id']}")).json()["project_id"] is None
