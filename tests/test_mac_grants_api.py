"""Grant Mac folders from Roost over HTTP (Task 7; Design §2): sealed, per user, per bot."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import AsyncIterator

import httpx
import pytest

from mac_helpers import BOT_A
from roost.config import load_config
from roost.constants import MAC_GRANTS_MAX
from roost.db.connection import db_session, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.mac.fake_files import FakeMacFiles
from roost.mac.texts import MAC_AWAY_TEXT
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}
PASSWORD = "pw-123456"
TREE = {"Notes/Tasks.md": "- one\n", "Docs/a.md": "doc", "Stuff/b.md": "b"}


@pytest.fixture
async def cfg(tmp_path: Path):
    tree = tmp_path / "tree.json"
    tree.write_text(json.dumps(TREE))
    config = replace(load_config(), fake_mac_tree=tree, mac_home=(tmp_path / "home"))
    await init_db(config)
    return config


@pytest.fixture
async def alice(cfg):
    return await register_user(cfg, "alice", PASSWORD)


@pytest.fixture
async def app(cfg, alice):
    return create_app(cfg)


@asynccontextmanager
async def _login(app, name: str) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        login = await client.post("/api/auth/login", json={"username": name, "password": PASSWORD}, headers=O)
        assert login.status_code == 200
        yield client


def _home(cfg) -> str:
    return str(cfg.mac_home)


def _body(cfg, folder: str, label: str, **extra) -> dict:
    return {"path": f"{_home(cfg)}/{folder}", "label": label, "access": "read_write",
            "read_policy": "ask_each", "bot_id": None, **extra}


async def test_add_a_grant_checks_it_at_the_keeper_and_stores_path_and_label_sealed(cfg, app, alice) -> None:
    bot = await make_bot(cfg, alice.id, "Mia")
    async with _login(app, "alice") as client:
        response = await client.post("/api/mac/grants", json=_body(cfg, "Notes", "MySpace", bot_id=bot.id), headers=O)
        assert response.status_code == 201
        out = response.json()
        assert set(out) == {"id", "bot_id", "label", "path", "access", "read_policy", "is_vault", "created_at"}
        assert out["path"] == f"{_home(cfg)}/Notes" and out["label"] == "MySpace" and out["bot_id"] == bot.id
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT path, label, access FROM mac_grants")).fetchone()
    assert row["path"].startswith("enc:v2") and row["label"].startswith("enc:v2") and row["access"] == "read_write"
    raw = json.dumps([row["path"], row["label"]])
    assert "Notes" not in raw and "MySpace" not in raw
    pushed = app.state.mac_files.grants
    assert [(g.label, g.path) for g in pushed] == [("MySpace", f"{_home(cfg)}/Notes")]


async def test_labels_are_unique_per_user_and_capped(cfg, app, alice) -> None:
    async with _login(app, "alice") as client:
        assert (await client.post("/api/mac/grants", json=_body(cfg, "Notes", "MySpace"), headers=O)).status_code == 201
        dup = await client.post("/api/mac/grants", json=_body(cfg, "Docs", "myspace"), headers=O)
        assert dup.status_code == 422 and "MySpace".casefold() in dup.json()["detail"].casefold()
        for bad in ("", "   ", "x" * 41):
            assert (await client.post("/api/mac/grants", json=_body(cfg, "Docs", bad), headers=O)).status_code == 422
        assert (await client.post("/api/mac/grants", json=_body(cfg, "Docs", "Docs"), headers=O)).status_code == 201
        for i in range(MAC_GRANTS_MAX - 2):
            assert (await client.post("/api/mac/grants", json=_body(cfg, "Stuff", f"S{i}"), headers=O)).status_code == 201
        over = await client.post("/api/mac/grants", json=_body(cfg, "Stuff", "one too many"), headers=O)
        assert over.status_code == 422 and str(MAC_GRANTS_MAX) in over.json()["detail"]
        bad_field = await client.post("/api/mac/grants", json={**_body(cfg, "Docs", "Z"), "root": "/"}, headers=O)
        assert bad_field.status_code == 422


async def test_a_denied_or_missing_folder_is_422_in_plain_words(cfg, app, alice) -> None:
    async with _login(app, "alice") as client:
        denied = await client.post("/api/mac/grants", json=_body(cfg, "Library", "Lib"), headers=O)
        missing = await client.post("/api/mac/grants", json=_body(cfg, "Nope", "Nope"), headers=O)
        relative = await client.post("/api/mac/grants", json={**_body(cfg, "Notes", "Rel"), "path": "Notes"}, headers=O)
        assert denied.status_code == missing.status_code == relative.status_code == 422
        assert denied.json()["detail"] == "That folder is off limits."
        assert missing.json()["detail"] == "That folder doesn't exist."
        assert "folder" in relative.json()["detail"]
        assert (await client.get("/api/mac/grants")).json() == []
        app.state.mac_files.fail = True
        away = await client.post("/api/mac/grants", json=_body(cfg, "Notes", "Away"), headers=O)
        assert away.status_code == 503 and away.json()["detail"] == MAC_AWAY_TEXT


async def test_a_bot_sees_its_own_and_all_bots_grants_only(cfg, app, alice) -> None:
    one, two = await make_bot(cfg, alice.id, "One"), await make_bot(cfg, alice.id, "Two")
    async with _login(app, "alice") as client:
        for folder, label, bot in (("Notes", "Mine", one.id), ("Docs", "Everyone", None), ("Stuff", "Hers", two.id)):
            assert (await client.post("/api/mac/grants", json=_body(cfg, folder, label, bot_id=bot), headers=O)).status_code == 201
        for_one = (await client.get(f"/api/mac/grants?bot_id={one.id}")).json()
        assert sorted(g["label"] for g in for_one) == ["Everyone", "Mine"]
        assert sorted(g["label"] for g in (await client.get("/api/mac/grants")).json()) == ["Everyone", "Hers", "Mine"]
        assert (await client.get(f"/api/mac/grants?bot_id={BOT_A}")).status_code == 404


async def test_update_a_grant_and_revoke_pushes_the_new_set_at_once(cfg, app, alice) -> None:
    async with _login(app, "alice") as client:
        first = (await client.post("/api/mac/grants", json=_body(cfg, "Notes", "Notes"), headers=O)).json()
        second = (await client.post("/api/mac/grants", json=_body(cfg, "Docs", "Docs"), headers=O)).json()
        changed = await client.patch(f"/api/mac/grants/{first['id']}",
                                     json={"label": "Renamed", "access": "read", "read_policy": "ask_session"}, headers=O)
        assert changed.status_code == 200
        assert (changed.json()["label"], changed.json()["access"], changed.json()["read_policy"]) == ("Renamed", "read", "ask_session")
        assert app.state.mac_files.grants[0].access == "read"
        clash = await client.patch(f"/api/mac/grants/{first['id']}", json={"label": "docs"}, headers=O)
        assert clash.status_code == 422
        assert (await client.patch(f"/api/mac/grants/{first['id']}", json={"path": "/etc"}, headers=O)).status_code == 422
        pushes = app.state.mac_files.pushes
        assert (await client.delete(f"/api/mac/grants/{first['id']}", headers=O)).status_code == 204
        assert app.state.mac_files.pushes == pushes + 1
        assert [g.id for g in app.state.mac_files.grants] == [second["id"]]
        assert [g["id"] for g in (await client.get("/api/mac/grants")).json()] == [second["id"]]
        assert (await client.delete(f"/api/mac/grants/{first['id']}", headers=O)).status_code == 404
        assert (await client.patch(f"/api/mac/grants/{first['id']}", json={"label": "x"}, headers=O)).status_code == 404
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT revoked_at FROM mac_grants WHERE id = ?", (first["id"],))).fetchone()
    assert row["revoked_at"] is not None                       # the row stays, revoked


async def test_revoke_still_succeeds_when_the_keeper_is_away(cfg, app, alice) -> None:
    async with _login(app, "alice") as client:
        made = (await client.post("/api/mac/grants", json=_body(cfg, "Notes", "Notes"), headers=O)).json()
        app.state.mac_files.fail = True
        assert (await client.delete(f"/api/mac/grants/{made['id']}", headers=O)).status_code == 204
        assert (await client.get("/api/mac/grants")).json() == []


async def test_another_users_grant_or_bot_is_404(cfg, app, alice) -> None:
    bob = await register_user(cfg, "bob", PASSWORD)
    alices_bot, bobs_bot = await make_bot(cfg, alice.id, "Mia"), await make_bot(cfg, bob.id, "Bo")
    async with _login(app, "alice") as a_client, _login(app, "bob") as b_client:
        mine = (await a_client.post("/api/mac/grants", json=_body(cfg, "Notes", "Notes"), headers=O)).json()
        assert (await b_client.patch(f"/api/mac/grants/{mine['id']}", json={"label": "x"}, headers=O)).status_code == 404
        assert (await b_client.delete(f"/api/mac/grants/{mine['id']}", headers=O)).status_code == 404
        assert (await b_client.get("/api/mac/grants")).json() == []
        assert (await b_client.get(f"/api/mac/grants?bot_id={alices_bot.id}")).status_code == 404
        stolen = await b_client.post("/api/mac/grants", json=_body(cfg, "Docs", "Docs", bot_id=alices_bot.id), headers=O)
        assert stolen.status_code == 422 and stolen.json()["detail"] == "No such bot."
        assert (await b_client.post("/api/mac/grants", json=_body(cfg, "Docs", "Docs", bot_id=bobs_bot.id), headers=O)).status_code == 201
        assert [g["label"] for g in (await a_client.get("/api/mac/grants")).json()] == ["Notes"]
        assert [g.label for g in app.state.mac_files.grants].count("Notes") == 1


async def test_grant_routes_need_the_origin_and_a_login(cfg, app, alice) -> None:
    async with _login(app, "alice") as client:
        made = (await client.post("/api/mac/grants", json=_body(cfg, "Notes", "Notes"), headers=O)).json()
        bad = {"Origin": "http://evil.example"}
        assert (await client.post("/api/mac/grants", json=_body(cfg, "Docs", "Docs"))).status_code == 403
        assert (await client.post("/api/mac/grants", json=_body(cfg, "Docs", "Docs"), headers=bad)).status_code == 403
        assert (await client.patch(f"/api/mac/grants/{made['id']}", json={"label": "x"}, headers=bad)).status_code == 403
        assert (await client.delete(f"/api/mac/grants/{made['id']}", headers=bad)).status_code == 403
        assert (await client.post("/api/mac/pick-folder", json={}, headers=bad)).status_code == 403
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as anon:
        assert (await anon.get("/api/mac/grants")).status_code == 401
        assert (await anon.post("/api/mac/pick-folder", json={}, headers=O)).status_code == 401


async def test_pick_folder_returns_the_path_or_nothing(cfg, app, alice) -> None:
    async with _login(app, "alice") as client:
        assert (await client.post("/api/mac/pick-folder", json={}, headers=O)).json() == {"path": f"{_home(cfg)}/Docs"}
        app.state.mac_files.replace_tree({})
        assert (await client.post("/api/mac/pick-folder", json={}, headers=O)).json() == {"path": None}
        app.state.mac_files.fail = True
        away = await client.post("/api/mac/pick-folder", json={}, headers=O)
        assert away.status_code == 503 and away.json()["detail"] == MAC_AWAY_TEXT
        assert (await client.post("/api/mac/pick-folder", json={"x": 1}, headers=O)).status_code == 422
    assert isinstance(app.state.mac_files, FakeMacFiles)
