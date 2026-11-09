"""The Obsidian export over HTTP: settings, the project switch, Export now, ownership."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest
from fastapi import FastAPI

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.mac.grants import GrantStore
from roost.mac.models import GrantDraft
from roost.money.models import ProjectDraft
from roost.money.project_store import ProjectStore

ORIGIN = {"Origin": "http://127.0.0.1:18800"}
EVIL = {"Origin": "http://evil.example"}


@dataclass(frozen=True)
class Rig:
    app: FastAPI
    alice_id: str
    bob_id: str
    alice: httpx.AsyncClient
    bob: httpx.AsyncClient


@pytest.fixture
async def rig():
    cfg = load_config()
    await init_db(cfg)
    app = create_app()
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    bob_id = (await register_user(cfg, "bob", "pw-123456")).id
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            login = await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"},
                                      headers=ORIGIN)
            assert login.status_code == 200
        yield Rig(app, alice_id, bob_id, alice, bob)


async def _folder(rig: Rig, user_id: str, access: str = "read_write"):
    cfg = rig.app.state.config
    files = rig.app.state.mac_files
    files.replace_tree({"Vault/": ""})
    grant = await GrantStore(cfg).create(user_id, GrantDraft(None, f"{cfg.mac_home.resolve()}/Vault", "Vault", access,
                                                             "ask_each", True))
    await files.push_grants(await GrantStore(cfg).all_live())
    return grant


async def _project(rig: Rig, user_id: str, name: str = "Garden"):
    return await ProjectStore(rig.app.state.config).create(user_id, ProjectDraft(name=name), created_by_bot=None,
                                                           tainted=False)


async def test_settings_start_off_and_list_only_writable_folders(rig):
    await _folder(rig, rig.alice_id)
    await _folder(rig, rig.alice_id, access="read")
    got = (await rig.alice.get("/api/vault-export")).json()
    assert (got["grant_id"], got["journals"], got["projects"]) == (None, False, [])
    assert [g["label"] for g in got["grants"]] == ["Vault"] and got["last"]["result"] is None


async def test_choose_a_folder_switch_a_project_and_export_now(rig):
    grant = await _folder(rig, rig.alice_id)
    project = await _project(rig, rig.alice_id)
    put = await rig.alice.put("/api/vault-export", json={"grant_id": grant.id, "journals": True}, headers=ORIGIN)
    assert put.status_code == 200 and (put.json()["grant_id"], put.json()["journals"]) == (grant.id, True)
    switched = await rig.alice.put(f"/api/projects/{project.id}/vault-export", json={"on": True}, headers=ORIGIN)
    assert switched.json() == {"project_id": project.id, "on": True}
    ran = (await rig.alice.post("/api/vault-export/run", headers=ORIGIN)).json()
    assert ran == {"result": "ok", "written": 2, "conflicts": 0, "failed": 0}
    files = rig.app.state.mac_files._tree
    assert "Vault/Roost/Projects/Garden/Garden.md" in files and "Vault/Roost/Projects/Garden/Garden · Money.md" in files
    last = (await rig.alice.get("/api/vault-export")).json()
    assert last["projects"] == [project.id] and last["last"]["result"] == "ok" and last["last"]["written"] == 2


async def test_a_read_only_or_someone_elses_folder_is_refused(rig):
    read_only = await _folder(rig, rig.alice_id, access="read")
    bobs = await _folder(rig, rig.bob_id)
    for grant_id in (read_only.id, bobs.id, "nope"):
        put = await rig.alice.put("/api/vault-export", json={"grant_id": grant_id}, headers=ORIGIN)
        assert put.status_code == 422


async def test_someone_elses_project_is_404_and_writes_need_the_origin(rig):
    bobs = await _project(rig, rig.bob_id)
    assert (await rig.alice.put(f"/api/projects/{bobs.id}/vault-export", json={"on": True},
                                headers=ORIGIN)).status_code == 404
    assert (await rig.bob.get("/api/vault-export")).json()["projects"] == []
    assert (await rig.alice.put("/api/vault-export", json={}, headers=EVIL)).status_code == 403
    assert (await rig.alice.post("/api/vault-export/run", headers=EVIL)).status_code == 403


async def test_export_now_with_nothing_chosen_is_off(rig):
    assert (await rig.alice.post("/api/vault-export/run", headers=ORIGIN)).json()["result"] == "off"
