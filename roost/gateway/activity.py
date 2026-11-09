"""What a bot is doing right now, in words, for the wire (``GET /api/bots`` and the live snapshot)."""

from __future__ import annotations

from typing import Any

from roost.bots.models import Bot, BotStatus
from roost.stuck.texts import stuck_status_line


async def bot_activity(state: Any, user_id: str, bot: Bot) -> str | None:
    """A Stuck bot's words come from its open card, so a reload and a reconnect keep the reason."""
    if bot.status is BotStatus.STUCK:
        card = await state.stuck.open_for_bot(user_id, bot.id)
        if card is not None:
            return stuck_status_line(card)
    return state.activity_board.get(bot.id)
