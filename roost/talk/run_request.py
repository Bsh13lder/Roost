"""What one model step is sent (keeping the cache warm, docs/plans/2026-11-09-roost-tool-groups.md §4).

The prompt cache's prefix is tools → system → messages, so each piece here changes as rarely as it can:

- ``offered_specs``: the core tools and the groups loaded so far; the list only grows during a run, and
  ``load_tools`` never drops out of its tail.
- ``system_for``: the system prompt. A Linux bot's screen prose rides in it only while the computer group is
  loaded; when that group loads mid-run the tool list changes in the same step, so the swap costs no extra cache
  break (the step after a load is a miss either way).
- ``request_turns``: the chat's turns, then the run's own steps with their old tool results folded in batches
  (``roost/talk/compact.py``).

Moved out of ``roost/talk/turn.py`` to keep it under its size."""

from __future__ import annotations

from roost.llm.types import ChatTurn, ToolSpec
from roost.talk.compact import compact_results
from roost.talk.tool_groups import COMPUTER_GROUP, LOAD_TOOLS, visible_specs


def offered_specs(specs: tuple[ToolSpec, ...], loaded: frozenset[str] | None) -> tuple[ToolSpec, ...]:
    """The tools this step is offered: the core and the groups loaded so far, or every tool with groups off."""
    if loaded is None:
        return tuple(spec for spec in specs if spec.name != LOAD_TOOLS)
    return visible_specs(specs, loaded)


def system_for(system: str, screen_system: str | None, loaded: frozenset[str] | None) -> str:
    """The system prompt for this step: the one with the screen prose once the computer group is loaded."""
    if screen_system is None or loaded is None or COMPUTER_GROUP not in loaded:
        return system
    return screen_system


def request_turns(history: tuple[ChatTurn, ...], added: tuple[ChatTurn, ...]) -> tuple[ChatTurn, ...]:
    """The transcript the model sees: the chat, then the run's steps with their old results folded."""
    return history + compact_results(added)
