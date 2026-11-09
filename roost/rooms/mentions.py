"""@mentions in a room post, matched to member bots and bound to their ids
at post time (D-E). Longest names first, so "@Scout Two" never also
counts as "@Scout"; an e-mail address (me@scout.com) or a longer word
(@Scouting) is not a mention."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from roost.bots.models import Bot

_EVERYONE = re.compile(r"(?<![\w])@everyone(?![\w\-])(?!\.\w)", re.IGNORECASE)


@dataclass(frozen=True)
class MentionResult:
    everyone: bool
    bot_ids: tuple[str, ...]


def _pattern(name: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w])@{re.escape(name)}(?![\w\-])(?!\.\w)", re.IGNORECASE)


def parse_mentions(text: str, members: Sequence[Bot]) -> MentionResult:
    remaining = text
    found: tuple[str, ...] = ()
    for bot in sorted(members, key=lambda b: len(b.name), reverse=True):
        pattern = _pattern(bot.name)
        if pattern.search(remaining):
            found = (*found, bot.id)
            remaining = pattern.sub(" ", remaining)
    return MentionResult(everyone=bool(_EVERYONE.search(text)), bot_ids=found)


def route_targets(mention: MentionResult, members: Sequence[Bot], coordinator_id: str | None) -> tuple[str, ...]:
    """@everyone → every member; @names → those members (room order); no
    mention → the coordinator (or the first member if it is gone)."""
    member_ids = tuple(b.id for b in members)
    if mention.everyone:
        return member_ids
    named = tuple(i for i in member_ids if i in mention.bot_ids)
    if named:
        return named
    return (coordinator_id,) if coordinator_id in member_ids else member_ids[:1]
