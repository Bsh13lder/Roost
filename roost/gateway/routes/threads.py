"""Threads/messages HTTP API — ``GET/POST /api/bots/{bot_id}/threads``,
``GET/POST /api/threads/{thread_id}/messages`` (see the contract's HTTP
API table).

Reads ``BotStore``/``TalkStore``/the ``TurnStarter`` hook off
``request.app.state`` (same per-app-instance pattern as
``roost/gateway/routes/bots.py``).

Foreign-id handling: ``/api/bots/{bot_id}/threads`` looks the bot up via
``BotStore.get(user.id, bot_id)`` first — a foreign or unknown bot id is
a 404 before ``TalkStore`` is ever touched (see ``TalkStore.create_thread``'s
docstring for why that check belongs here, not in the store).
``/api/threads/{thread_id}/messages`` instead looks the *thread* up via
``TalkStore.get_thread(user.id, thread_id)``, which is already scoped by
``user_id`` — a foreign or unknown thread id is a 404 the same way.

``POST /api/threads/{thread_id}/messages`` stores the user's message and
queues it as a work item for the thread's bot (``TurnRunner.submit``) —
the reply arrives over the event stream.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from roost.approvals.typed_answer import answer_by_words
from roost.constants import (
    CHAT_MEDIA_PER_MESSAGE, MAX_MESSAGE_TEXT_LENGTH, MAX_THREAD_TITLE_LENGTH, MESSAGE_ID_MAX, MIN_MESSAGE_TEXT_LENGTH,
)
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.memory.models import memory_out
from roost.memory.offers import accept_offer
from roost.memory.service import MemoryRefused
from roost.routines.reminder_answers import ReminderAnswerIn, reminder_answer
from roost.stuck.typed_reply import StuckReplyPorts, submit_message
from roost.talk.fresh_start import post_fresh_start
from roost.talk.mentions import chat_mentions
from roost.talk.replies import NO_SUCH_REPLY_TEXT, NoSuchReply, resolve_reply
from roost.talk.reactions import NOT_FOUND_TEXT, REACTION_KIND, ReactionIn, reaction_body
from roost.talk.store import message_out, thread_out
from roost.voice.constants import VOICE_CORRECT_FIXES_MAX, VOICE_CORRECT_TEXT_CHARS_MAX
from roost.voice.correct import FixIn
from roost.work.models import ORIGIN_YOU, WorkDraft, WorkKind

threads_router = APIRouter(tags=["threads"])
logger = logging.getLogger(__name__)
EMPTY_MESSAGE_TEXT = "Write a message or attach a picture."
TOO_MANY_PICTURES_TEXT = f"Attach at most {CHAT_MEDIA_PER_MESSAGE} pictures to one message."
BAD_PICTURES_TEXT = "Those pictures can't be sent: upload them again."


class ThreadCreate(BaseModel):
    title: str | None = Field(default=None, max_length=MAX_THREAD_TITLE_LENGTH)


class RememberIn(BaseModel):
    """Remember it carries nothing: the line itself says what to save."""
    model_config = ConfigDict(extra="forbid")


class MessageCreate(BaseModel):
    # Chat pictures (owner, 2026-11-05): with ``media_ids`` the text may be empty; without, it needs a character.
    text: str = Field(default="", max_length=MAX_MESSAGE_TEXT_LENGTH)
    media_ids: list[str] = Field(default_factory=list)
    # Replies: the message of this thread this one answers; the server makes the quote (roost/talk/replies.py).
    reply_to: str | None = Field(default=None, min_length=1, max_length=MESSAGE_ID_MAX)
    # Voice call (§3): a spoken turn; it beats the thread's call before the message is queued.
    call: bool = False
    # Voice §4: the text came from the voice service (a call turn, or a dictation sent unedited). With the bot's
    # Correct what I say on, a background job posts an ``english_fix`` line; the bot still reads the original words.
    spoken: bool = False
    # Voice tuning D3: the composer already showed the correction (``POST /api/voice/correct``): ``heard`` is the
    # raw transcript and ``fixes`` what it marked; the line is stored at once, with no second model call.
    heard: str | None = Field(default=None, max_length=VOICE_CORRECT_TEXT_CHARS_MAX)
    fixes: list[FixIn] = Field(default_factory=list, max_length=VOICE_CORRECT_FIXES_MAX)


# ---------------------------------------------------------------------------
# /api/bots/{bot_id}/threads
# ---------------------------------------------------------------------------

@threads_router.get("/api/bots/{bot_id}/threads")
async def list_threads(bot_id: str, request: Request, user: CurrentUser):
    bot = await request.app.state.bots.get(user.id, bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    threads = await request.app.state.talk.list_threads(user.id, bot_id)
    return [thread_out(t) for t in threads]


@threads_router.post("/api/bots/{bot_id}/threads", status_code=201, dependencies=[RequireOrigin])
async def create_thread(bot_id: str, body: ThreadCreate, request: Request, user: CurrentUser):
    bot = await request.app.state.bots.get(user.id, bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    thread = await request.app.state.talk.create_thread(user.id, bot_id, title=body.title)
    return thread_out(thread)


@threads_router.post("/api/bots/{bot_id}/chat", dependencies=[RequireOrigin])
async def open_chat(bot_id: str, request: Request, user: CurrentUser):
    """The bot's one chat (the thread last talked in), made when it has none."""
    bot = await request.app.state.bots.get(user.id, bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    thread, _ = await request.app.state.talk.ensure_main_thread(user.id, bot_id)
    return thread_out(thread)


# ---------------------------------------------------------------------------
# /api/threads/{thread_id}/messages
# ---------------------------------------------------------------------------

@threads_router.get("/api/threads/{thread_id}/messages")
async def list_messages(thread_id: str, request: Request, user: CurrentUser, after: int = 0):
    """``after`` omitted (0, the default): the latest page (Final
    review, finding 8) -- a fresh page load otherwise got the OLDEST
    page forever once a thread passed the limit, so a reload of Talk
    never showed anything posted since. A real cursor (``after > 0``)
    still pages forward from it, unchanged."""
    talk = request.app.state.talk
    thread = await talk.get_thread(user.id, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if after:
        messages = await talk.list_messages(user.id, thread_id, after_seq=after)
    else:
        messages = await talk.list_latest_messages(user.id, thread_id)
    media = await request.app.state.media.for_messages(user.id, [m.id for m in messages])
    return [message_out(m, media.get(m.id, ())) for m in messages]


async def _check_media(state: Any, user_id: str, thread_id: str, body: MessageCreate) -> None:
    """A message needs words or pictures (no words and no pictures stays the old 422); 400 for more than
    ``CHAT_MEDIA_PER_MESSAGE`` pictures or any that is not a loose one of yours in this thread."""
    if not body.media_ids and len(body.text) < MIN_MESSAGE_TEXT_LENGTH:
        raise HTTPException(status_code=422, detail=EMPTY_MESSAGE_TEXT)
    if len(body.media_ids) > CHAT_MEDIA_PER_MESSAGE:
        raise HTTPException(status_code=400, detail=TOO_MANY_PICTURES_TEXT)
    if body.media_ids and not await state.media.usable(user_id, thread_id, body.media_ids):
        raise HTTPException(status_code=400, detail=BAD_PICTURES_TEXT)


async def _with_media(state: Any, user_id: str, thread_id: str, message: Any, media_ids: list[str]) -> list[Any]:
    """Join the pictures to the stored message and answer its ``media`` list."""
    if not media_ids:
        return []
    if not await state.media.attach(user_id, thread_id, message.id, media_ids):
        logger.warning("Pictures for message %s were taken meanwhile", message.id)
    return (await state.media.for_messages(user_id, (message.id,))).get(message.id, [])


@threads_router.post("/api/threads/{thread_id}/messages", status_code=202, dependencies=[RequireOrigin])
async def post_message(thread_id: str, body: MessageCreate, request: Request, user: CurrentUser):
    """Store your message and queue it for the thread's bot. In a bot's chat, ``@Name`` of another of your bots
    also hands the message to that bot (``roost/talk/mentions.py``), and a message that starts with a mention goes
    to the named bots only. ``mentioned`` lists the bots it was handed to. A plain yes or no answers the one Ask
    card waiting in this chat instead (W1, ``answered_card``). Any other message of yours, or a reply quote of the
    card, answers the bot's open Stuck card in this chat (``answered_stuck``)."""
    state = request.app.state
    thread = await state.talk.get_thread(user.id, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if thread.kind == "room":
        raise HTTPException(status_code=409, detail="This is a room. Post in the room instead.")
    await _check_media(state, user.id, thread_id, body)
    if body.call:
        state.calls.beat(user.id, thread_id, thread.bot_id)

    reply = None
    if body.reply_to is not None:
        try:
            reply = await resolve_reply(state.talk, user.id, thread_id, body.reply_to)
        except NoSuchReply:
            raise HTTPException(status_code=404, detail=NO_SUCH_REPLY_TEXT) from None
    team = await state.bots.list(user.id) if thread.kind == "chat" else ()
    mentions = chat_mentions(body.text, team, thread.bot_id)
    # Read before submit (steer): the bot's run for this chat reads it mid-work ("steered"), a bot busy
    # elsewhere or with a routine, handoff or room run picks it up after ("queued"), a free bot starts on it.
    status = state.turns.message_status(thread.bot_id, thread_id)
    message = await state.talk.add_message(user.id, thread_id, role="user", body=body.text, reply=reply)
    media = await _with_media(state, user.id, thread_id, message, body.media_ids)
    # Every open screen (the web, the phone) shows your message at once; each one keeps it once, by id.
    await state.events.publish(user.id, {"type": "message", "thread_id": thread_id,
                                         "message": message_out(message, media)})
    if body.spoken and body.heard is not None:
        await state.english.post_fix(user.id, thread_id, thread.bot_id, message, body.heard, body.fixes)
    elif body.spoken:
        state.english.spawn(user.id, thread_id, thread.bot_id, message)   # never awaited: the run gets the original
    if thread.kind == "chat" and not mentions.bot_ids and reply is None:
        # W1: a plain yes or no answers the one Ask card waiting here, through the card's own path.
        answered = await answer_by_words(state.approvals, state.approval_service, user.id, thread_id, body.text)
        if answered is not None:
            return {"message_id": message.id, "status": "steered", "queued": False, "mentioned": [],
                    "answered_card": answered.id}
    answered_stuck = None
    if not mentions.addressed_only:
        # Your message (or a reply quote of the card) answers the bot's open Stuck card (roost/stuck/typed_reply.py).
        answered_stuck = await submit_message(_stuck_ports(state), user.id, thread, WorkDraft(
            bot_id=thread.bot_id, thread_id=thread_id, kind=WorkKind.MESSAGE,
            origin=ORIGIN_YOU, body=body.text, message_id=message.id,
        ), reply_to=body.reply_to)
    if mentions.bot_ids:
        by_id = {bot.id: bot for bot in team}
        await state.mentions.route(user.id, by_id[thread.bot_id], thread_id, body.text,
                                   tuple(by_id[bot_id] for bot_id in mentions.bot_ids))
    queued = status == "queued" and not mentions.addressed_only
    answer = {"message_id": message.id, "status": status, "queued": queued, "mentioned": list(mentions.bot_ids)}
    return {**answer, "answered_stuck": answered_stuck.id} if answered_stuck is not None else answer


def _stuck_ports(state: Any) -> StuckReplyPorts:
    return StuckReplyPorts(store=state.stuck, talk=state.talk, events=state.events, turns=state.turns,
                           control=state.control, teach=getattr(state, "teach", None))


@threads_router.put("/api/threads/{thread_id}/messages/{message_id}/reaction", dependencies=[RequireOrigin])
async def react(thread_id: str, message_id: str, body: ReactionIn, request: Request, user: CurrentUser):
    """A tapback on one of this thread's messages; ``key: null`` clears it. Stored as a ``reaction`` message and
    published as a ``message`` frame, but never replayed to the model and never queued as work."""
    talk = request.app.state.talk
    if await talk.get_thread(user.id, thread_id) is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    target = await talk.get_message(user.id, message_id)
    if target is None or target.thread_id != thread_id or target.kind == REACTION_KIND:
        raise HTTPException(status_code=404, detail=NOT_FOUND_TEXT)
    message = await talk.add_message(user.id, thread_id, "user", reaction_body(message_id, body.key), kind=REACTION_KIND)
    out = message_out(message)
    await request.app.state.events.publish(user.id, {"type": "message", "thread_id": thread_id, "message": out})
    return out


@threads_router.post("/api/threads/{thread_id}/fresh-start", dependencies=[RequireOrigin])
async def fresh_start(thread_id: str, request: Request, user: CurrentUser):
    """Fresh start: the chat's line that hides earlier web replies from the bot's next runs."""
    talk = request.app.state.talk
    if await talk.get_thread(user.id, thread_id) is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return message_out(await post_fresh_start(talk, request.app.state.events, user.id, thread_id))


@threads_router.post("/api/threads/{thread_id}/messages/{message_id}/remember", dependencies=[RequireOrigin])
async def remember_offer(thread_id: str, message_id: str, body: RememberIn, request: Request, user: CurrentUser):
    """Remember it on a ``memory_offer`` line: saves the memory as the user's own word (the bot's own memory,
    or About you) and marks the line remembered. Pressing it again saves nothing new."""
    talk = request.app.state.talk
    if await talk.get_thread(user.id, thread_id) is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    try:
        accepted = await accept_offer(talk, request.app.state.memories, user.id, thread_id, message_id)
    except MemoryRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if accepted is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND_TEXT)
    return {"message": message_out(accepted.message), "memory": memory_out(accepted.memory)}


@threads_router.put("/api/threads/{thread_id}/messages/{message_id}/reminder-answer", dependencies=[RequireOrigin])
async def answer_reminder(thread_id: str, message_id: str, body: ReminderAnswerIn, request: Request,
                          user: CurrentUser):
    """A task reminder card's answer (Done · Failed · Reschedule · Skip), kept on its Report so the web and the
    phone both show it folded. Done, Failed and Reschedule change the task through the task routes first; this
    only records the answer. Published as a ``message`` frame (same id), so every open screen folds the card."""
    state = request.app.state
    if await state.talk.get_thread(user.id, thread_id) is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    message = await reminder_answer(state.talk, user.id, thread_id, message_id, body.answer, body.due)
    if message is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND_TEXT)
    out = message_out(message)
    await state.events.publish(user.id, {"type": "message", "thread_id": thread_id, "message": out})
    return out
