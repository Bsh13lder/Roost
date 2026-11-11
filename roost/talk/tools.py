"""The per-run tool allowlist (S1 D2, Ruling 28): every bot gets the whole
catalog. Only the team tools depend on the run: ``ask_bot`` and ``list_bots``
need a handoff port, and ``suggest_bot`` is the main bot's, outside rooms.
The gate still checks each call's kind, the tainted-write rule and the link
guard (``roost.talk.gate``)."""

from __future__ import annotations

from roost.apps.tool_specs import APP_TOOLS, app_tools_for
from roost.bots.models import Bot
from roost.computer_use.tool_specs import cu_tools_for
from roost.constants import CU_TOOLS
from roost.llm.types import ToolSpec
from roost.programs.tool_specs import RUN_PROGRAM_SPEC, run_program_spec
from roost.talk.tool_catalog import ASK_BOT_SPEC, CATALOG, SUGGEST_BOT_SPEC  # noqa: F401 — re-exported

TEAM_TOOLS = frozenset({"ask_bot", "list_bots"})
LEAD_TOOLS = frozenset({"suggest_bot", "suggest_model"})
CREATOR_TOOLS = frozenset({"create_bot", "set_bot_model"})
PARALLEL_TOOLS = frozenset({"ask_bot"})
DESK_TOOLS = frozenset({"open_page", "read_page", "web_search"})
SCREEN_TOOLS = frozenset(CU_TOOLS)   # C3: only a bot on its Linux computer (cu_tools_for), never a helper
EVERY_BOT_TOOLS = frozenset(CATALOG) - TEAM_TOOLS - LEAD_TOOLS - CREATOR_TOOLS - SCREEN_TOOLS - APP_TOOLS


def run_tool_names(bot: Bot, *, team: bool, in_room: bool = False, user_started: bool = False) -> frozenset[str]:
    """``create_bot`` (Ruling 29) only for the main bot, outside rooms, in a run
    the user's own message started — never a handoff, room post or routine. The screen and app tools only on
    the bot's Linux computer."""
    names = EVERY_BOT_TOOLS | cu_tools_for(bot) | app_tools_for(bot)
    if team:
        names = names | TEAM_TOOLS
        if bot.is_primary and not in_room:
            names = names | LEAD_TOOLS | (CREATOR_TOOLS if user_started else frozenset())
    return names


def tool_specs_for(
    bot: Bot, *, team: bool, in_room: bool = False, user_started: bool = False,
) -> tuple[ToolSpec, ...]:
    """The run's tool specs; run_program says whether this bot's workspace has internet (A4)."""
    names = run_tool_names(bot, team=team, in_room=in_room, user_started=user_started)
    return tuple(_spec_for(bot, tool.spec) for tool in CATALOG.values() if tool.name in names)


def _spec_for(bot: Bot, spec: ToolSpec) -> ToolSpec:
    return run_program_spec(bot.workspace_internet) if spec.name == RUN_PROGRAM_SPEC.name else spec


# A helper reads and reports. It never asks, creates, switches, asks the user for help, or sends helpers.
# Owner, 2026-11-03: it opens and reads pages and searches the web (open_page, read_page, web_search), sharing the
# parent's taint and link scope. read_pdf is a screen tool: the screen loop is one per computer, never a helper's.
HELPER_DENIED = frozenset({
    "send_helpers", "ask_bot", "list_bots", "suggest_bot", "suggest_model", "create_bot", "set_bot_model",
    "ask_for_help", "request_sign_in", "ask_secret_field", "ask_choice",
    "mac_find", "mac_read", "mac_write_new", "mac_edit", "mac_rename", "mac_trash",
    *CU_TOOLS,   # one loop per computer: the screen belongs to the run, never to its helpers
    # Skills: a helper may list and read skills (reads), never propose one (not reads, so never given anyway).
    "propose_skill", "propose_skill_change",
    "propose_instructions_update",   # Replies: a helper never offers its parent's instructions
    "update_my_instructions",        # A2: nor changes them
    "request_connector",   # a card for the user is the bot's to raise, never a helper's
    "install_app", "remove_app",   # Install an app: only the bot itself asks, never a helper
    "load_tools",   # tool groups: a helper is offered its read tools whole
})


def helper_tool_names(parent_allowed: frozenset[str]) -> frozenset[str]:
    """A helper's tools: the parent's own, only the ``read`` kind, minus ``HELPER_DENIED``."""
    return frozenset(
        name for name in parent_allowed
        if name in CATALOG and CATALOG[name].kind == "read" and name not in HELPER_DENIED
    )
