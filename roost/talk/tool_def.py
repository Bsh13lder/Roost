"""Gate metadata every tool must carry (M1 D3, spec §4.4 "a tool with no
metadata is never registered"). Kept apart from ``tool_catalog`` so domain
packages can declare their tools without importing the catalog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping

from roost.llm.types import ToolSpec

# "act" (C3): a click or keystroke on the live page, judged by roost/computer_use/gate_rules.py:judge_act.
ToolKind = Literal["read", "write_create", "write_change", "act"]


@dataclass(frozen=True)
class ToolDef:
    spec: ToolSpec
    kind: ToolKind
    # What a tainted run is told when the gate refuses this tool (D3); None: the shared text.
    tainted_refusal: str | None = None
    refused_when_tainted: bool = False   # memory: never from a tainted run, even though it creates
    # The routine and Plan tools only store a proposal or the bot's own diary line, and mark it tainted, so D3's
    # tainted-change and tainted-create-cap rules do not apply to them (they still audit, and need the allowlist).
    allowed_when_tainted: bool = False
    # The tool itself leaves the decision to the user (a proposal card, a question the user answers), so approval
    # modes never put a second Ask card in front of it.
    no_ask: bool = False
    # Programs: the tool acts only on the bot's own sealed workspace. It runs in a clean run whatever the mode and
    # asks in a tainted one (web content could be steering the code), past D3's create cap.
    sandbox: bool = False
    # One tool whose kind depends on its arguments (use_connector: GET and HEAD are reads): True means "read".
    read_when: Callable[[Mapping[str, Any]], bool] | None = None
    # Every non-read call asks at the hard floor in every mode, even from a tainted run (the card says so), and
    # is refused where no card can be shown. The user's Yes on exactly what the card shows is the only way it runs.
    asks_always: bool = False
    # Voice §4: the tool changes only the calling bot's own settings (set_my_voice). It runs with no card in a run
    # the user's own message started in their 1:1 chat that has read no outside content (clean, or site-fresh), and
    # parks on an ordinary Ask card anywhere else (a tainted run, a routine, a handoff, a room).
    own_settings: bool = False

    def kind_for(self, arguments: Mapping[str, Any]) -> ToolKind:
        """This call's gate kind."""
        if self.read_when is not None and self.read_when(arguments):
            return "read"
        return self.kind

    @property
    def name(self) -> str:
        return self.spec.name
