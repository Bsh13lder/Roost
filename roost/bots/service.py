"""Serialization boundary between the bots domain model and the wire
shape the gateway returns (``BotOut``, see the contract's HTTP API
table).

Kept separate from ``roost/gateway/routes/bots.py`` so any other place
that needs to emit a ``BotOut`` — a later task's ``bot_status`` /
``snapshot`` WS event payloads (``roost/events/hub.py``), for one —
imports this one function instead of re-deriving the field list.
"""

from __future__ import annotations

from typing import Any, Mapping

from roost.approvals.models import locked_topics
from roost.bots.look import avatar_dict
from roost.bots.models import Bot
from roost.llm.registry import model_label, resolve_bot_model
from roost.voice.settings import voice_dict


def _picture_url(bot: Bot) -> str | None:
    """Where the web reads the bot's picture (roost/gateway/routes/bot_picture.py), versioned by it."""
    return None if bot.avatar.picture is None else f"/api/bots/{bot.id}/picture?v={bot.avatar.picture}"


def bot_out(bot: Bot, activity: str | None, seen_labels: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Build the ``BotOut`` wire shape for ``bot``.

    ``activity`` is passed in rather than looked up here — callers read
    it from their own ``ActivityBoard`` instance (``app.state.
    activity_board``), keeping this function a pure, dependency-free
    mapping. ``model`` is what the bot runs on: its stored choice (the routes only store a pickable
    one) or the default; ``seen_labels`` names a model the daily check found.
    """
    chosen = resolve_bot_model(bot.model_override, frozenset({bot.model_override}) if bot.model_override else frozenset())
    return {
        "id": bot.id,
        "name": bot.name,
        "job": bot.job,
        "instructions": bot.instructions,
        "avatar": {**avatar_dict(bot.avatar), "picture": _picture_url(bot)},
        "template_id": bot.template_id,
        "status": bot.status.value,
        "activity": activity,
        "model_override": bot.model_override,
        "model": chosen,
        "model_label": model_label(chosen, seen_labels),
        "effort": bot.effort,
        "created_at": bot.created_at,
        "updated_at": bot.updated_at,
        "off_duty": bot.off_duty,
        "is_primary": bot.is_primary,
        "notify": bot.notify,
        "approval": {"mode": bot.approval.mode, "ask_topics": sorted(bot.approval.ask_topics),
                     "locked_topics": locked_topics(), "auto_review": bot.approval.auto_review},
        "group": bot.group,
        "computer": bot.computer,
        "full_limit_until": bot.full_limit_until,
        "workspace_internet": bot.workspace_internet,
        "voice": voice_dict(bot.voice),
        "pinned": bot.pinned or bot.is_primary,   # the main bot is pinned by default
        "pinned_at": bot.pinned_at,
        # S1 D2: roles gate nothing. Always empty for one release, then removed.
        "roles": [],
    }
