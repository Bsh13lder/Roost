"""Team tools for one run (D-C, D-D; spec §11 step 17).

``ask_bot`` hands a task to a teammate through the teammate's own work
queue and waits for the answer. Only the task text and the answer cross
over — every bot keeps its own computer and logins. Taint goes with the
task and comes back with the answer (spec §8.2). Both chats show handoff
lines. ``suggest_bot`` joins in Task 5.

Rule: every tool-result string built here from model or outside text is
escaped HERE, by its producer — ``claude_sdk._render_prompt`` renders tool
results raw (see its ``_escape_tags`` docstring), so an unescaped echo of a
model-chosen ``bot`` name could forge a ``<turn role="user">``."""

from __future__ import annotations

import asyncio
import html
import json
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from functools import partial
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from roost.bots.limits import fits_on_one_line
from roost.bots.look import avatar_dict, next_bot_color
from roost.bots.models import Avatar, AvatarScreen, AvatarShape, Bot, BotDraft, BotRole, DuplicateBotName
from roost.bots.service import bot_out
from roost.bots.status import Activity, ActivityBoard, STATUS_LABELS
from roost.bots.store import BotStore
from roost.constants import (
    AVATAR_COLOR_PATTERN, BOT_NAME_PATTERN, BOT_ROLES, DEFAULT_LENSBOT_SHAPE, DEFAULT_ROBOT_SCREEN, HANDOFF_PREVIEW_CHARS,
    HANDOFF_TIMEOUT_S, MAX_BOT_INSTRUCTIONS_LENGTH, MAX_BOT_JOB_LENGTH, MAX_BOT_NAME_LENGTH, MAX_BOTS_CREATED_PER_RUN,
    MAX_HANDOFF_DEPTH, MAX_HANDOFF_TASK_LENGTH, MAX_HANDOFFS_PER_RUN, MAX_SUGGESTIONS_PER_RUN,
    LENSBOT_SHAPES, ROBOT_SCREENS,
)
from roost.events.hub import EventHub
from roost.models_check.store import SeenModelStore
from roost.bots.instruction_sections import structure_instructions
from roost.talk.model_tools import ModelTools
from roost.talk.notices import preview
from roost.talk.outcome import ToolOutcome  # noqa: F401 — re-exported
from roost.talk.store import Message, MessageRole, TalkStore, message_out
from roost.create_check.constants import CREATE_CHECK_MARK
from roost.talk.tool_catalog import TAINTED_CREATE_BOT_TEXT
from roost.work.models import HandoffResult, WorkDraft, WorkKind, handoff_origin

BAD_ASK_ARGS = "Refused: ask_bot needs the teammate's name as bot and the task text as task."
BAD_SUGGESTION = (
    "Refused: suggest_bot needs a name (letters, numbers, spaces, . or -, up to 40), a one-line job, "
    f"and optionally a shape ({', '.join(LENSBOT_SHAPES)}), a role ({', '.join(BOT_ROLES)}), "
    f"a screen ({', '.join(ROBOT_SCREENS)}) and a #RRGGBB color."
)
BAD_CREATE = (
    "Refused: create_bot needs a unique name (letters, numbers, spaces, . or -, up to 40), a job on one line "
    "(up to 200), instructions of at most 4000 characters, and optionally a shape, a role, a screen and a #RRGGBB "
    "color."
)
CREATED_TEXT = ("Created {name}. It starts Resting with the same tools as every bot, and the user sees a card with "
                "Open and Undo. To give it work, use ask_bot with its name.")
_NOT_MAIN = "Refused: only the main bot creates bots."
_NOT_ON_REQUEST = ("Refused: bots are created only when the user asks you in their own chat with you. "
                   "Suggest one with suggest_bot instead.")
NO_TEAMMATES = "You have no teammates yet."
_WAITING_ON_YOU = "Refused: {name} is already waiting on you. Answer with what you have."
_UNANSWERED = {
    "timeout": "{name} did not answer within {minutes} minutes. Its answer will appear in its own chat.",
    "dropped": "{name} stopped before answering.",
    "failed": "{name} ran into a problem and did not answer.",
    "refused": _WAITING_ON_YOU,
}


class HandoffPort(Protocol):
    async def hand_off(
        self, user_id: str, asker_bot_id: str, target_bot_id: str, prepare: Callable[[], Awaitable[WorkDraft]],
    ) -> HandoffResult: ...


@dataclass(frozen=True)
class RunScope:
    user_id: str
    bot: Bot
    thread_id: str
    depth: int = 0
    parent_item_id: str | None = None
    ancestors: frozenset[str] = frozenset()  # bots up the handoff chain, all waiting on this run
    in_room: bool = False
    user_started: bool = False   # the run's items are all the user's own messages (Ruling 29)


class AskBotArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    bot: str = Field(min_length=1, max_length=64)
    # Fix round 1, finding 2: a hand-over's task is often "the full content" a
    # bot gathered (a long task list, a month of expenses) on its way to
    # ask_bot docs, not a short human-typed chat message — its own larger cap
    # (MAX_HANDOFF_TASK_LENGTH), not the chat-message one.
    task: str = Field(min_length=1, max_length=MAX_HANDOFF_TASK_LENGTH)


class SuggestBotArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=1, max_length=MAX_BOT_NAME_LENGTH, pattern=BOT_NAME_PATTERN)
    job: str = Field(min_length=1, max_length=MAX_BOT_JOB_LENGTH)
    shape: AvatarShape = DEFAULT_LENSBOT_SHAPE
    color: str | None = Field(default=None, pattern=AVATAR_COLOR_PATTERN)   # none: a colour no teammate wears
    screen: AvatarScreen = DEFAULT_ROBOT_SCREEN
    role: BotRole | None = None   # the job's emblem; none: general

    @field_validator("name", "job")
    @classmethod
    def _one_line(cls, value: str) -> str:
        if not fits_on_one_line(value):
            raise ValueError("must fit on one line")
        return value.strip()

    def card(self, team_colors: Iterable[str]) -> dict[str, Any]:
        avatar = Avatar(shape=self.shape, color=self.color or next_bot_color(team_colors), badge="none",
                        screen=self.screen, role=self.role)
        return {"name": self.name, "job": self.job, "avatar": avatar_dict(avatar)}


class CreateBotArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=1, max_length=MAX_BOT_NAME_LENGTH, pattern=BOT_NAME_PATTERN)
    job: str = Field(min_length=1, max_length=MAX_BOT_JOB_LENGTH)
    instructions: str = Field(default="", max_length=MAX_BOT_INSTRUCTIONS_LENGTH)
    shape: AvatarShape = DEFAULT_LENSBOT_SHAPE
    color: str | None = Field(default=None, pattern=AVATAR_COLOR_PATTERN)   # none: a colour no teammate wears
    screen: AvatarScreen = DEFAULT_ROBOT_SCREEN
    role: BotRole | None = None   # the job's emblem; none: general

    @field_validator("name", "job")
    @classmethod
    def _one_line(cls, value: str) -> str:
        if not fits_on_one_line(value):
            raise ValueError("must fit on one line")
        return value.strip()

    def draft(self, team_colors: Iterable[str]) -> BotDraft:
        avatar = Avatar(shape=self.shape, color=self.color or next_bot_color(team_colors), badge="none",
                        screen=self.screen, role=self.role)
        instructions = structure_instructions(self.instructions, name=self.name, job=self.job)
        return BotDraft(name=self.name, job=self.job, instructions=instructions, avatar=avatar)


def created_card(bot: Bot) -> dict[str, Any]:
    """The "Created <name>" card's body (message kind ``bot_created``): the web
    shows the full instructions, Open and Undo (which retires ``bot_id``)."""
    return {"bot_id": bot.id, "name": bot.name, "job": bot.job, "instructions": bot.instructions,
            "avatar": avatar_dict(bot.avatar)}


Announce = Callable[[str], Awaitable[None]]


async def _quiet(activity: str) -> None:
    """The default: no activity line (tests and callers outside a run)."""


def wrap_reply(name: str, text: str) -> str:
    return f'<bot_reply from="{html.escape(name, quote=True)}">{html.escape(text, quote=True)}</bot_reply>'


def _status_line(bot: Bot, activity: Activity | None) -> str:
    """One roster line. Names and jobs are the user's text, escaped here. An activity line
    from a tainted run (a page host, a name the model chose after reading a page) is outside
    text, and escaping does nothing against words. So it is dropped and the status label stays:
    this run stays clean, and nothing blocks create_bot just because a teammate is browsing."""
    main = " (main bot)" if bot.is_primary else ""
    shown = activity is not None and not activity.tainted
    doing = f": {html.escape(activity.text, quote=True)}" if shown else ""
    status = STATUS_LABELS[bot.status.value]
    return f"- {html.escape(bot.name, quote=True)}{main}: {html.escape(bot.job, quote=True)} · {status}{doing}"


class TeamTools:
    def __init__(
        self, scope: RunScope, *, bots: BotStore, talk: TalkStore, events: EventHub, port: HandoffPort,
        activity: ActivityBoard | None = None, seen_models: SeenModelStore | None = None,
    ) -> None:
        self._scope = scope
        self._bots = bots
        self._talk = talk
        self._events = events
        self._port = port
        self._activity = activity
        self._handoffs = 0
        self._suggestions = 0
        self._created = 0
        self._thread_lock = asyncio.Lock()
        self.models = ModelTools(scope, bots=bots, talk=talk, events=events,
                                 seen=seen_models)

    async def ask_bot(
        self, arguments: dict[str, Any], *, tainted: bool, link_scope: tuple[str, ...] = (), announce: Announce = _quiet,
    ) -> ToolOutcome:
        refusal = self._take_handoff_slot()
        if refusal is not None:
            return ToolOutcome(refusal)
        try:
            args = AskBotArgs.model_validate(arguments)
        except ValidationError:
            return ToolOutcome(BAD_ASK_ARGS)
        target = await self._resolve_target(args.bot)
        if isinstance(target, str):
            return ToolOutcome(target)
        await announce(f"asking {target.name}")
        result = await self._port.hand_off(
            self._scope.user_id, self._scope.bot.id, target.id,
            prepare=partial(self._hand_over, target, args.task, tainted, link_scope),
        )
        return await self._report(target, result)

    async def list_bots(self) -> ToolOutcome:
        """S1: what each teammate is doing now — name, job, status, activity. Never chat text."""
        team = await self._bots.list(self._scope.user_id)
        lines = tuple(_status_line(bot, self._activity.entry(bot.id) if self._activity else None)
                      for bot in team if bot.id != self._scope.bot.id)
        return ToolOutcome("\n".join(lines) or NO_TEAMMATES)

    async def suggest_bot(self, arguments: dict[str, Any], *, tainted: bool) -> ToolOutcome:
        """D-D: post a "Create this bot" card. Creates nothing — the card's
        button calls the normal ``POST /api/bots`` only when the user clicks.
        A card from a tainted run is stored tainted, and the web marks it
        "This run read outside content." (spec §8.2)."""
        if self._scope.in_room:
            return ToolOutcome("Refused: suggestions are shown only in your 1:1 chat.")
        if self._suggestions >= MAX_SUGGESTIONS_PER_RUN:
            return ToolOutcome(f"Refused: at most {MAX_SUGGESTIONS_PER_RUN} suggestions per run.")
        try:
            args = SuggestBotArgs.model_validate(arguments)
        except ValidationError:
            return ToolOutcome(BAD_SUGGESTION)
        team = await self._bots.list(self._scope.user_id)
        if any(b.name.casefold() == args.name.casefold() for b in team):
            return ToolOutcome(f"Refused: a bot named {args.name} is already on the team.")
        self._suggestions += 1
        message = await self._talk.add_message(
            self._scope.user_id, self._scope.thread_id, role="bot",
            body=json.dumps(args.card(bot.avatar.color for bot in team)),
            tainted=tainted, kind="suggestion", author_bot_id=self._scope.bot.id,
        )
        await self._events.publish(self._scope.user_id, {
            "type": "message", "thread_id": self._scope.thread_id, "message": message_out(message),
        })
        return ToolOutcome(f"Shown a card suggesting {html.escape(args.name, quote=True)}. "
                           "Nothing is created until the user clicks Create this bot.")

    async def create_bot(self, arguments: dict[str, Any], *, tainted: bool, checked: bool = False,
                         announce: Announce = _quiet) -> ToolOutcome:
        """Ruling 29. The gate already refused a tainted run (write_change);
        the scope checks here are the second fence. Only a validated name is announced."""
        refusal = self._creation_refusal(tainted and not checked)
        if refusal is not None:
            return ToolOutcome(refusal)
        try:
            args = CreateBotArgs.model_validate(arguments)
        except ValidationError:
            return ToolOutcome(BAD_CREATE)
        await announce(f"creating {args.name}")
        self._created += 1   # create_bot is not a parallel tool: calls run one by one
        team = await self._bots.list(self._scope.user_id)
        try:
            bot = await self._bots.create(self._scope.user_id, args.draft(member.avatar.color for member in team))
        except DuplicateBotName:
            self._created -= 1
            return ToolOutcome(f"Refused: a bot named {html.escape(args.name, quote=True)} is already on the team.")
        await self._announce_created(bot, checked=tainted and checked)
        return ToolOutcome(CREATED_TEXT.format(name=html.escape(bot.name, quote=True)))

    def _creation_refusal(self, tainted: bool) -> str | None:
        if not self._scope.bot.is_primary:
            return _NOT_MAIN
        if self._scope.in_room or not self._scope.user_started:
            return _NOT_ON_REQUEST
        if tainted:
            return TAINTED_CREATE_BOT_TEXT
        if self._created >= MAX_BOTS_CREATED_PER_RUN:
            return f"Refused: at most {MAX_BOTS_CREATED_PER_RUN} new bots per request."
        return None

    async def _announce_created(self, bot: Bot, *, checked: bool = False) -> None:
        """``checked``: made in a run that read web content, after the create check or your Yes on its card."""
        body = {**created_card(bot), **({CREATE_CHECK_MARK: True} if checked else {})}
        card = await self._talk.add_message(
            self._scope.user_id, self._scope.thread_id, role="bot", body=json.dumps(body),
            tainted=False, kind="bot_created", author_bot_id=self._scope.bot.id,
        )
        await self._events.publish(self._scope.user_id, {"type": "bot_updated", "bot": bot_out(bot, None)})
        await self._events.publish(self._scope.user_id, {
            "type": "message", "thread_id": self._scope.thread_id, "message": message_out(card),
        })

    async def _hand_over(self, target: Bot, task: str, tainted: bool, link_scope: tuple[str, ...]) -> WorkDraft:
        """Runs only once the runner has accepted the handoff (no wait
        cycle): the lines in both chats, then the target's work item."""
        thread_id = await self._target_thread(target)
        line = f"{self._scope.bot.name} → {target.name}: {task}"
        await self._post(self._scope.thread_id, "activity", line, self._scope.bot.id, tainted)
        task_line = await self._post(thread_id, "user", line, self._scope.bot.id, tainted)
        return WorkDraft(
            bot_id=target.id, thread_id=thread_id, kind=WorkKind.HANDOFF,
            origin=handoff_origin(self._scope.bot.name), body=task, tainted=tainted,
            depth=self._scope.depth + 1, parent_item_id=self._scope.parent_item_id, message_id=task_line.id,
            link_scope=link_scope,
        )

    def _take_handoff_slot(self) -> str | None:
        """Synchronous on purpose: parallel calls of one step can't both pass
        the per-run limit between an await and the increment."""
        if self._scope.depth + 1 > MAX_HANDOFF_DEPTH:
            return f"Refused: handoffs can only go {MAX_HANDOFF_DEPTH} bots deep."
        if self._handoffs >= MAX_HANDOFFS_PER_RUN:
            return f"Refused: at most {MAX_HANDOFFS_PER_RUN} handoffs per run."
        self._handoffs += 1
        return None

    async def _resolve_target(self, wanted: str) -> Bot | str:
        """A teammate by exact name (case-insensitive, an @ allowed) or id. Only
        this user's bots exist here. ``wanted`` is model text: escaped when echoed."""
        key = wanted.strip().lstrip("@").casefold()
        team = await self._bots.list(self._scope.user_id)
        target = next((b for b in team if b.id == wanted or b.name.casefold() == key), None)
        if target is None:
            return f"Refused: there is no teammate named {html.escape(wanted, quote=True)}."
        return self._check_target(target)

    def _check_target(self, target: Bot) -> Bot | str:
        if target.id == self._scope.bot.id:
            return "Refused: you can't hand work to yourself."
        if target.id in self._scope.ancestors:
            return _WAITING_ON_YOU.format(name=target.name)
        if target.off_duty:
            return f"Refused: {target.name} is off duty."
        return target

    async def _target_thread(self, target: Bot) -> str:
        async with self._thread_lock:  # two parallel asks to one bot share one "From" thread
            thread = await self._talk.find_or_create_peer_thread(
                self._scope.user_id, target.id, self._scope.bot.id, title=f"From {self._scope.bot.name}",
            )
        return thread.id

    async def _report(self, target: Bot, result: HandoffResult) -> ToolOutcome:
        if result.status == "done":
            line = f"{target.name} → {self._scope.bot.name}: {preview(result.text, HANDOFF_PREVIEW_CHARS)}"
            await self._post(self._scope.thread_id, "activity", line, target.id, result.tainted)
            return ToolOutcome(wrap_reply(target.name, result.text), tainted=result.tainted, link_scope=result.link_scope)
        minutes = max(1, int(HANDOFF_TIMEOUT_S // 60))
        return ToolOutcome(_UNANSWERED[result.status].format(name=target.name, minutes=minutes))

    async def _post(self, thread_id: str, role: MessageRole, body: str, author_id: str, tainted: bool) -> Message:
        message = await self._talk.add_message(
            self._scope.user_id, thread_id, role=role, body=body, tainted=tainted,
            kind="handoff", author_bot_id=author_id,
        )
        await self._events.publish(self._scope.user_id, {
            "type": "message", "thread_id": thread_id, "message": message_out(message),
        })
        return message
