"""The contact details you gave a bot yourself (owner, 2026-11-03): typing one of them never asks.

They come from three places you wrote: your own messages in this chat (the caller passes them, read by
``text_source.your_messages``), the bot's own instructions, and the memories it reads (About you and its own) that no
run saved after reading outside content. Every query names ``user_id``; a bot that isn't yours adds nothing."""

from __future__ import annotations

from typing import Iterable

from roost.computer_use.contact import contact_details
from roost.config import Config


async def _instructions(config: Config, user_id: str, bot_id: str) -> str:
    from roost.bots.store import BotStore   # here: the bot store imports the approvals the gate imports

    bot = await BotStore(config).get(user_id, bot_id) if bot_id else None
    return bot.instructions if bot is not None else ""


async def _memories(config: Config, user_id: str, bot_id: str) -> tuple[str, ...]:
    from roost.memory.store import MemoryStore

    found = await MemoryStore(config).list_scopes(user_id, bot_id)
    return tuple(memory.text for memory in found if not memory.tainted)


async def allowed_contacts(config: Config, user_id: str, bot_id: str, messages: Iterable[str]) -> frozenset[str]:
    """Every email address and phone number in your messages, the bot's instructions and its clean memories."""
    texts = (*messages, await _instructions(config, user_id, bot_id), *await _memories(config, user_id, bot_id))
    return frozenset(detail for text in texts for detail in contact_details(text))
