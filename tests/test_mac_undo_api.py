"""Undo is the user's click and reverts exactly that change (approval plan Task 10)."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from approval_helpers import ORIGIN
from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.mac.models import FileRef
from roost.talk.domain_tools import RecordContext
from team_helpers import make_bot, wait_idle

PASSWORD = "pw-123456"
TREE = {"MySpace/Tasks.md": "- call bank\n", "MySpace/notes/ideas.md": "kettle idea\n", "MySpace/notes/": ""}


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@asynccontextmanager
async def _signed_in(app, username: str):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        login = await client.post("/api/auth/login", json={"username": username, "password": PASSWORD}, headers=ORIGIN)
        assert login.status_code == 200
        try:
            yield client
        finally:
            await wait_idle(app.state.turns, timeout=8)


async def _world(cfg):
    alice = await register_user(cfg, "alice", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Scout")
    app = create_app(cfg)
    files = app.state.mac_files
    files.replace_tree(TREE)
    home = str(cfg.mac_home.resolve())
    grant = await app.state.grants.add(alice.id, path=f"{home}/MySpace", label="MySpace", access="read_write",
                                       read_policy="ask_each", bot_id=None)
    thread = await app.state.talk.create_thread(alice.id, bot.id)
    return app, alice, bot, grant, thread, files


async def _do(app, alice, bot, thread, name, **arguments):
    ctx = RecordContext(user_id=alice.id, bot_id=bot.id, tainted=False, thread_id=thread.id)
    return await app.state.turns.domain.run(name, arguments, ctx)


async def _last_activity(app, alice, thread):
    return [m for m in await app.state.talk.list_messages(alice.id, thread.id) if m.kind == "mac_activity"][-1]


async def _text(files, grant, bot, path):
    return (await files.read(FileRef(grant.id, bot.id, path))).text


async def test_undo_restores_and_a_second_undo_is_409(cfg):
    app, alice, bot, grant, thread, files = await _world(cfg)
    sha = (await files.read(FileRef(grant.id, bot.id, "Tasks.md"))).sha256
    await _do(app, alice, bot, thread, "mac_edit", folder="MySpace", path="Tasks.md", base_hash=sha, text="- new\n")
    line = await _last_activity(app, alice, thread)
    async with _signed_in(app, "alice") as client:
        first = await client.post(f"/api/mac/activity/{line.id}/undo", json={}, headers=ORIGIN)
        assert first.status_code == 200, first.text
        said = first.json()["message"]
        assert said["kind"] == "mac_activity" and json.loads(said["body"])["op"] == "undo"
        assert await _text(files, grant, bot, "Tasks.md") == "- call bank\n"
        second = await client.post(f"/api/mac/activity/{line.id}/undo", json={}, headers=ORIGIN)
        assert second.status_code == 409
    assert json.loads((await app.state.talk.get_message(alice.id, line.id)).body)["undo"] is None


async def test_undo_refuses_when_the_file_changed_since(cfg):
    app, alice, bot, grant, thread, files = await _world(cfg)
    sha = (await files.read(FileRef(grant.id, bot.id, "Tasks.md"))).sha256
    await _do(app, alice, bot, thread, "mac_edit", folder="MySpace", path="Tasks.md", base_hash=sha, text="- new\n")
    line = await _last_activity(app, alice, thread)
    files.replace_tree({**TREE, "MySpace/Tasks.md": "- by hand\n"})
    async with _signed_in(app, "alice") as client:
        refused = await client.post(f"/api/mac/activity/{line.id}/undo", json={}, headers=ORIGIN)
        assert refused.status_code == 409 and refused.json()["detail"] == "The file changed since; nothing was undone."
    assert await _text(files, grant, bot, "Tasks.md") == "- by hand\n"


async def test_undo_of_create_trash_and_rename(cfg):
    app, alice, bot, grant, thread, files = await _world(cfg)
    await _do(app, alice, bot, thread, "mac_write_new", folder="MySpace", path="made.md", text="hello\n")
    create = await _last_activity(app, alice, thread)
    await _do(app, alice, bot, thread, "mac_rename", folder="MySpace", path="Tasks.md", new_path="moved.md")
    rename = await _last_activity(app, alice, thread)
    await _do(app, alice, bot, thread, "mac_trash", folder="MySpace", path="notes/ideas.md")
    trash = await _last_activity(app, alice, thread)
    async with _signed_in(app, "alice") as client:
        for line in (trash, rename, create):
            reply = await client.post(f"/api/mac/activity/{line.id}/undo", json={}, headers=ORIGIN)
            assert reply.status_code == 200, reply.text
    assert await _text(files, grant, bot, "notes/ideas.md") == "kettle idea\n"
    assert await _text(files, grant, bot, "Tasks.md") == "- call bank\n"
    with pytest.raises(Exception):
        await files.read(FileRef(grant.id, bot.id, "made.md"))


async def test_another_users_activity_is_404_for_undo(cfg):
    app, alice, bot, grant, thread, files = await _world(cfg)
    await register_user(cfg, "bob", PASSWORD)
    await _do(app, alice, bot, thread, "mac_write_new", folder="MySpace", path="made.md", text="hello\n")
    line = await _last_activity(app, alice, thread)
    plain = await app.state.talk.add_message(alice.id, thread.id, "user", "hi")
    async with _signed_in(app, "bob") as client:
        assert (await client.post(f"/api/mac/activity/{line.id}/undo", json={}, headers=ORIGIN)).status_code == 404
    async with _signed_in(app, "alice") as client:
        assert (await client.post(f"/api/mac/activity/{plain.id}/undo", json={}, headers=ORIGIN)).status_code == 404
        assert (await client.post("/api/mac/activity/nope/undo", json={}, headers=ORIGIN)).status_code == 404
    assert await _text(files, grant, bot, "made.md") == "hello\n"


async def test_undo_needs_the_origin(cfg):
    app, alice, bot, grant, thread, files = await _world(cfg)
    await _do(app, alice, bot, thread, "mac_write_new", folder="MySpace", path="made.md", text="hello\n")
    line = await _last_activity(app, alice, thread)
    async with _signed_in(app, "alice") as client:
        bad = await client.post(f"/api/mac/activity/{line.id}/undo", json={}, headers={"Origin": "http://evil.example"})
        assert bad.status_code == 403
    assert await _text(files, grant, bot, "made.md") == "hello\n"


async def test_undo_after_the_folder_stopped_being_shared_is_refused(cfg):
    app, alice, bot, grant, thread, files = await _world(cfg)
    await _do(app, alice, bot, thread, "mac_write_new", folder="MySpace", path="made.md", text="hello\n")
    line = await _last_activity(app, alice, thread)
    await app.state.grants.revoke(alice.id, grant.id)
    async with _signed_in(app, "alice") as client:
        refused = await client.post(f"/api/mac/activity/{line.id}/undo", json={}, headers=ORIGIN)
        assert refused.status_code == 409


async def test_undo_of_a_pruned_backup_says_the_backup_expired(cfg):
    app, alice, bot, grant, thread, files = await _world(cfg)
    sha = (await files.read(FileRef(grant.id, bot.id, "Tasks.md"))).sha256
    await _do(app, alice, bot, thread, "mac_edit", folder="MySpace", path="Tasks.md", base_hash=sha, text="- new\n")
    line = await _last_activity(app, alice, thread)
    files._backups.clear()          # the keeper pruned (or lost) the backup
    async with _signed_in(app, "alice") as client:
        refused = await client.post(f"/api/mac/activity/{line.id}/undo", json={}, headers=ORIGIN)
        assert refused.status_code == 409 and refused.json()["detail"] == "The backup for this change has expired."
    assert await _text(files, grant, bot, "Tasks.md") == "- new\n"
    assert json.loads((await app.state.talk.get_message(alice.id, line.id)).body)["undo"] is not None
