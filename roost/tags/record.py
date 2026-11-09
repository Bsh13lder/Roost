"""The one call every bot tool makes for a new record's tags."""

from __future__ import annotations

from typing import Iterable

from roost.tags.rules import obsidian_tag, record_tags, topic_tags
from roost.talk.domain_tools import RecordContext


def bot_record_tags(ctx: RecordContext, project_name: str | None, raw_topics: Iterable[str]) -> tuple[str, ...]:
    """``bot:<slug>``, ``project:<slug>`` (when ``project_name``) and the checked topic tags.
    ``ValueError`` (a plain sentence) for a topic tag that breaks the rules."""
    return record_tags(bot_name=ctx.bot_name, bot_id=ctx.bot_id, project_name=project_name,
                       topics=topic_tags(raw_topics))


def plan_tags(ctx: RecordContext, raw_topics: Iterable[str]) -> tuple[str, ...]:
    """A Plan line's tags in Obsidian's spelling (``#bot/<slug>``, ``#garden``): Plan lines are Obsidian Tasks."""
    tags = (obsidian_tag(tag) for tag in bot_record_tags(ctx, None, raw_topics))
    return tuple(f"#{tag}" for tag in tags if tag)
