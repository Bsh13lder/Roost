"""The tool groups a run starts with (owner, 2026-11-09; ``roost/talk/tool_groups.py``): read from the run's own
words, so most requests need no ``load_tools`` step. The claimed items' text (your message, a handoff, a routine's
instructions, a card's answer) and the chat's last few messages are scanned; a card's answer or a Stuck reply
carries on a screen task, so the computer group comes with it. The groups the thread's last runs used come too
(keeping the cache warm, §4; ``roost/talk/recent_groups.py``): a bot that browsed will most likely browse again."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from roost.talk.tool_groups import COMPUTER_GROUP, ROUTINE_RUN_GROUP, groups_in_text, tool_groups_on
from roost.work.models import WorkItem, WorkKind

RECENT_MESSAGES: Final = 6   # the chat's newest messages read for a follow-up ("move it to Friday")
_SCREEN_KINDS: Final = frozenset({"card_answer", "stuck"})


def start_groups(
    items: tuple[WorkItem, ...], recent: Iterable[str], *, stuck_reply: bool,
    recent_groups: Iterable[frozenset[str]] = (),
) -> frozenset[str] | None:
    """The groups loaded before the first step; ``None`` when groups are off (every tool is offered)."""
    if not tool_groups_on():
        return None
    words = "\n".join((*(item.body for item in items), *recent))
    screen = stuck_reply or any(item.kind in _SCREEN_KINDS for item in items)
    # A routine's own run can finish its routine (owner, 2026-11-11): that one tool rides along from the start.
    routine = bool(items) and all(item.kind == WorkKind.ROUTINE for item in items)
    used = frozenset().union(*recent_groups)
    return (groups_in_text(words) | used | (frozenset({COMPUTER_GROUP}) if screen else frozenset())
            | (frozenset({ROUTINE_RUN_GROUP}) if routine else frozenset()))
