"""What a tool call hands back to the run (shared by team and domain tools)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolOutcome:
    text: str
    tainted: bool = False                 # the call loaded outside content or a tainted record
    link_scope: tuple[str, ...] = ()      # links a teammate's chain read (D4)
    created: bool = False                 # a write_create call stored a record
    failed: bool = False                  # an approved Mac step that did not run (the card shows it failed)
