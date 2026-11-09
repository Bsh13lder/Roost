"""Reports: a routine's result as a ``report`` message in the bot's main chat, and the quiet lines around it.

A Report's body is ``ReportBody`` JSON; the chat draws its text as the bot's own message with a quiet footer
(2026-10-26, "like Grok") and the model reads it back as text. Past
``REPORTS_PER_BOT_PER_HOUR`` a Report is not posted: one quiet line in the run-log thread says so (the reply is
already in that log). A failure Report is always posted (``always=True``)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from itertools import dropwhile

from roost.constants import (
    REPORT_HEADLINE_MAX, REPORT_NARRATION_LINE_MAX_CHARS, REPORT_NARRATION_WORD_ENDINGS, REPORT_QUIET_SENTINEL,
    REPORT_TEXT_MAX_CHARS, REPORTS_PER_BOT_PER_HOUR, ROUTINE_NAME_MAX,
)
from roost.events.hub import EventHub
from roost.routines.models import ReportBody, RoutineRun
from roost.routines.runs import RoutineRunStore, utc_now
from roost.routines.texts import FOLDED_LINE, EMPTY_REPLY_TEXT, activity_line, clip
from roost.talk.store import Message, TalkStore, message_out

_HOUR = timedelta(hours=1)
_ON_IT = "on it"      # chat_feel.FIRST_LINE_RULE's opener


def _is_on_it(line: str) -> bool:
    return line.strip().lower().startswith(_ON_IT)


def headline_of(reply: str, fallback: str) -> str:
    """The reply's first non-empty line after its "On it: …" openers, Markdown ``#`` removed, cut to the
    headline limit."""
    lines = [text for line in reply.splitlines() if (text := line.strip().lstrip("#").strip())]
    rest = list(dropwhile(_is_on_it, lines))
    return clip((rest or lines or [fallback])[0], REPORT_HEADLINE_MAX)


def without_on_it(reply: str) -> str:
    """The reply without the first-line rule's leading "On it: …" lines (a bot may say it again after a tool
    step, 2026-10-28), unless such lines are all there is (the chat shows a Report as a plain bot message,
    2026-10-26)."""
    text = reply.strip()
    rest = "\n".join(dropwhile(lambda line: not line.strip() or _is_on_it(line), text.splitlines()))
    return rest.strip() or text


def report_body(
    reply: str, *, name: str, routine_id: str, run_id: str, log_thread_id: str, tainted: bool,
) -> ReportBody:
    text = without_on_it(reply)[:REPORT_TEXT_MAX_CHARS] or EMPTY_REPLY_TEXT
    return ReportBody(
        source="routine", headline=headline_of(reply, name), text=text, routine_id=routine_id, run_id=run_id,
        log_thread_id=log_thread_id, routine_name=clip(name, ROUTINE_NAME_MAX), tainted=tainted)


def with_headline(headline: str, text: str) -> str:
    """A Report the server wrote itself (a failure, a missed slot): its headline as the first line, since the chat
    shows only the text."""
    return clip(f"{headline}\n\n{text}" if text.strip() else headline, REPORT_TEXT_MAX_CHARS)


def _sentinel(line: str) -> bool:
    """The quiet sentinel, forgiving Markdown around it (``**[nothing new]**``, ``\\[nothing new\\]``), case
    and a closing full stop."""
    bare = re.sub(r"[*_`\\]", "", line).strip().rstrip(".").strip().lower()
    return bare == REPORT_QUIET_SENTINEL


def _narration(line: str) -> bool:
    """A short line that only says what the bot is checking: one sentence whose first word is a gerund
    ("Checking the Deduci chat.", "Revisando el chat…"). A line with news in it is never this."""
    words = line.split()
    one_sentence = not re.search(r"[.!?…]\s+\S", line)
    return (bool(words) and len(line) <= REPORT_NARRATION_LINE_MAX_CHARS and one_sentence
            and words[0].lower().strip(",.:").endswith(REPORT_NARRATION_WORD_ENDINGS))


def _lines(reply: str) -> list[str]:
    """The reply's non-empty lines, with a sentinel at the end of a line split off onto its own."""
    lines: list[str] = []
    for raw in (line.strip() for line in reply.splitlines()):
        head, cut, _ = raw.lower().rpartition(REPORT_QUIET_SENTINEL)
        head = head.rstrip("*_`\\ ")
        if cut and head and not _sentinel(raw) and _sentinel(raw[len(head):]):
            lines += [raw[:len(head)].strip(), raw[len(head):]]
        elif raw:
            lines.append(raw)
    return [line for line in lines if line]


def is_quiet(reply: str) -> bool:
    """The sentinel, alone or after the first-line rule's "On it: …" lines (one, or the same said again after a
    tool step, 2026-10-28) and lines that only say what the bot is checking (2026-11-07)."""
    lines = _lines(reply)
    return bool(lines) and _sentinel(lines[-1]) and all(_is_on_it(x) or _narration(x) for x in lines[:-1])


async def post_routine_note(
    talk: TalkStore, events: EventHub, user_id: str, thread_id: str, bot_id: str, verb: str, name: str,
    *, routine_id: str | None = None, text: str | None = None,
) -> Message:
    """A quiet activity line ("Created routine · {name}") in ``thread_id``. UI only: it never reaches the model."""
    body = json.dumps({"routine_id": routine_id, "verb": verb, "name": name, "text": text or activity_line(verb, name)})
    message = await talk.add_message(user_id, thread_id, "activity", body, kind="routine_note", author_bot_id=bot_id)
    await events.publish(user_id, {"type": "message", "thread_id": thread_id, "message": message_out(message)})
    return message


async def post_report(
    talk: TalkStore, events: EventHub, user_id: str, bot_id: str, body: ReportBody,
    *, runs: RoutineRunStore, now: datetime | None = None, always: bool = False,
) -> Message | None:
    """Post ``body`` as a Report in the bot's main chat. ``None`` when the hourly cap folded it into the log."""
    moment = now if now is not None else utc_now()
    body = body.model_copy(update={"bot_id": bot_id})      # the bot posting it, whatever the body said
    if not always and await runs.recent_reports(user_id, bot_id, moment - _HOUR) >= REPORTS_PER_BOT_PER_HOUR:
        await _fold(talk, events, user_id, bot_id, body)
        return None
    thread, _created = await talk.ensure_main_thread(user_id, bot_id)
    message = await talk.add_message(
        user_id, thread.id, "bot", body.model_dump_json(), tainted=body.tainted, kind="report", author_bot_id=bot_id)
    await events.publish(user_id, {"type": "message", "thread_id": thread.id, "message": message_out(message)})
    return message


async def _fold(talk: TalkStore, events: EventHub, user_id: str, bot_id: str, body: ReportBody) -> None:
    if body.log_thread_id is None:
        return
    await post_routine_note(talk, events, user_id, body.log_thread_id, bot_id, "folded", body.headline,
                            routine_id=body.routine_id, text=FOLDED_LINE)


async def publish_run(events: EventHub, user_id: str, run: RoutineRun) -> None:
    await events.publish(user_id, {
        "type": "routine_run", "routine_id": run.routine_id, "run_id": run.id, "state": run.state})
