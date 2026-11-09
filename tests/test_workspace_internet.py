"""Internet in the workspace, gateway side (owner, 2026-10-23, A4).

A per-bot switch, off by default (schema v34 ``bots.workspace_internet``), set only by its owner through
``PUT /api/bots/{id}/workspace-internet``. The keeper recreates the workspace on the switch (files kept); the
prompt and run_program's text say whether the workspace has internet; with internet on, what a program prints or
a workspace file holds may be web content, so it taints the run like a page."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from roost.bots.models import BotPatch
from roost.bots.service import bot_out
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.db.migrations import MIGRATIONS
from roost.desk import DeskFactory, DeskUnavailable
from roost.desk.client import KeeperClient, KeeperDesk
from roost.events.hub import EventHub
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.programs.marks import WorkspaceMarks
from roost.programs.texts import programs_text
from roost.programs.tools import ProgramTools
from roost.talk.domain_tools import RecordContext
from roost.talk.instructions import build_instructions
from roost.talk.store import TalkStore
from roost.talk.tools import tool_specs_for
from team_helpers import make_bot

ORIGIN = {"Origin": "http://127.0.0.1:18800"}
AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


# --- the column and the store -----------------------------------------------------------------------------------

def test_the_migration_is_v34_and_adds_one_column_off_by_default():
    migration = next(m for m in MIGRATIONS if m.version == 34)
    assert migration.name == "workspace internet"
    [step] = migration.steps
    assert (step.table, step.column, step.definition) == ("bots", "workspace_internet", "INTEGER NOT NULL DEFAULT 0")


async def test_a_bot_starts_without_internet_and_only_its_owner_switches_it(cfg):
    alice = (await register_user(cfg, "alice", "pw-123456")).id
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bot = await make_bot(cfg, alice, "Coder")
    store = BotStore(cfg)
    assert bot.workspace_internet is False and bot_out(bot, None)["workspace_internet"] is False
    assert await store.set_workspace_internet(bob, bot.id, True) is None
    on = await store.set_workspace_internet(alice, bot.id, True)
    assert on.workspace_internet is True and (await store.get(alice, bot.id)).workspace_internet is True
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT workspace_internet FROM bots WHERE id = ?", (bot.id,))).fetchone()
    assert row[0] == 1


# --- the route ---------------------------------------------------------------------------------------------------

def _login(client: TestClient, name: str) -> None:
    r = client.post("/api/auth/register", json={"username": name, "password": "pw-123456"}, headers=ORIGIN)
    assert r.status_code == 201


def _bot(client: TestClient) -> dict:
    r = client.post("/api/bots", json={"name": "Coder", "job": "codes", "instructions": "", "avatar": AVATAR},
                    headers=ORIGIN)
    assert r.status_code == 201
    return r.json()


def test_the_owner_turns_it_on_and_the_workspace_is_recreated(cfg):
    app = create_app()
    with TestClient(app) as client:
        _login(client, "alice")
        bot = _bot(client)
        r = client.put(f"/api/bots/{bot['id']}/workspace-internet", json={"on": True}, headers=ORIGIN)
        assert r.status_code == 200 and r.json()["workspace_internet"] is True
        desk = app.state.desks.for_bot(bot["id"], bot["computer"])
        assert desk.workspace_internet is True
        off = client.put(f"/api/bots/{bot['id']}/workspace-internet", json={"on": False}, headers=ORIGIN)
        assert off.json()["workspace_internet"] is False and desk.workspace_internet is False


async def test_it_is_owner_only_needs_the_origin_and_a_boolean(cfg):
    app = create_app()
    await register_user(cfg, "bob", "pw-123456")
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"},
                           headers=ORIGIN).status_code == 200
        bot = _bot(client)
        assert client.put(f"/api/bots/{bot['id']}/workspace-internet", json={"on": True}).status_code == 403
        bad = client.put(f"/api/bots/{bot['id']}/workspace-internet", json={"on": "yes"}, headers=ORIGIN)
        assert bad.status_code == 422
        client.post("/api/auth/logout", headers=ORIGIN)
        await register_user(cfg, "carol", "pw-123456")
        assert client.post("/api/auth/login", json={"username": "carol", "password": "pw-123456"},
                           headers=ORIGIN).status_code == 200
        assert client.put(f"/api/bots/{bot['id']}/workspace-internet", json={"on": True},
                          headers=ORIGIN).status_code == 404


def test_an_unreachable_keeper_is_a_503_and_nothing_changes(cfg):
    app = create_app()
    with TestClient(app) as client:
        _login(client, "alice")
        bot = _bot(client)
        app.state.desks.for_bot(bot["id"], bot["computer"]).force_unavailable = True
        r = client.put(f"/api/bots/{bot['id']}/workspace-internet", json={"on": True}, headers=ORIGIN)
        assert r.status_code == 503
        assert next(b for b in client.get("/api/bots").json() if b["id"] == bot["id"])["workspace_internet"] is False


# --- the keeper client -------------------------------------------------------------------------------------------

async def test_the_keeper_client_sends_one_signed_boolean():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"internet": True})

    config = load_config()
    desk = KeeperDesk(config, "b1", computer="linux", transport=httpx.MockTransport(handler))
    await desk.set_workspace_internet(True)
    [request] = seen
    assert request.url.path == "/desks/b1/workspace/internet" and json.loads(request.content) == {"internet": True}
    assert request.headers.get("x-roost-sig") and request.headers.get("x-roost-nonce")


async def test_a_retired_keeper_desk_refuses():
    desk = KeeperDesk(load_config(), "b1", computer="linux", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={})))
    desk._retired = True
    with pytest.raises(DeskUnavailable):
        await desk.set_workspace_internet(True)


# --- what the bot is told ------------------------------------------------------------------------------------------

async def test_the_prompt_and_run_program_say_whether_there_is_internet(cfg):
    user = (await register_user(cfg, "alice", "pw-123456")).id
    bot = await make_bot(cfg, user, "Coder")
    on = await BotStore(cfg).set_workspace_internet(user, bot.id, True)
    assert programs_text(False) in build_instructions(bot) and "no internet" in programs_text(False)
    assert programs_text(True) in build_instructions(on) and "has internet" in programs_text(True)
    spec_off = next(s for s in tool_specs_for(bot, team=False) if s.name == "run_program")
    spec_on = next(s for s in tool_specs_for(on, team=False) if s.name == "run_program")
    assert "no internet" in spec_off.description and "has internet" in spec_on.description


# --- taint ---------------------------------------------------------------------------------------------------------

async def test_with_internet_on_a_programs_output_taints_the_run(cfg):
    user = (await register_user(cfg, "alice", "pw-123456")).id
    bot = await make_bot(cfg, user, "Coder")
    store = BotStore(cfg)
    desks = DeskFactory(cfg)
    talk = TalkStore(cfg)
    thread = await talk.create_thread(user, bot.id)

    async def internet(user_id: str, bot_id: str) -> bool:
        found = await store.get(user_id, bot_id)
        return bool(found and found.workspace_internet)

    tools = ProgramTools(desks.for_bot, WorkspaceMarks(cfg), talk, EventHub(cfg), internet=internet)
    ctx = RecordContext(user_id=user, bot_id=bot.id, tainted=False, thread_id=thread.id, run_id="r1")
    assert (await tools.run("run_program", {"command": "echo hi"}, ctx)).tainted is False
    await store.set_workspace_internet(user, bot.id, True)
    assert (await tools.run("run_program", {"command": "echo hi"}, ctx)).tainted is True
    assert (await tools.run("list_files", {}, ctx)).tainted is True
