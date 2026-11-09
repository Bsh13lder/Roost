"""Helpers for the Auto-edit and Review-first (plan) tests (not a test module)."""

from __future__ import annotations

from approval_helpers import make_card_rig
from roost.approvals.models import ApprovalState, BotApproval
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.desk import DeskFactory
from roost.events.hub import EventHub
from roost.llm.scripted_team import ScriptedTeamModel
from roost.llm.types import ToolCallRequested, TurnDone
from roost.mac.fake_files import FakeMacFiles
from roost.mac.grant_service import GrantService
from roost.mac.grants import GrantStore
from roost.mac.limits import MacLimits
from roost.talk.gate import Gate
from roost.talk.tool_runner import ToolRunner
from roost.talk.tools import run_tool_names
from team_helpers import RecordingModel

TREE = {"MySpace/Tasks.md": "- call bank\n- pay rent\n", "MySpace/notes/ideas.md": "kettle idea\n"}
NEW = "- call bank\n- pay rent\n- buy milk\n"


def call(tool: str, call_id: str = "c1", /, **arguments) -> ToolCallRequested:
    return ToolCallRequested(id=call_id, name=tool, arguments=arguments)


def step(*calls: ToolCallRequested) -> list:
    return [*calls, TurnDone("tool_use")]


async def mac_setup(cfg, user_id, *, access: str = "read_write"):
    home = str(cfg.mac_home.resolve())
    files = FakeMacFiles(TREE, home)
    grants = GrantService(GrantStore(cfg), BotStore(cfg), files)
    grant = await grants.add(user_id, path=f"{home}/MySpace", label="MySpace", access=access,
                             read_policy="ask_each", bot_id=None)
    return files, grants, grant


async def mode_rig(cfg, user_id, bot, mode: str, script, *, files=None, grants=None, topics=()):
    """A card rig whose bot (one scripted agent called by the bot's name) is in ``mode``, and a chat."""
    model = RecordingModel(ScriptedTeamModel({bot.name: script}))
    rig = make_card_rig(cfg, model, mac_files=files, grants=grants, limits=MacLimits())
    await rig.bots.set_approval(user_id, bot.id, BotApproval(mode, frozenset(topics)))
    thread = await rig.talk.create_thread(user_id, bot.id)
    return rig, thread


def direct_runner(cfg, user_id, bot, rig, mode: str, *, tainted: bool = False, thread_id=None,
                  topics=frozenset()) -> ToolRunner:
    """A ToolRunner (no model) for one bot, to call tools one by one."""
    return ToolRunner(
        user_id=user_id, bot_id=bot.id, desk=DeskFactory(cfg).for_bot(bot.id), gate=Gate(cfg),
        activity=ActivityBoard(), events=EventHub(cfg), allowed=run_tool_names(bot, team=False),
        domain=rig.runner.domain, approval=ApprovalState(mode, topics, True), tainted=tainted,
        thread_id=thread_id,
    )
