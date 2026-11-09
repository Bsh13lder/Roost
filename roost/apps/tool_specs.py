"""The app tools and their gate kinds (docs/plans/2026-10-22-roost-install-app.md §1).

install_app and remove_app always ask, at the hard floor, in every mode and in tainted runs too; list_apps is a
read. Only a bot on its Linux computer is offered them (``app_tools_for``)."""

from __future__ import annotations

from roost.apps.constants import APP_WHY_MAX_CHARS
from roost.bots.models import Bot
from roost.computer_use.tool_specs import LINUX_COMPUTER
from roost.llm.types import ToolSpec
from roost.talk.tool_def import ToolDef

_PACKAGE = {"type": "string", "description": "The Debian package's exact name, such as gimp or libreoffice-calc."}

INSTALL_APP_SPEC = ToolSpec(
    name="install_app",
    description=(
        "Ask the user to install a Debian package on your own Linux computer. Nothing installs until they say Yes "
        "on a card that shows the package, your reason and Debian's description. Only packages from Debian's "
        "main archive; browsers, remote access, VPN and system tools are refused. Then stop and wait for the answer."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "package": _PACKAGE,
            "why": {"type": "string",
                    "description": f"One short sentence: what you need it for (up to {APP_WHY_MAX_CHARS} characters)."},
        },
        "required": ["package", "why"],
    },
)

REMOVE_APP_SPEC = ToolSpec(
    name="remove_app",
    description=("Ask the user to remove a package you installed with install_app. Nothing changes until they say "
                 "Yes on a card."),
    input_schema={"type": "object", "properties": {"package": _PACKAGE}, "required": ["package"]},
)

LIST_APPS_SPEC = ToolSpec(
    name="list_apps",
    description="See the apps the user approved on your own Linux computer.",
    input_schema={"type": "object", "properties": {}},
)

APP_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(INSTALL_APP_SPEC, "write_change", asks_always=True),
    ToolDef(REMOVE_APP_SPEC, "write_change", asks_always=True),
    ToolDef(LIST_APPS_SPEC, "read"),
)

APP_TOOLS: frozenset[str] = frozenset(tool.name for tool in APP_TOOL_DEFS)


def app_tools_for(bot: Bot) -> frozenset[str]:
    """The app tools for a bot on its Linux computer; none on Mac Brave."""
    return APP_TOOLS if bot.computer == LINUX_COMPUTER else frozenset()
