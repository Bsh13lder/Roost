"""One turn's worth of work — contract's Interfaces: ``run_turn``, the
step-by-step mechanics ``roost.talk.runner.TurnRunner`` schedules a
background task around. Split into its own file so these mechanics
(build instructions, stream the model, run tools through the gate,
persist + publish) are testable directly, without the asyncio
task-scheduling the runner wraps around them.

Ruling 15 (controller, 2026-10-13): the bot's reply id is generated up
front; an empty-bodied placeholder ``message`` frame is published BEFORE
the first ``text_delta`` (so a live client can render the bubble right
away); the real reply is persisted under that same id once the turn
ends; then the full ``message`` frame and ``message_done`` are published.
A turn cut short (Stop, the wall-time cap, an error) stores and publishes
whatever text streamed the same way before closing the placeholder.

Review Focus #2 / Ruling 16: a tool's page/text result is wrapped in
``<untrusted_page url="…">…</untrusted_page>`` with its own content
escaped (``<``/``>`` → entities) before wrapping, so a hostile page
can't inject a fake closing tag into OUR wrapper — independent of
``roost/llm/claude_sdk.py``'s own, broader escaping of every turn's
text when it renders the SDK prompt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from collections.abc import Awaitable, Sequence
from typing import Callable, Mapping
from uuid import uuid4

from roost.approvals.models import ApprovalState, PendingCall
from roost.bots.models import Bot
from roost.bots.status import ActivityBoard
from roost.choices.decisions import DecisionBook
from roost.bots.store import BotStore
from roost.computer_use.runner import ScreenKit
from roost.constants import CHAT_TAINT_KEEP, MAX_RUN_SECONDS, MAX_STEPS, SITE_LOGINS_IN_PROMPT
from roost.desk import Desk
from roost.desk.control import ControlLock
from roost.desk.stuck import Block
from roost.events.hub import EventHub
from roost.helpers.tools import HelperTools
from roost.llm.registry import model_label, resolve_bot_model, resolve_call_model
from roost.mac.models import FolderLine
from roost.money.models import Project
from roost.models_check.store import SeenModelStore
from roost.memory.hooks import MemoryHooks
from roost.vault.store import VaultStore
from roost.memory.summaries import SummaryStore, summary_turn
from roost.llm.types import ChatTurn, ImagePart, Model, ModelRequest, ToolSpec
from roost.media.pictures import PICTURES_PROMPT_LINE
from roost.rooms.models import RoomContext
from roost.plan.prompt import plan_section
from roost.plan.service import PlanService
from roost.routines.models import ReportBody, RoutineSection
from roost.skills.prompt import skills_section
from roost.skills.service import SkillService
from roost.talk.domain_tools import DomainTools
from roost.talk.carry import carried_sites
from roost.talk.chat_feel import announce_start, on_it_only
from roost.talk.gate import Gate
from roost.talk.instructions import Teammate, build_instructions
from roost.projects.chat_refs import chat_projects, project_mention_section
from roost.talk.link_scope import HOST_PREFIX, LinkScope, named_site_entries
from roost.talk.notices import post_notice
from roost.talk.steer import RunRestart, RunSteer, RunStopped
from roost.talk.replies import reply_turn_text
from roost.talk.run_steps import RunSteps
from roost.talk.store import Message, TalkStore, message_out
from roost.talk.team_tools import HandoffPort, RunScope, TeamTools
from roost.talk.steps import OnDelta, step_loop
from roost.talk.tool_runner import InflightRecorder, ToolRunner
from roost.talk.tool_runner import wrap_page as _wrap_page  # noqa: F401 — tests/test_claude_sdk_options.py imports it from here
from roost.talk.fresh_start import last_fresh_start
from roost.talk.tools import tool_specs_for
from roost.work.models import WorkItem, WorkKind

_STEP_LIMIT_TEXT = "I hit my step limit — say continue."
# Amendment A1: a tainted reply this far back in the chat reaches the model only as this line.
TAINT_PLACEHOLDER_TEXT = (
    "(an earlier reply here used web content; its text is no longer shown. search_chat finds it if you need it)"
)

logger = logging.getLogger(__name__)
ProjectLookup = Callable[[str], Awaitable[Sequence[Project]]]   # a user id -> that user's projects


@dataclass(frozen=True)
class RunInputs:
    """What the work queue hands one turn (spec §4.2): the claimed items —
    their origin labels, taint and any interrupted-call note. Later tasks
    add fields with defaults; ``RunInputs()`` is a turn outside the queue."""

    items: tuple[WorkItem, ...] = ()
    record_inflight: InflightRecorder | None = None
    handoff: HandoffPort | None = None
    ancestors: frozenset[str] = frozenset()
    room: RoomContext | None = None
    domain: DomainTools | None = None
    control: ControlLock | None = None
    memory: MemoryHooks | None = None
    helpers: HelperTools | None = None
    run_id: str | None = None   # the work queue's run id; helpers' run rows hang off it
    approval: ApprovalState | None = None   # None: today's verdicts, no Ask cards
    mac_writes_now: Callable[[], int] | None = None   # re-read before every gate decision (the floor counts live)
    decisions: DecisionBook | None = None   # the user's earlier choices: a decided question is not asked again
    mac_folders: tuple[FolderLine, ...] = ()   # the Mac folders this bot may use (its own and all-bots ones)
    vault: VaultStore | None = None   # which accounts this bot is signed in with (named in its prompt)
    routine_section: RoutineSection | None = None   # a routine run's "nobody is watching" section and its taint
    plan: PlanService | None = None   # the bot's own Plan: today's and tomorrow's clean items go in its prompt
    screen: ScreenKit | None = None   # C3: a Linux bot's screen loop (the lease lives on app.state.cu_leases)
    skills: SkillService | None = None   # Skills: the index of clean skills on for this bot goes in its prompt
    steer: RunSteer | None = None   # steer design: your new messages mid-run, restart and Stop (None: never)
    projects: ProjectLookup | None = None   # #project in the chat: the user's projects, to read "#Name" against
    call: bool = False   # voice call (§3): the thread is in a call, so a run of your own message is spoken
    stuck_reply: str | None = None   # your message answered a Stuck card: the trusted line (roost/stuck/typed_reply.py)
    routine_sites: tuple[str, ...] = ()   # a routine run: sites it names that its bot opened from your own chat
    chat_thread: bool = False   # the run's thread is a bot's 1:1 chat (never a routine's run log)
    pictures: tuple[ImagePart, ...] = ()   # chat pictures (owner, 2026-11-05): the ones on your claimed messages


@dataclass(frozen=True)
class TurnResult:
    reply: str
    tainted: bool
    capped: bool
    link_scope: tuple[str, ...] = ()
    own_sites: tuple[str, ...] = ()   # the sites the gate let this run open itself (carried to the run after a card)
    block: Block | None = None   # Stuck flow: the block that ended this run (only in a run that may open cards)
    parked: PendingCall | None = None   # the step that asked: the run ended on an Ask card
    plan: tuple[PendingCall, ...] = ()   # Review first: the steps this run collected for one Proposal card
    wall: Block | None = None   # a block met in a run that may not open a Stuck card (a routine): loud result only
    stopped: bool = False   # you pressed Stop: the run ended at a boundary and kept what it said


EMPTY_RESULT = TurnResult(reply="", tainted=False, capped=False)

# Only conversation text reaches the model: activity rows, notices,
# suggestion cards and Stuck cards are UI; an incoming handoff (role
# "user", kind "handoff") is the task the bot must answer; and a continue
# line (role "user", kind "card_answer", Stuck flow R6) is your go-ahead
# after you cleared a Stuck card, and the outcome of a step you approved (``approval_result``, shown to the
# model as a user turn). A routine's instructions (``routine``, role "user") start its run, and a ``report`` is the
# bot's own earlier Report, read back as text. A work item's body never reaches the model.
REMINDER_HEADLINE_PREFIX = "Reminder: "    # system_reports._reminder's headline, for a body with no task_title
_MODEL_KINDS = frozenset({"text", "handoff", "card_answer", "approval_result", "routine", "report"})


def _origins(items: tuple[WorkItem, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.origin for item in items))


def _interrupted(items: tuple[WorkItem, ...]) -> tuple[str, ...]:
    """Fix round 1, finding 2: ``set_inflight`` writes the SAME note to
    every item of a claimed batch, so a batch of N re-queued items would
    otherwise repeat one call's text N times in the system prompt
    (``dict.fromkeys``, like ``_origins`` already dedupes)."""
    return tuple(dict.fromkeys(item.inflight for item in items if item.inflight))


def _model_line(bot: Bot, labels: Mapping[str, str]) -> str:
    """"Opus 5.5, high effort": what a bot runs on, for the main bot's roster."""
    model_id = resolve_bot_model(bot.model_override, frozenset(labels))
    effort = f"{bot.effort} effort" if bot.effort else "default effort"
    return f"{model_label(model_id, labels)}, {effort}"


def _user_started(items: tuple[WorkItem, ...]) -> bool:
    """Ruling 29: only a run made entirely of the user's own messages may create
    bots — never a handoff, a room post, a routine or a run outside the queue."""
    return bool(items) and all(item.kind is WorkKind.MESSAGE for item in items)


_OWNER_CHAT_KINDS = frozenset({WorkKind.MESSAGE, WorkKind.CARD_ANSWER})


def _user_chat(inputs: RunInputs) -> bool:
    """A 1:1 run of your own chat: your messages, and (owner, 2026-11-05: "Grok is much freer") the run your Yes or
    your cleared card carries on in a bot's 1:1 chat, never a routine's run log. Creating a bot stays message-only."""
    if inputs.room is not None or not inputs.items:
        return False
    kinds = {item.kind for item in inputs.items}
    return kinds == {WorkKind.MESSAGE} or (inputs.chat_thread and kinds <= _OWNER_CHAT_KINDS)


def _site_fresh(inputs: RunInputs) -> bool:
    """W7 (owner, 2026-10-24): your new message is a fresh start for opening sites only. A 1:1 run made only of your
    own messages (never a card answer, routine, handoff or room) starts site-fresh whatever the chat's older history
    holds, unless a claimed message is itself tainted or survived a crash mid-call (its taint is unknown)."""
    return (_user_chat(inputs) and _may_open_cards(inputs)
            and not any(item.tainted or item.inflight for item in inputs.items))


def _routine_run(inputs: RunInputs) -> bool:
    """A run made only of routine items, outside rooms: nobody is watching, so it may park on an Ask card
    (which waits for the next run) but never opens a Stuck card or creates a bot."""
    return inputs.room is None and bool(inputs.items) and all(item.kind is WorkKind.ROUTINE for item in inputs.items)


def _may_open_cards(inputs: RunInputs) -> bool:
    """Stuck flow R5: a Stuck card opens only in a run made of your own
    messages and continue items, outside rooms. Every other run (a handoff,
    a room post, a routine, a run outside the queue) gets a block back as a
    loud tool result, and its model answers with it."""
    return inputs.room is None and bool(inputs.items) and all(
        item.kind in (WorkKind.MESSAGE, WorkKind.CARD_ANSWER) for item in inputs.items
    )


def _progress_lines_allowed(inputs: RunInputs) -> bool:
    """The words between steps (owner, 2026-11-01) join the activity pill's steps as notes (owner, 2026-11-04,
    never their own bubbles) only in your own chat: a run of your messages and continue items, outside rooms. A
    handoff, a room post, a routine or a run outside the queue keeps them to itself."""
    return _may_open_cards(inputs)


def _team_tools(
    user_id: str, bot: Bot, thread_id: str, inputs: RunInputs, *, bots: BotStore, talk: TalkStore, events: EventHub,
    activity: ActivityBoard, seen_models: SeenModelStore | None = None,
) -> TeamTools | None:
    if inputs.handoff is None:
        return None
    scope = RunScope(
        user_id=user_id, bot=bot, thread_id=thread_id,
        depth=max((item.depth for item in inputs.items), default=0),
        parent_item_id=inputs.items[0].id if inputs.items else None,
        ancestors=inputs.ancestors, in_room=inputs.room is not None,
        user_started=_user_started(inputs.items),
    )
    return TeamTools(scope, bots=bots, talk=talk, events=events, port=inputs.handoff, activity=activity,
                     seen_models=seen_models)


def _outside_task(items: tuple[WorkItem, ...], history: "_History", bot_id: str) -> bool:
    """D4: True when this run carries another bot's outside content — a
    tainted handoff, a tainted teammate line in its context, or a tainted
    answer it received — the run keeps its desk but its links are limited
    (``LinkScope``). True when a claimed item is tainted (a handoff from a
    tainted run) or ANY message this run loaded holds a tainted message
    another bot wrote (an earlier tainted handoff in a "From <asker>"
    thread, a "Scout → Chief" activity line a tainted answer left in the
    asker's own thread, a teammate's tainted room post) -- ``history.messages``
    is every loaded row, not only the ones ``_chat_turn_for`` replays to the
    model (review finding, Task 4 round 1), since an activity row carries
    real taint but is never itself a turn. The bot's own tainted replies
    don't count: it read those pages, or asked for those answers, at its
    own desk. A handoff run loads only its own task lines (final review),
    so an older tainted task in its "From <asker>" thread no longer counts."""
    return any(item.tainted for item in items) or any(
        m.tainted and m.author_bot_id not in (None, bot_id) for m in history.messages
    )


def _report_text(body: str) -> str:
    """A Report's JSON body as the text the bot reads back: "Report (routine): headline" and its text. A task's
    reminder names the task and its id, so "done" from the owner reaches ``complete_task`` on the right task."""
    try:
        report = ReportBody.model_validate_json(body)
    except ValueError:
        return body
    if report.source == "reminder" and report.task_id:
        title = report.task_title or report.headline.removeprefix(REMINDER_HEADLINE_PREFIX)
        answered = f" You already answered it: {report.answer}." if report.answer else ""
        return f"Reminder for task {title} (id {report.task_id}): {report.text}{answered}"
    return f"Report ({report.source}): {report.headline}\n\n{report.text}"


def _chat_turn_for(message: Message, bot_id: str, names: dict[str, str]) -> ChatTurn | None:
    if message.kind not in _MODEL_KINDS:
        return None
    if message.kind == "approval_result":
        return ChatTurn("user", message.body)
    if message.kind == "report":
        return ChatTurn("assistant", _report_text(message.body)) if message.author_bot_id in (None, bot_id) else None
    if message.role == "user":
        return ChatTurn("user", reply_turn_text(message))
    if message.role != "bot":
        return None
    if message.author_bot_id in (None, bot_id):
        return ChatTurn("assistant", message.body)
    # Another bot's room post: its answer, data — never the user's voice (spec §8.2).
    return ChatTurn("teammate", message.body, tool_name=names.get(message.author_bot_id, "A teammate"))


def _delta_publisher(
    events: EventHub, user_id: str, thread_id: str, reply_id: str, draft: list[str],
    run_steps: RunSteps | None = None,
) -> OnDelta:
    """Each streamed chunk goes live to the chat and into ``draft``, the turn's
    text so far, which outlives a Stop's cancellation (see ``_keep_cut_short``).
    The activity pill hears "Writing the reply" once per streak."""
    async def on_delta(text: str) -> None:
        draft.append(text)
        if run_steps is not None:
            await run_steps.writing()
        await events.publish(user_id, {
            "type": "text_delta", "thread_id": thread_id, "message_id": reply_id, "delta": text,
        })
    return on_delta


@dataclass(frozen=True)
class _History:
    """What a run loads from its thread: ``turns`` is the transcript the
    model replays (``user``/``bot`` rows only, via ``_chat_turn_for``);
    ``messages`` is every row this page loaded, taint and author
    included. Review finding (Task 4, round 1): an ``activity`` row (a
    "Scout → Chief" handoff line) never becomes a turn, but it is real
    taint -- ``_starts_tainted``/``_outside_task`` must scan ``messages``,
    not the model-visible ``turns``, or that line's taint never reaches
    either check."""

    turns: tuple[ChatTurn, ...]
    messages: tuple[Message, ...]


def _newest_claimed_message(items: tuple[WorkItem, ...]) -> str | None:
    """The claimed batch's own post, if it has one: ``claim_batch`` claims
    items oldest-first, so the last one carrying a ``message_id`` is the
    newest post THIS run is meant to answer. ``None`` when no claimed item
    has one (a run outside the queue, or handoffs queued before they did) —
    that keeps today's behavior (``_replay_through`` below is a no-op)."""
    message_ids = tuple(item.message_id for item in items if item.message_id is not None)
    return message_ids[-1] if message_ids else None


def _replay_through(messages: tuple[Message, ...], message_id: str | None) -> tuple[Message, ...]:
    """Fix round 1, finding 1: a room post is meant for a specific bot —
    a member that was busy when it was addressed must answer ITS OWN
    post once it becomes free, not whatever the room's chattiest member
    posted last while it was away. Cuts the replay right after
    ``message_id``; ``None``, or an id this page never loaded, changes
    nothing (a 1:1 run's own newest message is already the last one
    loaded, since nothing follows it until this very run answers)."""
    if message_id is None:
        return messages
    for i, message in enumerate(messages):
        if message.id == message_id:
            return messages[: i + 1]
    return messages


_OWN_LINE_KINDS = frozenset({WorkKind.HANDOFF, WorkKind.ROUTINE})


def _first_claimed_handoff_line(items: tuple[WorkItem, ...]) -> str | None:
    """Final review (Chief): every handoff from one asker lands in ONE
    long-lived "From <asker>" thread, so loading that whole thread would let
    one old tainted task switch the target's desk off for every later task,
    and would show the model tasks it was never handed (``ask_bot``'s
    contract: the teammate "sees only the task text you write"). A run that
    answers only handoffs therefore loads from its oldest claimed task line
    on. ``None`` — the whole page, as before — when any claimed item is not
    a handoff (the user writing in that thread loads all of it) or predates
    the task-line id (a handoff queued before this fix).

    A routine run likewise loads only the line that launched it (owner, 2026-11-07, tokens): its run log holds every
    earlier launch and reply, and the routine section already carries the slot, the earlier answers and a watch's
    change."""
    if not items or any(item.kind not in _OWN_LINE_KINDS or item.message_id is None for item in items):
        return None
    return items[0].message_id


def _replay_from(messages: tuple[Message, ...], message_id: str | None) -> tuple[Message, ...]:
    """Drop everything before ``message_id``; ``None``, or an id this page
    never loaded (the line is older than the page), changes nothing."""
    if message_id is None:
        return messages
    for i, message in enumerate(messages):
        if message.id == message_id:
            return messages[i:]
    return messages


def _age_taint(loaded: tuple[Message, ...]) -> tuple[Message, ...]:
    """Amendment A1: a tainted row that is not among the newest ``CHAT_TAINT_KEEP`` loaded messages stops
    tainting the run. Its text is replaced, so the web content can no longer steer anything either. Every row
    before the newest Fresh start line (``roost/talk/fresh_start.py``) is aged the same way."""
    cutoff = max(len(loaded) - CHAT_TAINT_KEEP, last_fresh_start(loaded))
    return tuple(_aged(m) if i < cutoff else m for i, m in enumerate(loaded))


def _aged(message: Message) -> Message:
    """An old row's web text gone: a tainted message's body, and a reply's quote of web content (Replies)."""
    if message.tainted:
        message = replace(message, tainted=False, body=TAINT_PLACEHOLDER_TEXT)
    if message.reply_tainted:
        message = replace(message, reply_tainted=False, reply_quote=TAINT_PLACEHOLDER_TEXT)
    return message


async def _history(
    talk: TalkStore, user_id: str, thread_id: str, bot_id: str, names: dict[str, str],
    items: tuple[WorkItem, ...] = (), summaries: SummaryStore | None = None,
) -> _History:
    # Final review, finding 8: `list_messages`'s default is the OLDEST
    # page -- past DEFAULT_MESSAGE_PAGE_LIMIT messages the model would
    # never see the user's newest one. `list_latest_messages` is the
    # newest page instead, still in chronological order.
    #
    # `messages` stays EVERY loaded row -- an `activity` row (a
    # "Scout → Chief" handoff line) never becomes a turn below, but it
    # is real taint `_starts_tainted`/`_outside_task` must still see (see
    # `_History`'s own docstring). `turns`, the model-visible replay, both
    # drops the ones `_chat_turn_for` has nothing to say about AND (fix
    # round 1, finding 1) ends at this run's own claimed post, so a bot
    # that was busy elsewhere doesn't answer a later post addressed to
    # someone else. A run answering only handoffs loads just its own task
    # lines (`_first_claimed_handoff_line`), and scans only those for taint.
    #
    # Memory: with a summary, only messages after its boundary load, and the
    # summary is the first turn. A handoff-only run ignores summaries. Old
    # tainted rows age out of the replay and the scans (Amendment A1).
    start = _first_claimed_handoff_line(items)
    summary = await summaries.latest(user_id, thread_id) if summaries is not None and start is None else None
    after = summary.upto_created_at if summary is not None else None
    loaded = tuple(await talk.list_latest_messages(user_id, thread_id, after_created_at=after))
    if start is None:
        loaded = _age_taint(loaded)
    replay = _replay_through(_replay_from(loaded, start), _newest_claimed_message(items))
    turns = tuple(turn for m in replay for turn in (_chat_turn_for(m, bot_id, names),) if turn is not None)
    if summary is not None and summary.text:
        turns = (summary_turn(summary.text), *turns)
    return _History(turns=turns, messages=loaded if start is None else replay)


def _starts_tainted(items: tuple[WorkItem, ...], history: _History) -> bool:
    """Spec §8.2: a run is tainted from its first step when a claimed item
    is, or when any message it loads into context is — an earlier tainted
    reply in this thread, a teammate's tainted room post, a tainted task
    line among the handoffs it claimed (a handoff run loads only those, see
    ``_first_claimed_handoff_line``). A clean run must not launder an
    injection by reading it back (a fresh thread starts clean).

    Fix round 1, finding 1: a claimed item still carrying an ``inflight``
    note survived a crash mid-call (``queue.recover_on_boot`` re-queues it
    without clearing that note). The crashed run's own taint lived only in
    ``ToolRunner.tainted`` and was never persisted (only ``complete()``
    does that), so it is unknown -- and unknown must be treated as tainted,
    or a re-run could launder page-derived call text in as clean."""
    return (
        any(item.tainted for item in items)
        or any(item.inflight for item in items)
        or any(m.tainted or m.reply_tainted for m in history.messages)
    )


async def _persist_reply(
    *, talk: TalkStore, events: EventHub, user_id: str, thread_id: str, reply_id: str,
    bot_id: str, text: str, tainted: bool, capped: bool,
) -> None:
    if capped:
        await post_notice(talk, events, user_id, thread_id, _STEP_LIMIT_TEXT)
    await _store_reply(talk, events, user_id, thread_id, reply_id, bot_id, text, tainted)
    await _close_placeholder(events, user_id, thread_id, reply_id)


async def _store_reply(
    talk: TalkStore, events: EventHub, user_id: str, thread_id: str, reply_id: str,
    bot_id: str, text: str, tainted: bool,
) -> None:
    message = await talk.add_message(
        user_id, thread_id, role="bot", body=text, tainted=tainted, message_id=reply_id, author_bot_id=bot_id,
    )
    await events.publish(user_id, {"type": "message", "thread_id": thread_id, "message": message_out(message)})


async def _close_placeholder(events: EventHub, user_id: str, thread_id: str, reply_id: str) -> None:
    await events.publish(user_id, {"type": "message_done", "thread_id": thread_id, "message_id": reply_id})


async def _keep_cut_short(
    *, talk: TalkStore, events: EventHub, user_id: str, thread_id: str, reply_id: str,
    bot_id: str, text: str, tainted: bool,
) -> None:
    """Task 7 fix round 2: a reply cut short (Stop, the wall-time cap, an
    error) keeps what streamed: it is stored under the placeholder's id
    and published as a real ``message`` frame, so it has a genuine
    per-thread ``seq`` (the web never invents one from the hub's per-user
    cursor) and survives a reload. Then the placeholder is closed. A
    failed store is logged, never raised: it must not mask why the turn
    ended (a Stop's ``CancelledError`` above all)."""
    if text.strip():
        try:
            await _store_reply(talk, events, user_id, thread_id, reply_id, bot_id, text, tainted)
        except Exception:
            logger.exception("Could not store the cut-short reply %s in thread %s", reply_id, thread_id)
    await _close_placeholder(events, user_id, thread_id, reply_id)


async def _finish_reply(
    *, talk: TalkStore, events: EventHub, user_id: str, thread_id: str, reply_id: str,
    bot_id: str, text: str, tainted: bool, capped: bool, blocked: bool,
) -> None:
    """Store and publish the turn's reply, then close its placeholder. A
    blocked or parked turn that said nothing, or only its "On it: …" line, stores no bubble: the Stuck or Ask card
    ``TurnRunner`` posts next speaks for it. The placeholder always closes."""
    if blocked and on_it_only(text):
        await _close_placeholder(events, user_id, thread_id, reply_id)
        return
    try:
        await _persist_reply(
            talk=talk, events=events, user_id=user_id, thread_id=thread_id, reply_id=reply_id,
            bot_id=bot_id, text=text, tainted=tainted, capped=capped,
        )
    except BaseException:
        await _close_placeholder(events, user_id, thread_id, reply_id)
        raise


def _own_texts(history: "_History") -> tuple[str, ...]:
    """The user's own words in the loaded context — the only trusted text."""
    return tuple(m.body for m in history.messages if m.role == "user" and m.author_bot_id is None and m.kind == "text")


def _routine_named_sites(history: "_History") -> LinkScope:
    """Owner, 2026-11-04: the well-known sites a routine's own instructions name ("Open WhatsApp Web") open in its
    runs even once it read outside content; only ``NAMED_SITES`` words count, never an address in them."""
    texts = (m.body for m in history.messages if m.role == "user" and m.kind == "routine" and m.author_bot_id is None)
    return LinkScope.of(entry for text in texts for entry in named_site_entries(text))


def _initial_link_scope(items: tuple[WorkItem, ...], history: "_History", routine_sites: tuple[str, ...] = ()) -> LinkScope:
    inherited = LinkScope.of(url for item in items for url in item.link_scope)
    chat_opened = LinkScope.of(f"{HOST_PREFIX}{site}" for site in routine_sites)
    return (LinkScope.from_texts(_own_texts(history)).merge(_routine_named_sites(history)).merge(inherited)
            .merge(chat_opened))


@dataclass(frozen=True)
class _Prepared:
    system: str
    tools: tuple[ToolSpec, ...]
    team: TeamTools | None
    outside: bool
    memory_tainted: bool = False
    spoken: bool = False   # a voice call's run of the user's own message: the voice rule and the call model
    pictures: tuple[ImagePart, ...] = ()   # your attached pictures, shown with every step of the run


def _fresh_user_texts(history: "_History") -> tuple[str, ...]:
    """The user's own messages since anything else was said (a burst of quick messages is one turn)."""
    fresh: tuple[str, ...] = ()
    for message in reversed(history.messages):
        if not (message.role == "user" and message.author_bot_id is None and message.kind == "text"):
            break
        fresh = (message.body, *fresh)
    return fresh


async def _projects_section(user_id: str, inputs: RunInputs, history: "_History") -> str | None:
    """#project: one trusted line per project the user's fresh messages name as "#Name" (their own projects only)."""
    texts = _fresh_user_texts(history)
    if inputs.projects is None or not any("#" in text for text in texts):
        return None
    return project_mention_section(chat_projects("\n".join(texts), await inputs.projects(user_id)))


def _newest_user_text(history: "_History") -> str:
    """The body of the user's newest own message in what this run loaded ("" when there is none)."""
    for message in reversed(history.messages):
        if message.role == "user" and message.author_bot_id is None and message.kind == "text":
            return message.body
    return ""


async def _prepare(
    user_id: str, bot: Bot, thread_id: str, inputs: RunInputs, history: "_History",
    *, bots: BotStore, talk: TalkStore, events: EventHub, activity: ActivityBoard,
    seen_models: SeenModelStore | None = None,
) -> _Prepared:
    team_bots = await bots.list(user_id)
    labels = await seen_models.labels() if seen_models is not None and bot.is_primary else {}
    teammates = tuple(
        Teammate(b.name, b.job, b.off_duty, is_main=b.is_primary, model=_model_line(b, labels) if bot.is_primary else "")
        for b in team_bots if b.id != bot.id
    )
    outside = _outside_task(inputs.items, history, bot.id)
    started = _user_started(inputs.items)
    team = _team_tools(user_id, bot, thread_id, inputs, bots=bots, talk=talk, events=events, activity=activity,
                       seen_models=seen_models)
    can_create = bot.is_primary and inputs.room is None and started and team is not None
    spoken = inputs.call and started and inputs.room is None
    section = (
        await inputs.memory.prompt_section(user_id, bot.id, _newest_user_text(history))
        if inputs.memory is not None else None
    )
    logins = (await inputs.vault.list_for_bot(user_id, bot.id, SITE_LOGINS_IN_PROMPT)) if inputs.vault is not None else ()
    # Only clean items are shown (tainted ones are counted), so this adds no taint to the run.
    plan_text = plan_section(await inputs.plan.items_for_prompt(user_id, bot.id)) if inputs.plan is not None else None
    # Skills: only clean skills are named (marked ones are counted), so the index adds no taint either.
    skills = (skills_section(await inputs.skills.on_for_bot(user_id, bot.id), query=_newest_user_text(history))
              if inputs.skills is not None else None)
    system = build_instructions(
        bot, origins=_origins(inputs.items), interrupted=_interrupted(inputs.items), teammates=teammates,
        outside_content=outside, room=inputs.room, can_create=can_create,
        memory=section.text if section is not None else None, mac_folders=inputs.mac_folders,
        approval=bot.approval if inputs.approval is not None else None, site_logins=logins,
        routine=inputs.routine_section.text if inputs.routine_section is not None else None, plan=plan_text,
        skills=skills.text if skills is not None else None,
        projects=await _projects_section(user_id, inputs, history), spoken=spoken, stuck_reply=inputs.stuck_reply,
    )
    tools = tool_specs_for(bot, team=team is not None, in_room=inputs.room is not None, user_started=started)
    if inputs.pictures:
        system = f"{system}\n\n{PICTURES_PROMPT_LINE}"
    return _Prepared(system, tools, team, outside, memory_tainted=(section is not None and section.tainted) or (
        inputs.routine_section is not None and inputs.routine_section.tainted), spoken=spoken,
        pictures=inputs.pictures)


async def run_turn(
    *, user_id: str, bot: Bot, thread_id: str, bots: BotStore, talk: TalkStore, events: EventHub,
    desk: Desk, model: Model, activity: ActivityBoard, gate: Gate, inputs: RunInputs = RunInputs(),
    seen_ids: frozenset[str] = frozenset(), seen_models: SeenModelStore | None = None,
) -> TurnResult:
    """Run one full turn for ``bot`` in ``thread_id`` and return what it
    said. Raises on any unexpected failure — ``TurnRunner`` is the error
    boundary and also settles the bot's status afterwards."""
    reply_id = str(uuid4())
    await announce_start(events=events, bots=bots, activity=activity, user_id=user_id, bot_id=bot.id,
                         thread_id=thread_id, reply_id=reply_id)
    try:
        team_bots = await bots.list(user_id)
        history = await _history(
            talk, user_id, thread_id, bot.id, {b.id: b.name for b in team_bots}, inputs.items,
            summaries=inputs.memory.summaries if inputs.memory is not None else None,
        )
        prepared = await _prepare(user_id, bot, thread_id, inputs, history, bots=bots, talk=talk, events=events,
                                  activity=activity, seen_models=seen_models)
    except BaseException:
        await _close_placeholder(events, user_id, thread_id, reply_id)
        raise
    run_steps = RunSteps(events, user_id=user_id, bot_id=bot.id, thread_id=thread_id,
                         run_id=inputs.run_id or str(uuid4()))
    await run_steps.begin()
    tool_runner = ToolRunner(
        user_id=user_id, bot_id=bot.id, desk=desk, gate=gate, activity=activity, events=events,
        allowed=frozenset(spec.name for spec in prepared.tools), tainted=_starts_tainted(inputs.items, history) or prepared.memory_tainted,
        record_inflight=inputs.record_inflight, team=prepared.team, domain=inputs.domain,
        link_scope=_initial_link_scope(inputs.items, history, inputs.routine_sites), link_guard=prepared.outside,
        approval=inputs.approval, mac_writes_now=inputs.mac_writes_now,
        decisions=inputs.decisions,
        # S1 D2: every bot can see the user's records, so R2's link guard covers every tainted run.
        sees_records=True, control=inputs.control, cards=_may_open_cards(inputs), thread_id=thread_id, helpers=inputs.helpers,
        from_routine=_routine_run(inputs), run_id=inputs.run_id, screen=inputs.screen,
        user_started=_user_chat(inputs), steer=inputs.steer, run_steps=run_steps, site_fresh=_site_fresh(inputs),
        owner=gate.owner_source(user_id, thread_id), check_model=resolve_bot_model(bot.model_override, seen_ids),
        own_sites=carried_sites(inputs.items),
    )
    try:
        return await _run_steps(
            tool_runner=tool_runner, prepared=prepared, history=history, bot=bot, model=model, events=events,
            talk=talk, user_id=user_id, thread_id=thread_id, reply_id=reply_id, seen_ids=seen_ids, steer=inputs.steer,
            run_steps=run_steps, progress=_progress_lines_allowed(inputs),
        )
    finally:
        await tool_runner.close_screen()   # C3: the lease and the browser guards never outlive the run
        await run_steps.finish()


async def _run_steps(
    *, tool_runner: ToolRunner, prepared: "_Prepared", history: "_History", bot: Bot, model: Model,
    events: EventHub, talk: TalkStore, user_id: str, thread_id: str, reply_id: str, seen_ids: frozenset[str],
    steer: RunSteer | None = None, run_steps: RunSteps | None = None, progress: bool = False,
) -> TurnResult:
    """The step loop and the reply, for one prepared run. Stop keeps what streamed and returns ``stopped``; a
    restart drops it (the run starts over) and re-raises ``RunRestart`` for ``TurnRunner``."""
    draft: list[str] = []

    async def note(text: str) -> None:
        if run_steps is not None:
            await run_steps.note(text, tainted=tool_runner.tainted)   # the run's taint at that moment

    try:
        model_id = (resolve_call_model(bot.model_override, seen_ids) if prepared.spoken
                    else resolve_bot_model(bot.model_override, seen_ids))
        # Your pictures ride right after the chat's turns, before the run's own steps (a stable prompt prefix).
        pictures = tuple(replace(p, after_turn=len(history.turns) - 1) for p in prepared.pictures)
        reply_text, capped = await step_loop(
            model=model, tool_runner=tool_runner, max_steps=MAX_STEPS, deadline_s=MAX_RUN_SECONDS,
            request_for=lambda added: ModelRequest(
                system=prepared.system, turns=history.turns + added, tools=prepared.tools, model=model_id,
                agent=bot.name, effort=bot.effort, images=pictures,
            ),
            on_delta=_delta_publisher(events, user_id, thread_id, reply_id, draft, run_steps), steer=steer,
            on_progress=note if progress and run_steps is not None else None,
        )
    except RunRestart:
        await _close_placeholder(events, user_id, thread_id, reply_id)   # nothing stored: the bubble goes away
        raise
    except RunStopped:
        text = "".join(draft)
        await _keep_cut_short(talk=talk, events=events, user_id=user_id, thread_id=thread_id, reply_id=reply_id,
                              bot_id=bot.id, text=text, tainted=tool_runner.tainted)
        return TurnResult(reply=text, tainted=tool_runner.tainted, capped=False,
                          link_scope=tool_runner.link_scope.as_tuple(), stopped=True)
    except BaseException:
        # BaseException, not Exception: a Stop cancels the task, and the
        # placeholder bubble must still be closed (it also closes the bubble
        # a wall-time cap leaves — MORNING.md's "half-empty bubble").
        await _keep_cut_short(
            talk=talk, events=events, user_id=user_id, thread_id=thread_id, reply_id=reply_id,
            bot_id=bot.id, text="".join(draft), tainted=tool_runner.tainted,
        )
        raise
    await _finish_reply(
        talk=talk, events=events, user_id=user_id, thread_id=thread_id, reply_id=reply_id, bot_id=bot.id,
        text=reply_text, tainted=tool_runner.tainted, capped=capped,
        blocked=tool_runner.block is not None or tool_runner.parked is not None or bool(tool_runner.plan.steps),
    )
    return TurnResult(reply=reply_text, tainted=tool_runner.tainted, capped=capped,
                      link_scope=tool_runner.link_scope.as_tuple(), own_sites=tuple(sorted(tool_runner.own_sites)),
                      block=tool_runner.block, parked=tool_runner.parked, plan=tool_runner.plan.steps,
                      wall=tool_runner.wall)
