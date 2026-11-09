"""@bot in a bot's chat: your message names another of your bots, and that bot gets it as a handoff.

``chat_mentions`` finds the user's other bots named in a message (exact name, case-insensitive, longest name first;
the chat's own bot, unknown names, ``@everyone`` and e-mail addresses are ignored), in text order and at most
``MENTIONS_PER_MESSAGE_MAX``. A message that *starts* with a mention is meant for those bots only.

``MentionRouter`` hands the message to each named bot through ``TurnRunner.hand_off`` (the ``ask_bot`` path: a
``handoff`` work item in the bot's "From <chat bot>" thread) and posts the answer back into the chat the user wrote
in, written by the bot that answered, so the chat's own bot later reads it as a teammate's words. You typed the
task, so it is never tainted; the answer keeps the taint its run had. The asker is ``MENTION_ASKER``, never a bot
id, so the chat's own bot is not counted as waiting and nothing up a handoff chain is refused for it."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial

from roost.bots.models import Bot
from roost.constants import HANDOFF_PREVIEW_CHARS, MENTIONS_PER_MESSAGE_MAX
from roost.events.hub import EventHub
from roost.talk.notices import post_notice, preview
from roost.talk.store import Message, MessageRole, TalkStore, message_out
from roost.work.models import HandoffResult, WorkDraft, WorkKind

logger = logging.getLogger(__name__)

MENTION_ASKER = "you"     # the asker of a mention handoff: the user, never a bot id
OFF_DUTY_TEXT = "{name} is off duty."
EMPTY_ANSWER_TEXT = "{name} finished without an answer."
UNANSWERED_TEXT = {
    "timeout": "{name} did not answer in time. Its answer will appear in its own chat.",
    "dropped": "{name} stopped before answering.",
    "failed": "{name} ran into a problem and did not answer.",
    "refused": "{name} is busy with this chat's work. Try again in a moment.",
}


@dataclass(frozen=True)
class ChatMentions:
    bot_ids: tuple[str, ...] = ()
    addressed_only: bool = False      # the message starts with a mention: the chat's own bot is not asked


def mention_origin(chat_bot_name: str) -> str:
    return f"you, in {chat_bot_name}'s chat"


def _pattern(names: Sequence[str]) -> re.Pattern[str]:
    """``@name`` for any of ``names``, longest first so "@Scout Two" never reads as "@Scout"."""
    choices = "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    return re.compile(rf"(?<![\w])@({choices})(?![\w\-])(?!\.\w)", re.IGNORECASE)


def chat_mentions(text: str, team: Sequence[Bot], chat_bot_id: str) -> ChatMentions:
    """The other bots of ``team`` that ``text`` names, in text order. ``team`` is only the user's own bots."""
    others = {bot.name.casefold(): bot.id for bot in team if bot.id != chat_bot_id}
    if not others:
        return ChatMentions()
    stripped = text.lstrip()
    matches = tuple(_pattern(tuple(others)).finditer(stripped))
    found = tuple(dict.fromkeys(others[match.group(1).casefold()] for match in matches))
    if not found:
        return ChatMentions()
    return ChatMentions(bot_ids=found[:MENTIONS_PER_MESSAGE_MAX], addressed_only=matches[0].start() == 0)


class MentionRouter:
    def __init__(self, talk: TalkStore, events: EventHub, turns) -> None:
        self._talk = talk
        self._events = events
        self._turns = turns
        self._tasks: frozenset["asyncio.Task[None]"] = frozenset()
        self._thread_lock = asyncio.Lock()

    async def route(self, user_id: str, chat_bot: Bot, thread_id: str, text: str, targets: Sequence[Bot]) -> None:
        """Start one ask per target and return at once; each answer arrives in ``thread_id`` later."""
        for target in targets:
            task = asyncio.create_task(self._ask_logged(user_id, chat_bot, thread_id, text, target))
            self._tasks = self._tasks | {task}
            task.add_done_callback(self._forget)

    async def wait(self) -> None:
        """Wait until every open ask has finished (tests, and a clean shutdown)."""
        while self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()

    def _forget(self, task: "asyncio.Task[None]") -> None:
        self._tasks = self._tasks - {task}

    async def _ask_logged(self, user_id: str, chat_bot: Bot, thread_id: str, text: str, target: Bot) -> None:
        try:
            await self._ask(user_id, chat_bot, thread_id, text, target)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Mention handoff to bot %s failed", target.id)
            await post_notice(self._talk, self._events, user_id, thread_id,
                              UNANSWERED_TEXT["failed"].format(name=target.name))

    async def _ask(self, user_id: str, chat_bot: Bot, thread_id: str, text: str, target: Bot) -> None:
        if target.off_duty:
            await post_notice(self._talk, self._events, user_id, thread_id, OFF_DUTY_TEXT.format(name=target.name))
            return
        result: HandoffResult = await self._turns.hand_off(
            user_id, MENTION_ASKER, target.id, prepare=partial(self._hand_over, user_id, chat_bot, thread_id, text,
                                                                target))
        await self._answer(user_id, thread_id, target, result)

    async def _hand_over(self, user_id: str, chat_bot: Bot, thread_id: str, text: str, target: Bot) -> WorkDraft:
        async with self._thread_lock:   # two asks to one bot share one "From" thread
            peer = await self._talk.find_or_create_peer_thread(
                user_id, target.id, chat_bot.id, title=f"From {chat_bot.name}")
        await self._post(user_id, thread_id, "activity", f"You → {target.name}: {preview(text, HANDOFF_PREVIEW_CHARS)}")
        task_line = await self._post(user_id, peer.id, "user", f"You → {target.name}: {text}")
        return WorkDraft(bot_id=target.id, thread_id=peer.id, kind=WorkKind.HANDOFF,
                         origin=mention_origin(chat_bot.name), body=text, tainted=False, depth=1,
                         message_id=task_line.id)

    async def _answer(self, user_id: str, thread_id: str, target: Bot, result: HandoffResult) -> None:
        if result.status != "done":
            await post_notice(self._talk, self._events, user_id, thread_id,
                              UNANSWERED_TEXT[result.status].format(name=target.name))
            return
        if not result.text.strip():
            await post_notice(self._talk, self._events, user_id, thread_id, EMPTY_ANSWER_TEXT.format(name=target.name))
            return
        message = await self._talk.add_message(user_id, thread_id, role="bot", body=result.text,
                                               tainted=result.tainted, kind="text", author_bot_id=target.id)
        await self._publish(user_id, thread_id, message)

    async def _post(self, user_id: str, thread_id: str, role: MessageRole, body: str) -> Message:
        message = await self._talk.add_message(user_id, thread_id, role=role, body=body, tainted=False, kind="handoff")
        await self._publish(user_id, thread_id, message)
        return message

    async def _publish(self, user_id: str, thread_id: str, message: Message) -> None:
        await self._events.publish(user_id, {"type": "message", "thread_id": thread_id, "message": message_out(message)})
