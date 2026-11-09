import pytest
from approval_helpers import make_card_rig
from roost.approvals.models import BotApproval
from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import MAC_WRITES_PER_RUN
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.llm.scripted_team import ScriptedTeamModel
from roost.llm.types import ToolCallRequested, TurnDone
from roost.mac.fake_files import FakeMacFiles
from roost.mac.grant_service import GrantService
from roost.mac.grants import GrantStore
from roost.mac.limits import MacLimits
from roost.mac.models import FileRef
from team_helpers import RecordingModel, make_bot, say, send, wait_idle

@pytest.fixture
async def cfg():
    c = load_config(); await init_db(c); return c

async def test_one_run_stops_at_the_mass_write_floor(cfg):
    uid = (await register_user(cfg, "alice", "pw-123456")).id
    home = str(cfg.mac_home.resolve())
    files = FakeMacFiles({"MySpace/a.md": "x\n"}, home)
    grants = GrantService(GrantStore(cfg), BotStore(cfg), files)
    grant = await grants.add(uid, path=f"{home}/MySpace", label="MySpace", access="read_write",
                             read_policy="ask_each", bot_id=None)
    bot = await make_bot(cfg, uid, "Scout")
    n = MAC_WRITES_PER_RUN + 10
    script = [[ToolCallRequested(id=f"w{i}", name="mac_write_new", arguments={"folder": "MySpace", "path": f"n{i}.md", "text": "y\n"}), TurnDone("tool_use")] for i in range(n)]
    script.append(say("ok"))
    limits = MacLimits()
    rig = make_card_rig(cfg, RecordingModel(ScriptedTeamModel({"Scout": script})), mac_files=files, grants=grants, limits=limits)
    await rig.bots.set_approval(uid, bot.id, BotApproval("auto_edit", frozenset()))
    thread = await rig.talk.create_thread(uid, bot.id)
    await send(rig, uid, bot.id, thread.id, "make files")
    await wait_idle(rig.runner)
    written = 0
    for i in range(n):
        try:
            await files.read(FileRef(grant.id, bot.id, f"n{i}.md")); written += 1
        except Exception:
            pass
    assert written <= MAC_WRITES_PER_RUN
    assert limits.writes(bot.id) <= MAC_WRITES_PER_RUN
    cards = await rig.store.list_open(uid)
    assert len(cards) == 1 and cards[0].steps[0].floor == "mass_edit"


async def test_a_tainted_auto_edit_run_still_stops_at_the_mass_write_floor(cfg):
    from plan_helpers import mac_setup
    from roost.approvals.models import ApprovalState
    from roost.bots.status import ActivityBoard
    from roost.desk import DeskFactory
    from roost.events.hub import EventHub
    from roost.talk.gate import Gate
    from roost.talk.tool_runner import ToolRunner
    from roost.talk.tools import run_tool_names

    uid = (await register_user(cfg, "alice", "pw-123456")).id
    files, grants, grant = await mac_setup(cfg, uid)
    bot = await make_bot(cfg, uid, "Scout")
    limits = MacLimits()
    rig = make_card_rig(cfg, RecordingModel(ScriptedTeamModel({bot.name: []})), mac_files=files, grants=grants,
                        limits=limits)
    thread = await rig.talk.create_thread(uid, bot.id)
    runner = ToolRunner(
        user_id=uid, bot_id=bot.id, desk=DeskFactory(cfg).for_bot(bot.id), gate=Gate(cfg),
        activity=ActivityBoard(), events=EventHub(cfg), allowed=run_tool_names(bot, team=False),
        domain=rig.runner.domain, approval=ApprovalState("auto_edit", frozenset(), True), tainted=True,
        thread_id=thread.id, mac_writes_now=lambda: limits.writes(bot.id),
    )
    ref = FileRef(grant.id, bot.id, "Tasks.md")
    for i in range(MAC_WRITES_PER_RUN):
        sha = (await files.read(ref)).sha256
        await runner.run(ToolCallRequested(id=f"e{i}", name="mac_edit", arguments={
            "folder": "MySpace", "path": "Tasks.md", "base_hash": sha, "text": f"v{i}\n"}))
        assert runner.parked is None, i
    sha = (await files.read(ref)).sha256
    await runner.run(ToolCallRequested(id="over", name="mac_edit", arguments={
        "folder": "MySpace", "path": "Tasks.md", "base_hash": sha, "text": "over\n"}))
    assert runner.parked is not None and runner.parked.floor == "mass_edit"
    assert (await files.read(ref)).text == f"v{MAC_WRITES_PER_RUN - 1}\n"
