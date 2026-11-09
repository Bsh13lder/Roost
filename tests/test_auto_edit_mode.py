"""Auto-edit (approval plan Task 11): changes go through with an activity line and Undo; the floor, topic
switches and the tainted-write rule still hold."""

from __future__ import annotations

import json

import pytest

from plan_helpers import NEW, call, direct_runner, mac_setup, mode_rig, step
from roost.approvals.texts import PARKED_TEXT
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.mac.marks import MacMarkStore
from roost.mac.models import FileRef
from roost.talk.gate import TAINTED_CHANGE_TEXT
from team_helpers import make_bot, say, send, wait_idle


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _count(cfg, sql: str, *params) -> int:
    async with db_session(cfg) as db:
        return (await (await db.execute(sql, params)).fetchone())[0]


async def _activity(rig, user_id, thread_id):
    return [m for m in await rig.talk.list_messages(user_id, thread_id) if m.kind == "mac_activity"]


async def test_auto_edit_writes_records_and_mac_files_with_activity_lines(cfg, user_id):
    files, grants, grant = await mac_setup(cfg, user_id)
    bot = await make_bot(cfg, user_id, "Scout")
    rig, thread = await mode_rig(cfg, user_id, bot, "auto_edit", [
        step(call("add_task", "a", title="Call bank"), call("mac_write_new", "b", folder="MySpace", path="n.md",
                                                              text="hi\n")),
        say("Done.")], files=files, grants=grants)
    await send(rig, user_id, bot.id, thread.id, "do both")
    await wait_idle(rig.runner)
    assert await rig.store.list_open(user_id) == ()
    assert await _count(cfg, "SELECT COUNT(*) FROM tasks WHERE user_id = ?", user_id) == 1
    assert (await files.read(FileRef(grant.id, bot.id, "n.md"))).text == "hi\n"
    lines = await _activity(rig, user_id, thread.id)
    assert [json.loads(m.body)["op"] for m in lines] == ["create"]
    assert json.loads(lines[0].body)["undo"]["kind"] == "create"


async def test_auto_edit_relaxes_a_tainted_mac_edit_and_marks_it_from_outside_content(cfg, user_id):
    files, grants, grant = await mac_setup(cfg, user_id)
    bot = await make_bot(cfg, user_id, "Scout")
    rig, thread = await mode_rig(cfg, user_id, bot, "auto_edit", [], files=files, grants=grants)
    sha = (await files.read(FileRef(grant.id, bot.id, "Tasks.md"))).sha256
    runner = direct_runner(cfg, user_id, bot, rig, "auto_edit", tainted=True, thread_id=thread.id)
    text = await runner.run(call("mac_edit", folder="MySpace", path="Tasks.md", base_hash=sha, text=NEW))
    assert text.startswith("Edited Tasks.md in MySpace")
    assert (await files.read(FileRef(grant.id, bot.id, "Tasks.md"))).text == NEW
    mark = await MacMarkStore(cfg).get(user_id, grant.id, "Tasks.md")
    assert mark.written_tainted is True
    body = json.loads((await _activity(rig, user_id, thread.id))[0].body)
    assert body["tainted_basis"] is True
    assert runner.parked is None


async def test_auto_edit_never_relaxes_tainted_record_changes(cfg, user_id):
    files, grants, grant = await mac_setup(cfg, user_id)
    bot = await make_bot(cfg, user_id, "Scout")
    rig, thread = await mode_rig(cfg, user_id, bot, "auto_edit", [], files=files, grants=grants)
    runner = direct_runner(cfg, user_id, bot, rig, "auto_edit", tainted=True, thread_id=thread.id)
    for name, args in (
        ("update_task", {"task_id": "t1", "title": "x"}), ("delete_task", {"task_id": "t1"}),
        ("delete_note", {"note_id": "n1"}),
        ("mac_rename", {"folder": "MySpace", "path": "Tasks.md", "new_path": "T2.md"}),
        ("mac_trash", {"folder": "MySpace", "path": "Tasks.md"}),
    ):
        assert await runner.run(call(name, **args)) == TAINTED_CHANGE_TEXT, name
    assert (await files.read(FileRef(grant.id, bot.id, "Tasks.md"))).text.startswith("- call bank")
    assert runner.parked is None


async def test_a_topic_switch_still_asks_in_auto_edit(cfg, user_id):
    files, grants, grant = await mac_setup(cfg, user_id)
    bot = await make_bot(cfg, user_id, "Scout")
    rig, thread = await mode_rig(cfg, user_id, bot, "auto_edit", [], files=files, grants=grants)
    runner = direct_runner(cfg, user_id, bot, rig, "auto_edit", thread_id=thread.id, topics=frozenset({"tasks"}))
    assert await runner.run(call("add_task", title="Call bank")) == PARKED_TEXT
    assert runner.parked is not None and runner.parked.topic == "tasks"
    assert await _count(cfg, "SELECT COUNT(*) FROM tasks WHERE user_id = ?", user_id) == 0
    other = direct_runner(cfg, user_id, bot, rig, "auto_edit", thread_id=thread.id, topics=frozenset({"tasks"}))
    assert (await other.run(call("mac_write_new", folder="MySpace", path="n.md", text="x\n"))).startswith("Created")
