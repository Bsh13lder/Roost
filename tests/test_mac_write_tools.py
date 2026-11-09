"""Mac edits with diffs: create, edit, rename and trash, backups and marks (approval plan Task 10)."""

from __future__ import annotations

import json

import pytest

from approval_helpers import make_card_rig
from roost.approvals import topics
from roost.approvals.models import ApprovalState, BotApproval, CardState
from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import MAC_WRITES_PER_RUN
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.llm.scripted_team import ScriptedTeamModel
from roost.llm.types import ToolCallRequested, TurnDone
from roost.mac.edits import EditError, apply_edits
from roost.mac.fake_files import FakeMacFiles
from roost.mac.grant_service import GrantService
from roost.mac.grants import GrantStore
from roost.mac.limits import MacLimits
from roost.mac.marks import MacMarkStore
from roost.mac.models import FileRef
from roost.mac.tools import MacTools
from roost.mac.write_tools import MacWrites
from roost.talk.domain_tools import RecordContext
from roost.events.hub import EventHub
from roost.talk.gate import GateContext, judge
from roost.talk.store import TalkStore
from roost.talk.tool_catalog import CATALOG
from team_helpers import RecordingModel, make_bot, say, send, wait_idle

TREE = {"MySpace/Tasks.md": "- call bank\n- pay rent\n", "MySpace/notes/ideas.md": "kettle idea\n"}
NEW = "- call bank\n- pay rent\n- buy milk\n"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _setup(cfg, user_id, *, access="read_write", bot_id=None):
    home = str(cfg.mac_home.resolve())
    files = FakeMacFiles(TREE, home)
    grants = GrantService(GrantStore(cfg), BotStore(cfg), files)
    grant = await grants.add(user_id, path=f"{home}/MySpace", label="MySpace", access=access,
                             read_policy="ask_each", bot_id=bot_id)
    return files, grants, grant


def _writes(cfg, files, grants, limits=None) -> MacWrites:
    return MacWrites(grants, files, MacMarkStore(cfg), TalkStore(cfg), EventHub(cfg), limits)


async def _ctx(cfg, user_id, bot, *, tainted=False):
    thread = await TalkStore(cfg).create_thread(user_id, bot.id)
    return RecordContext(user_id=user_id, bot_id=bot.id, tainted=tainted, thread_id=thread.id)


async def _sha(files, grant, bot, path="Tasks.md"):
    return await files.read(FileRef(grant.id, bot.id, path))


def _call(name, call_id="w1", **arguments):
    return [ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


async def _activity(cfg, user_id, ctx):
    return [m for m in await TalkStore(cfg).list_messages(user_id, ctx.thread_id) if m.kind == "mac_activity"]


def test_write_tools_carry_kinds_topics_and_the_relax_flag():
    kinds = {"mac_write_new": "write_create", "mac_edit": "write_change", "mac_rename": "write_change",
             "mac_trash": "write_change"}
    for name, kind in kinds.items():
        assert CATALOG[name].kind == kind and topics.topic_of(name) == "files"
    assert topics.RELAX_TAINTED_TOOLS == frozenset({"mac_edit"})


def test_edits_must_match_once_each():
    assert apply_edits("a b a", [{"old": "b", "new": "c"}]) == "a c a"
    with pytest.raises(EditError, match="Edit 1: its old text appears 2 times; it must appear once."):
        apply_edits("a b a", [{"old": "a", "new": "x"}])
    with pytest.raises(EditError, match="Edit 2: its old text appears 0 times; it must appear once."):
        apply_edits("a b", [{"old": "a", "new": "x"}, {"old": "zzz", "new": "y"}])
    assert apply_edits("a b", [{"old": "a", "new": "b"}, {"old": "b b", "new": "q"}]) == "q"


async def test_the_card_shows_a_line_diff_with_counts(cfg, user_id):
    files, grants, grant = await _setup(cfg, user_id)
    bot = await make_bot(cfg, user_id, "Scout")
    ctx = await _ctx(cfg, user_id, bot)
    sha = (await _sha(files, grant, bot)).sha256
    step = await _writes(cfg, files, grants).prepare(
        "mac_edit", {"folder": "MySpace", "path": "Tasks.md", "base_hash": sha,
                     "edits": [{"old": "- pay rent\n", "new": "- pay rent\n- buy milk\n"}]}, ctx)
    assert step.title == "Edit Tasks.md · MySpace" and step.topic == "files"
    assert (step.diff.plus, step.diff.minus) == (1, 0) and "+- buy milk" in step.diff.text
    assert step.arguments["new_text"] == NEW and step.arguments["base_sha256"] == sha
    assert step.arguments["grant_id"] == grant.id


async def test_an_approved_edit_checks_the_hash_again_and_fails_cleanly_if_it_changed(cfg, user_id):
    files, grants, grant = await _setup(cfg, user_id)
    bot = await make_bot(cfg, user_id, "Scout")
    sha = (await _sha(files, grant, bot)).sha256
    model = RecordingModel(ScriptedTeamModel({"Scout": [
        _call("mac_edit", folder="MySpace", path="Tasks.md", base_hash=sha, text=NEW), say("ok")]}))
    rig = make_card_rig(cfg, model, mac_files=files, grants=grants, limits=MacLimits())
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "add milk")
    await wait_idle(rig.runner)
    card = (await rig.store.list_open(user_id))[0]
    assert card.steps[0].diff is not None and card.steps[0].diff.plus == 1
    files.replace_tree({**TREE, "MySpace/Tasks.md": "- someone else changed this\n"})
    answered = await rig.service.answer(user_id, card.id, "yes")
    await wait_idle(rig.runner)
    assert answered.state is CardState.FAILED
    result = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "approval_result"]
    assert result[0].body == "The file changed since you read it. Read it again first."
    assert (await files.read(FileRef(grant.id, bot.id, "Tasks.md"))).text == "- someone else changed this\n"
    assert await _activity(cfg, user_id, RecordContext(user_id, bot.id, False, thread.id)) == []


async def test_every_write_posts_an_activity_line_with_undo_and_a_mark(cfg, user_id):
    files, grants, grant = await _setup(cfg, user_id)
    bot = await make_bot(cfg, user_id, "Scout")
    ctx = await _ctx(cfg, user_id, bot)
    tools, marks = _writes(cfg, files, grants), MacMarkStore(cfg)
    sha = (await _sha(files, grant, bot)).sha256
    out = await tools.run("mac_edit", {"folder": "MySpace", "path": "Tasks.md", "base_hash": sha, "text": NEW}, ctx)
    assert "Edited Tasks.md in MySpace (+1 −0)" in out.text and not out.tainted
    new_sha = (await _sha(files, grant, bot)).sha256
    mark = await marks.get(user_id, grant.id, "Tasks.md")
    assert mark.sha256 == new_sha and mark.bot_id == bot.id and not mark.written_tainted
    created = await tools.run("mac_write_new", {"folder": "MySpace", "path": "new.md", "text": "hi\n"}, ctx)
    assert created.created
    renamed = await tools.run("mac_rename", {"folder": "MySpace", "path": "new.md", "new_path": "renamed.md"}, ctx)
    trashed = await tools.run("mac_trash", {"folder": "MySpace", "path": "renamed.md"}, ctx)
    assert "trash" in trashed.text and "Renamed" in renamed.text
    lines = await _activity(cfg, user_id, ctx)
    assert [m.role for m in lines] == ["activity"] * 4
    bodies = [json.loads(m.body) for m in lines]
    assert [b["op"] for b in bodies] == ["edit", "create", "rename", "trash"]
    assert bodies[0]["undo"]["kind"] == "content" and bodies[0]["undo"]["backup_id"]
    assert bodies[0]["undo"]["expected_sha256"] == new_sha and bodies[0]["undo"]["grant_id"] == grant.id
    assert bodies[1]["undo"]["kind"] == "create" and bodies[2]["undo"]["kind"] == "rename"
    assert bodies[3]["undo"]["kind"] == "trash" and bodies[3]["undo"]["back_to"] == "renamed.md"


async def test_a_read_of_an_unchanged_own_clean_file_stays_clean_and_a_tainted_write_does_not(cfg, user_id):
    files, grants, grant = await _setup(cfg, user_id)
    bot = await make_bot(cfg, user_id, "Scout")
    reads = MacTools(grants, files, MacMarkStore(cfg))
    writes = _writes(cfg, files, grants)
    sha = (await _sha(files, grant, bot)).sha256
    clean_ctx = await _ctx(cfg, user_id, bot)
    await writes.run("mac_edit", {"folder": "MySpace", "path": "Tasks.md", "base_hash": sha, "text": NEW}, clean_ctx)
    assert not (await reads.run("mac_read", {"folder": "MySpace", "path": "Tasks.md"}, clean_ctx)).tainted
    new_sha = (await _sha(files, grant, bot)).sha256
    dirty_ctx = await _ctx(cfg, user_id, bot, tainted=True)
    await writes.run("mac_edit", {"folder": "MySpace", "path": "Tasks.md", "base_hash": new_sha,
                                  "text": NEW + "- more\n"}, dirty_ctx)
    assert (await reads.run("mac_read", {"folder": "MySpace", "path": "Tasks.md"}, clean_ctx)).tainted
    await files.write(FileRef(grant.id, bot.id, "Tasks.md"), "by hand\n", (await _sha(files, grant, bot)).sha256)
    assert (await reads.run("mac_read", {"folder": "MySpace", "path": "Tasks.md"}, clean_ctx)).tainted


async def _auto_rig(cfg, user_id, bot, files, grants, script, limits):
    model = RecordingModel(ScriptedTeamModel({"Scout": script}))
    rig = make_card_rig(cfg, model, mac_files=files, grants=grants, limits=limits)
    await rig.bots.set_approval(user_id, bot.id, BotApproval("auto_edit", frozenset()))
    thread = await rig.talk.create_thread(user_id, bot.id)
    return rig, thread


async def test_writes_over_the_window_cap_hit_the_floor(cfg, user_id):
    files, grants, grant = await _setup(cfg, user_id)
    bot = await make_bot(cfg, user_id, "Scout")
    limits = MacLimits()
    rig, thread = await _auto_rig(cfg, user_id, bot, files, grants,
                                  [_call("mac_write_new", folder="MySpace", path="n.md", text="x\n"), say("ok")], limits)
    await send(rig, user_id, bot.id, thread.id, "make n.md")
    await wait_idle(rig.runner)
    assert await rig.store.list_open(user_id) == ()                       # auto-edit: it just wrote
    assert limits.writes(bot.id) == 1
    for _ in range(MAC_WRITES_PER_RUN):
        limits.note_write(bot.id)
    rig2, thread2 = await _auto_rig(cfg, user_id, bot, files, grants,
                                    [_call("mac_write_new", folder="MySpace", path="m.md", text="y\n"), say("ok")], limits)
    await send(rig2, user_id, bot.id, thread2.id, "make m.md")
    await wait_idle(rig2.runner)
    card = (await rig2.store.list_open(user_id))[0]
    assert card.steps[0].floor == "mass_edit"
    with pytest.raises(Exception):
        await files.read(FileRef(grant.id, bot.id, "m.md"))               # nothing written yet


async def test_a_secret_in_new_text_always_asks(cfg, user_id):
    files, grants, grant = await _setup(cfg, user_id)
    bot = await make_bot(cfg, user_id, "Scout")
    rig, thread = await _auto_rig(
        cfg, user_id, bot, files, grants,
        [_call("mac_write_new", folder="MySpace", path="n.md", text="my password is hunter22!\n"), say("ok")], MacLimits())
    await send(rig, user_id, bot.id, thread.id, "save it")
    await wait_idle(rig.runner)
    card = (await rig.store.list_open(user_id))[0]
    assert card.steps[0].floor == "secret"


async def test_an_edit_with_a_hash_does_not_trip_the_secret_floor(cfg, user_id):
    files, grants, grant = await _setup(cfg, user_id)
    bot = await make_bot(cfg, user_id, "Scout")
    sha = (await _sha(files, grant, bot)).sha256
    rig, thread = await _auto_rig(
        cfg, user_id, bot, files, grants,
        [_call("mac_edit", folder="MySpace", path="Tasks.md", base_hash=sha, text=NEW), say("ok")], MacLimits())
    await send(rig, user_id, bot.id, thread.id, "add milk")
    await wait_idle(rig.runner)
    assert await rig.store.list_open(user_id) == ()
    assert (await files.read(FileRef(grant.id, bot.id, "Tasks.md"))).text == NEW


async def test_read_only_grant_refuses_writes_before_any_card(cfg, user_id):
    files, grants, grant = await _setup(cfg, user_id, access="read")
    bot = await make_bot(cfg, user_id, "Scout")
    model = RecordingModel(ScriptedTeamModel({"Scout": [
        _call("mac_write_new", folder="MySpace", path="n.md", text="x\n"), say("sorry")]}))
    rig = make_card_rig(cfg, model, mac_files=files, grants=grants, limits=MacLimits())
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "make n.md")
    await wait_idle(rig.runner)
    assert await rig.store.list_open(user_id) == ()
    assert any(t.text == "MySpace is read-only for you." for t in model.requests[-1].turns if t.role == "tool")


def test_rename_and_trash_stay_refused_in_a_tainted_run():
    names = ("mac_rename", "mac_trash")
    for mode in ("ask", "auto_edit", "plan"):
        ctx = GateContext(allowed=frozenset(CATALOG), tainted=True, approval=ApprovalState(mode, frozenset(), True))
        for name in names:
            assert judge(CATALOG[name], name, {"folder": "F", "path": "a.md"}, ctx).decision == "never"
    edit = GateContext(allowed=frozenset(CATALOG), tainted=True, approval=ApprovalState("auto_edit", frozenset(), True))
    assert judge(CATALOG["mac_edit"], "mac_edit", {"folder": "F", "path": "a.md"}, edit).decision == "do"


async def test_a_secret_split_across_edits_asks_in_auto_edit(cfg, user_id):
    home = str(cfg.mac_home.resolve())
    files = FakeMacFiles({"MySpace/k.md": "AB\n"}, home)
    grants = GrantService(GrantStore(cfg), BotStore(cfg), files)
    grant = await grants.add(user_id, path=f"{home}/MySpace", label="MySpace", access="read_write",
                             read_policy="ask_each", bot_id=None)
    bot = await make_bot(cfg, user_id, "Scout")
    sha = (await _sha(files, grant, bot, "k.md")).sha256
    edits = [{"old": "A", "new": "ghp_"}, {"old": "B", "new": "Zx9kQ2mL7pR4"}]
    rig, thread = await _auto_rig(
        cfg, user_id, bot, files, grants,
        [_call("mac_edit", folder="MySpace", path="k.md", base_hash=sha, edits=edits), say("ok")], MacLimits())
    await send(rig, user_id, bot.id, thread.id, "save it")
    await wait_idle(rig.runner)
    card = (await rig.store.list_open(user_id))[0]
    assert card.steps[0].floor == "secret"
    assert (await files.read(FileRef(grant.id, bot.id, "k.md"))).text == "AB\n"
