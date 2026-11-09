"""``InstructionChanges``: a bot changes one section of its own instructions in your own chat, and you can Undo it
(owner, 2026-10-23, A2).

``change`` replaces the named section (the five of ``roost/bots/instruction_sections.py``), writes the result by
compare-and-swap against the instructions it read, and posts an ``instruction_change`` line (role ``activity``,
never replayed to a model) whose sealed body keeps the section, the text before and the text after. ``undo``
restores the text before, again by compare-and-swap against the text after, so an Undo never overwrites a newer
change; the line is then marked ``undone``. Another user's line, or a message that is not such a line, reads as no
such line (``None``). Where a run may call ``change`` is the tool's rule (``change_tools.py``)."""

from __future__ import annotations

import json
from dataclasses import dataclass

from roost.bots.instruction_sections import (
    TITLES, parse_sections, render_sections, section_key, structure_instructions,
)
from roost.bots.instructions_swap import swap_instructions
from roost.bots.redact import find_secret_kinds
from roost.bots.store import BotStore
from roost.config import Config
from roost.constants import MAX_BOT_INSTRUCTIONS_LENGTH
from roost.events.hub import EventHub
from roost.instruction_proposals.texts import (
    CHANGE_TOO_LONG, CHANGED_SINCE, NO_CHANGE, NO_SUCH_BOT, SECRET, STALE, UNDO_SPENT,
)
from roost.talk.store import Message, TalkStore, message_out

CHANGE_KIND = "instruction_change"
_ACTIVITY_ROLE = "activity"


class ChangeRefused(ValueError):
    """A change that can't be made; the text is a plain sentence for the bot."""


class UndoRefused(Exception):
    """An Undo that can't happen (HTTP 409); the text is a plain sentence for the user."""


@dataclass(frozen=True)
class ChangeRequest:
    user_id: str
    bot_id: str
    thread_id: str
    section: str          # a section title or one of its names
    new_text: str
    why: str


def replace_section(instructions: str, key: str, text: str, *, name: str | None, job: str | None) -> str:
    """The instructions in their five sections with ``key``'s text replaced; the other sections stay as they were."""
    sections = parse_sections(structure_instructions(instructions, name=name, job=job))
    rendered = render_sections({**sections, key: text.strip()})
    if len(rendered) > MAX_BOT_INSTRUCTIONS_LENGTH:
        raise ChangeRefused(CHANGE_TOO_LONG)
    return structure_instructions(rendered, name=name, job=job)


class InstructionChanges:
    def __init__(self, bots: BotStore, talk: TalkStore, events: EventHub, config: Config) -> None:
        self._bots = bots
        self._talk = talk
        self._events = events
        self._config = config

    async def change(self, request: ChangeRequest) -> tuple[str, Message]:
        """Write the new section and post its line: (the section's title, the line). ``ChangeRefused`` otherwise."""
        key = section_key(request.section)
        bot = await self._bots.get(request.user_id, request.bot_id)
        if bot is None:
            raise ChangeRefused(NO_SUCH_BOT)
        if key is None:
            raise ChangeRefused(f"No section is called “{request.section}”.")
        kinds = find_secret_kinds(request.new_text) + find_secret_kinds(request.why)
        if kinds:
            raise ChangeRefused(SECRET.format(kinds=" or ".join(dict.fromkeys(kinds))))
        after = replace_section(bot.instructions, key, request.new_text, name=bot.name, job=bot.job)
        if after == bot.instructions:
            raise ChangeRefused(NO_CHANGE)
        if not await swap_instructions(self._config, request.user_id, bot.id, bot.instructions, after):
            raise ChangeRefused(STALE)
        title = TITLES[key]
        body = json.dumps({"section": title, "before": bot.instructions, "after": after, "why": request.why,
                           "undone": False})
        line = await self._talk.add_message(request.user_id, request.thread_id, _ACTIVITY_ROLE, body,
                                            kind=CHANGE_KIND, author_bot_id=bot.id)
        await self._events.publish(request.user_id, {"type": "message", "thread_id": request.thread_id,
                                                     "message": message_out(line)})
        return title, line

    async def undo(self, user_id: str, message_id: str) -> Message | None:
        """Restore the text the change replaced. ``None``: no such line of yours. ``UndoRefused``: spent, or the
        instructions changed since."""
        line = await self._talk.get_message(user_id, message_id)
        data = _change_data(line)
        if line is None or data is None or line.author_bot_id is None:
            return None
        if data.get("undone"):
            raise UndoRefused(UNDO_SPENT)
        if not await swap_instructions(self._config, user_id, line.author_bot_id, data["after"], data["before"]):
            raise UndoRefused(CHANGED_SINCE)
        spent = json.dumps({**data, "undone": True})
        await self._talk.replace_body(user_id, line.id, spent)
        return await self._talk.get_message(user_id, line.id)


def _change_data(line: Message | None) -> dict | None:
    if line is None or line.kind != CHANGE_KIND or line.role != _ACTIVITY_ROLE:
        return None
    try:
        data = json.loads(line.body)
    except ValueError:
        return None
    ok = isinstance(data, dict) and isinstance(data.get("before"), str) and isinstance(data.get("after"), str)
    return data if ok else None
