"""Assigning a task to a bot (design 2026-10-20 P5): your own message in that bot's main chat.

Not a ``handoff`` (bot to bot, dropped on a restart): it is the same message ``POST
/api/threads/{id}/messages`` would queue, so the run goes through the same gate, caps and Ask cards, and
the task is untainted because you typed it."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from roost.bots.models import Bot
from roost.timezones import local_tz
from roost.tasks.models import Task
from roost.work.models import ORIGIN_YOU, WorkDraft, WorkKind

ASSIGN_MESSAGE_TEXT = "Please take this task: “{title}”{due}."
_DAY_FORMAT = "%a %d %b"
_MOMENT_FORMAT = "%a %d %b %H:%M"


def _due_phrase(task: Task) -> str:
    if not task.due_date:
        return ""
    try:
        moment = datetime.fromisoformat(task.due_date)
    except ValueError:
        return ""
    if len(task.due_date) == len("YYYY-MM-DD"):
        return f" (due {moment.strftime(_DAY_FORMAT)})"
    return f" (due {moment.astimezone(local_tz()).strftime(_MOMENT_FORMAT)})"


def assign_message(task: Task) -> str:
    return ASSIGN_MESSAGE_TEXT.format(title=task.title, due=_due_phrase(task))


async def assign_task(app_state: Any, user_id: str, task: Task, bot: Bot) -> None:
    """Post your message in ``bot``'s main chat and queue it as one of your own messages."""
    thread, _ = await app_state.talk.ensure_main_thread(user_id, bot.id)
    text = assign_message(task)
    message = await app_state.talk.add_message(user_id, thread.id, role="user", body=text)
    await app_state.turns.submit(user_id, WorkDraft(
        bot_id=bot.id, thread_id=thread.id, kind=WorkKind.MESSAGE, origin=ORIGIN_YOU, body=text,
        message_id=message.id,
    ))
