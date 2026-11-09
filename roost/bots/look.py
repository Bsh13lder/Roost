"""How a bot looks (look & feel redesign V1, "Boxbot"): the avatar as the wire and the cards carry
it, and the colour a new bot takes when nobody chose one. The gateway stores a shape as sent, an
old bird shape included; only the web draws, so the bird-to-head table lives there
(web/src/components/robot/look.ts)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from roost.bots.models import Avatar
from roost.constants import BOT_DEFAULT_COLORS


def avatar_dict(avatar: Avatar) -> dict[str, Any]:
    """An avatar on the wire and in a card: its shape, colour, badge and screen, and its role when it has
    one (an avatar without a role counts as general, so an old client sees the shape it always saw)."""
    data: dict[str, Any] = {"shape": avatar.shape, "color": avatar.color, "badge": avatar.badge,
                            "screen": avatar.screen}
    return data if avatar.role is None else {**data, "role": avatar.role}


def next_bot_color(used: Iterable[str]) -> str:
    """The first default colour no teammate wears (any case). Once all are worn they come round again."""
    worn = [color.lower() for color in used]
    free = next((color for color in BOT_DEFAULT_COLORS if color not in worn), None)
    return free if free is not None else BOT_DEFAULT_COLORS[len(worn) % len(BOT_DEFAULT_COLORS)]
