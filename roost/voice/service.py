"""``VoiceSettingsService``: the one door a bot's voice settings change through — the Info tab's save
(``PUT /api/bots/{id}/voice``) and the bot's own ``set_my_voice`` alike. It merges a ``VoicePatch`` onto the stored
settings, writes them and publishes the ``bot_updated`` frame open clients refresh the bot from (and a call in
progress reads its next part's voice from). Another user's bot, or no such bot, is ``None``."""

from __future__ import annotations

from typing import Protocol

from roost.bots.models import Bot
from roost.bots.service import bot_out
from roost.voice.constants import VoiceSettings
from roost.voice.settings import VoicePatch, apply_patch


class _Bots(Protocol):
    async def get(self, user_id: str, bot_id: str) -> Bot | None: ...

    async def set_voice(self, user_id: str, bot_id: str, voice: VoiceSettings) -> Bot | None: ...


class _Events(Protocol):
    async def publish(self, user_id: str, frame: dict) -> int: ...


class VoiceSettingsService:
    def __init__(self, bots: _Bots, events: _Events) -> None:
        self._bots = bots
        self._events = events

    async def save(self, user_id: str, bot_id: str, patch: VoicePatch, *, activity: str | None = None) -> Bot | None:
        """The bot with the patch applied, stored and published; ``None`` when the bot is not this user's.
        ``activity`` is the bot's status word for the frame (the route knows it; a tool passes none)."""
        bot = await self._bots.get(user_id, bot_id)
        if bot is None:
            return None
        updated = await self._bots.set_voice(user_id, bot_id, apply_patch(bot.voice, patch))
        if updated is None:
            return None
        await self._events.publish(user_id, {"type": "bot_updated", "bot": bot_out(updated, activity)})
        return updated
