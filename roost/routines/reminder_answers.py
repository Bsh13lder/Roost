"""A task reminder card's answer (Done · Failed · Reschedule · Skip), kept on its Report.

The card is a ``report`` message whose ``ReportBody`` names a ``task_id``. Done, Failed and Reschedule change the
task through the task routes first; the client then records the answer here, and Skip only records it. The answer
lives in the Report's own sealed body (``answer``, ``answer_due``, ``answered_at``), so every screen, the web and
the phone, shows the same folded card after a reload or a restart. No schema change: the body is JSON already."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from roost.constants import REMINDER_DUE_MAX, REMINDER_DUE_PATTERN
from roost.routines.models import ReminderAnswer, ReportBody
from roost.talk.store import Message, TalkStore

REPORT_KIND = "report"
REMINDER_SOURCE = "reminder"
DUE_ONLY_ON_RESCHEDULE_TEXT = "Only a Reschedule carries a new due date."


class ReminderAnswerIn(BaseModel):
    """``PUT …/reminder-answer``: the answer, and for a Reschedule the new due (``None``: the task has no date)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    answer: ReminderAnswer
    due: str | None = Field(default=None, max_length=REMINDER_DUE_MAX, pattern=REMINDER_DUE_PATTERN)

    @model_validator(mode="after")
    def _due_needs_reschedule(self) -> ReminderAnswerIn:
        if self.due is not None and self.answer != "rescheduled":
            raise ValueError(DUE_ONLY_ON_RESCHEDULE_TEXT)
        return self


def _reminder_body(message: Message | None, thread_id: str) -> ReportBody | None:
    if message is None or message.thread_id != thread_id or message.kind != REPORT_KIND:
        return None
    try:
        body = ReportBody.model_validate_json(message.body)
    except ValidationError:
        return None
    return body if body.source == REMINDER_SOURCE and body.task_id else None


async def reminder_answer(talk: TalkStore, user_id: str, thread_id: str, message_id: str,
                          answer: ReminderAnswer, due: str | None) -> Message | None:
    """Store ``answer`` on the user's reminder Report in ``thread_id`` and return the updated message. ``None``:
    no such reminder of this user's in this thread (another user's id reads the same). A later answer replaces an
    earlier one."""
    message = await talk.get_message(user_id, message_id)
    body = _reminder_body(message, thread_id)
    if message is None or body is None:
        return None
    answered = body.model_copy(update={
        "answer": answer, "answer_due": due if answer == "rescheduled" else None,
        "answered_at": datetime.now(UTC).isoformat(timespec="seconds"),
    })
    text = answered.model_dump_json()
    if not await talk.replace_body(user_id, message.id, text):
        return None
    return replace(message, body=text)
