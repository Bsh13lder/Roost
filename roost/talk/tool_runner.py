"""``ToolRunner`` — dispatches one ``ToolCallRequested`` through the gate
and the bot's desk (spec §4.2). Split out of ``roost/talk/turn.py`` so
the calls-in-flight bookkeeping (Task 2: a call running at Stop or a
crash is reported "interrupted, outcome unknown") is testable on its
own, independent of the step loop that drives it.
"""

from __future__ import annotations

import asyncio
import html
import logging
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING, Any, Awaitable, Callable
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import ValidationError

from roost.desk.card_redact import hide_card_numbers
from roost.approvals import topics
from roost.approvals.floor import hard_floor
from roost.approvals.models import ApprovalState, CardTooBig, PendingCall, steps_json
from roost.approvals.plan import PlanDraft
from roost.approvals.preview import preview_call
from roost.approvals.rows import with_rows
from roost.approvals.texts import CANT_SHOW_TEXT, CARD_TOO_BIG_TEXT, NEEDS_YOUR_OK_TEXT, NOT_ASKABLE_TEXT, NOT_PERFORMED_TEXT, PARKED_TEXT, PLANNED_TEXT
from roost.bots.models import BotStatus
from roost.bots.status import ActivityBoard
from roost.choices.decisions import DecisionBook
from roost.choices.texts import CHOICE_PARKED_TEXT
from roost.choices.tool import park_choice
# STUCK_CHALLENGE_WAIT_SECONDS is imported by name and read at call time, so tests patch this module's copy.
from roost.constants import (
    COMPUTERS_BUSY_TEXT, CU_ACT_TOOLS, CU_MAX_MODEL_STEPS, CU_TOOLS, INFLIGHT_DESCRIPTION_CHARS,
    STEER_SIDE_EFFECT_TOOLS, STUCK_CHALLENGE_WAIT_SECONDS,
)
from roost.computer_use import steps
from roost.computer_use.runner import ComputerUse, CuOutcome, CuRun, ScreenKit
from roost.desk import Desk, DeskBusy, DeskUnavailable, PageText
from roost.desk.crash import PageKeepsCrashing
from roost.desk.control import ControlLock
from roost.desk.stuck import Block, host_of_url, names_sign_in
from roost.desk.url_policy import UrlBlocked, check_url
from roost.events.hub import EventHub
from roost.helpers.args import (
    BAD_HELPERS_ARGS_TEXT, NO_HELPERS_TEXT, NO_NESTED_HELPERS_TEXT, SendHelpersArgs, sending_line,
)
from roost.llm.types import ToolCallRequested
from roost.signin.texts import SIGN_IN_REQUESTED_TEXT, SITE_NOT_IN_SCOPE_TEXT
from roost.signin.secret_tool import ASKED_TEXT as SECRET_ASKED_TEXT, secret_field_block
from roost.signin.tool import sign_in_block
from roost.create_check.guard import OwnerSource
from roost.talk.domain_tools import DomainTools, RecordContext
from roost.talk.gate import REFUSAL_TEXT, Gate, GateContext
from roost.talk.instructions import (
    ASK_ONLY_IN_CHAT_TEXT, ASKED_FOR_HELP_TEXT, BAD_HELP_ARGS_TEXT, CONTROL_HANDED_BACK_TEXT, CONTROL_HELD_TEXT,
    SIGN_IN_PAGE_NOTE, STUCK_NOT_PERFORMED_TEXT, blocked_result_text, refused_once_text,
    stuck_result_text,
)
from roost.research.results import parse_results
from roost.research.search import BAD_QUERY_TEXT, SEARCH_ACTIVITY, result_scope, search_query, search_url, wrap_results
from roost.talk.link_scope import HOST_PREFIX, LinkScope
from roost.talk.new_site import OPEN_PAGE, fresh_site, page_step
from roost.talk.outcome import ToolOutcome
from roost.talk.owner_chat import OWNER_CHAT_OWN_TOOLS, OWNER_CHAT_REASON
from roost.talk.run_steps import RunSteps
from roost.talk.steer import RunSteer
from roost.talk.plain_address import plain_address
from roost.talk.server_error import reload_on_server_error
from roost.talk.stuck_check import AskForHelpArgs, Fetch, check_page
from roost.talk.tool_catalog import CATALOG
from roost.talk.team_tools import TeamTools
from roost.timezones import local_tz

logger = logging.getLogger(__name__)

# The audit key of an act refused while you hold (or just handed back) the computer (refusal_keys.py's table).
_HANDS_KEYS = {CONTROL_HELD_TEXT: "held", CONTROL_HANDED_BACK_TEXT: "handed_back"}

_BLOCKED_TEXT = "Blocked: that address is not allowed."
SIGN_IN_REASON = "login"   # the stuck detector's sign-in page: read with a note, never a card by itself
_DESK_UNAVAILABLE_TEXT = "Your computer is unavailable right now."

if TYPE_CHECKING:
    from roost.helpers.tools import HelperTools

InflightRecorder = Callable[[str | None], Awaitable[None]]


_FILE_TEXT_ARGS = frozenset({"text", "edits", "new_text", "base_hash"})


def describe_call(call: ToolCallRequested) -> str:
    """``open_page(https://example.com)`` — what an interrupted-call note quotes."""
    hidden = _FILE_TEXT_ARGS if call.name.startswith("mac_") else frozenset()   # a file's text never rides in a note
    args = ", ".join(str(value) for key, value in call.arguments.items() if key not in hidden)
    return f"{call.name}({args})"[:INFLIGHT_DESCRIPTION_CHARS]


def _without_one(labels: tuple[str, ...], label: str) -> tuple[str, ...]:
    index = labels.index(label)
    return labels[:index] + labels[index + 1:]


def escape_tags(text: str) -> str:
    """Neutralize ``&``/``<``/``>``/quotes so ``text`` can never smuggle a
    fake closing tag (or a fake attribute) into whatever structural
    wrapper it's about to be embedded in.

    Fix round 1, finding 3: ``&`` MUST be escaped first (``html.escape``
    does this). A page whose raw text already contains the literal,
    pre-entity-encoded string ``"&lt;/untrusted_page&gt;"`` has no real
    ``<``/``>`` characters in it at all -- escaping ``<``/``>`` alone
    would leave that string byte-for-byte identical to how THIS function
    escapes a real ``</untrusted_page>``, letting the page's own text
    impersonate our wrapper's closing tag. Escaping ``&`` first turns the
    attacker's literal ampersand into ``&amp;`` (``"&amp;lt;...&amp;gt;"``),
    which no longer collides with anything this function itself produces.
    """
    return html.escape(text, quote=True)


def host_of(url: str) -> str:
    return urlsplit(url).hostname or url


def wrap_page(page: PageText) -> str:
    return f'<untrusted_page url="{escape_tags(page.url)}">{escape_tags(hide_card_numbers(page.text))}</untrusted_page>'


def page_result_text(page: PageText, text: str) -> str:
    """§4: a read that came after the bot's tab crashed and was opened again starts with the fixed notice (never a
    word of the page); an ordinary read is ``text`` alone."""
    return f"{page.notice} {text}" if page.notice else text


def _to_matched_url(call: ToolCallRequested, url: str | None) -> ToolCallRequested:
    """R3: a guarded ``open_page`` goes to the scope entry the gate matched,
    never to the model's own spelling of it."""
    return call if url is None else replace(call, arguments={**call.arguments, "url": url})


@dataclass(frozen=True)
class RunnerSnapshot:
    """What a run knows that a helper must inherit, or hand back: its taint, the links it may open,
    whether its link guard is on and whether record text is in its context."""

    tainted: bool
    link_scope: LinkScope
    link_guard: bool
    sees_records: bool


class ToolRunner:
    """Dispatches one ``ToolCallRequested`` through the gate and the bot's
    desk, team or domain tools, tracking this run's taint, whether it can
    see the user's records (R2), the links its chain may open (D4), how
    many records it created (D3), the last page host and the calls in
    flight (spec §4.2)."""

    def __init__(
        self, *, user_id: str, bot_id: str, desk: Desk, gate: Gate, activity: ActivityBoard, events: EventHub,
        allowed: frozenset[str], tainted: bool = False, record_inflight: InflightRecorder | None = None,
        team: TeamTools | None = None, domain: DomainTools | None = None,
        link_scope: LinkScope = LinkScope(), link_guard: bool = False, sees_records: bool = False,
        control: ControlLock | None = None, cards: bool = False, thread_id: str | None = None,
        helpers: "HelperTools | None" = None, helper_number: int | None = None,
        approval: ApprovalState | None = None, mac_writes_now: Callable[[], int] | None = None,
        decisions: DecisionBook | None = None, from_routine: bool = False, run_id: str | None = None,
        screen: ScreenKit | None = None,
        user_started: bool = False, steer: RunSteer | None = None, run_steps: RunSteps | None = None,
        site_fresh: bool = False, owner: OwnerSource | None = None, check_model: str | None = None,
        own_sites: frozenset[str] = frozenset(),
    ) -> None:
        self._own_sites = own_sites   # sites the gate let this run open itself, or a card's continue item carried
        self._check_model = check_model   # the bot's own model: the gate's model checks run on it (owner, 2026-11-03)
        self._owner = owner   # the create check reads your newest own messages here (None: no check, refused)
        self._run_steps = run_steps   # the activity pill: each call's start and end in plain words
        self._steer = steer   # steer design: every completed call is reported (Stop's line, no restart after a write)
        self._from_routine = from_routine
        self._user_started = user_started   # a 1:1 run of the user's own messages: routines may be written directly
        self._run_id = run_id
        self._decisions = decisions
        self._user_id = user_id
        self._bot_id = bot_id
        self._thread_id = thread_id
        self._helpers = helpers
        self._helper_number = helper_number   # set for a helper's runner: its announcements say so, it sends none
        self._desk = desk
        self._gate = gate
        self._activity = activity
        self._events = events
        self._allowed = allowed
        self._record_inflight = record_inflight
        self._team = team
        self._domain = domain
        self._inflight: tuple[str, ...] = ()
        self._creates = 0
        self._link_guard = link_guard
        self._sees_records = sees_records
        self._control = control
        self._cards = cards                                   # this run may open Stuck cards (your own chat, R5)
        self._mac_writes_now = mac_writes_now
        self._approval = approval                             # None: today's verdicts (no Ask cards)
        self._refused_hosts: frozenset[str] = frozenset()      # hosts that refused once in this run
        self.link_scope = link_scope
        self._tainted = tainted
        # W6/W7: may open any safe site with no card, until this run reads new outside content. A run of your new
        # messages is told so (site_fresh, even with tainted history); a clean run of yours always is.
        self._site_fresh = site_fresh or (user_started and not tainted and not link_guard)
        self.last_host: str | None = None
        self.last_url: str | None = None
        self.block: Block | None = None                       # a page that stayed blocked, or ask_for_help
        self.wall: Block | None = None                        # a block met where no Stuck card may open (a routine)
        self.parked: PendingCall | None = None                # the call that asked: the run stops after its step
        self.plan = PlanDraft()                               # Review first: the steps collected, never run here
        self._computer = self._screen_loop(screen, desk, gate, events, control)   # C3: None without screen tools

    @property
    def tainted(self) -> bool:
        return self._tainted

    @tainted.setter
    def tainted(self, value: bool) -> None:
        """Marking the run tainted means it just took in outside content: that also ends its site freshness."""
        self._tainted = value
        if value:
            self._site_fresh = False

    @property
    def own_sites(self) -> frozenset[str]:
        """The sites the gate let this run open itself (and those carried in): the run after a card keeps them."""
        computer = self._computer.own_sites if self._computer is not None else frozenset()
        return self._own_sites | computer

    @property
    def site_fresh(self) -> bool:
        """W7: this run has read no new outside content yet, so it may still open any safe site."""
        return self._site_fresh

    def saw_content(self, *, tainted: bool) -> None:
        """Content reached the run: a tainted piece taints it (and ends freshness); a clean one changes nothing."""
        if tainted:
            self.tainted = True

    def _screen_loop(self, screen: ScreenKit | None, desk: Desk, gate: Gate, events: EventHub,
                     control: ControlLock | None) -> ComputerUse | None:
        if screen is None or not frozenset(CU_TOOLS) & self._allowed:
            return None
        # The computer card and the activity pill share one run id, so the web draws them as one.
        fallback = self._run_steps.run_id if self._run_steps is not None else str(uuid4())
        run = CuRun(screen.config, self._user_id, self._bot_id, self._thread_id, self._run_id or fallback)
        return ComputerUse(run, desk=desk, gate=gate, events=events, leases=screen.leases, control=control,
                           announce=self._announce, sleep=screen.sleep, signals=screen.signals,
                           own_sites=self._own_sites)

    def newest_image(self) -> bytes | None:
        """The newest look's picture, for the next model request (only the newest one is ever sent)."""
        return self._computer.newest_image() if self._computer is not None else None

    def begin_step(self) -> None:
        """A new model step: one more screen action may run."""
        if self._computer is not None:
            self._computer.new_step()

    def step_limit(self, default: int) -> int:
        """``CU_MAX_MODEL_STEPS`` once this run has used its screen, else ``default``."""
        used = self._computer is not None and self._computer.state.used_screen
        return max(default, CU_MAX_MODEL_STEPS) if used else default

    async def close_screen(self) -> None:
        """The run ended: disarm the browser guards and free the computer for the next loop. Never raises."""
        if self._computer is not None:
            await self._computer.close()

    def _record_context(self) -> RecordContext:
        return RecordContext(user_id=self._user_id, bot_id=self._bot_id, tainted=self.tainted,
                             thread_id=self._thread_id, from_routine=self._from_routine, run_id=self._run_id,
                             user_started=self._user_started)

    def _context(self) -> GateContext:
        """D4's guard is on for a run carrying another bot's outside content,
        and (R2) for any tainted run that can see the user's records — in
        either order — so a page can't steer them out inside a URL."""
        guarded = self._link_guard or (self.tainted and self._sees_records)
        return GateContext(
            allowed=self._allowed, tainted=self.tainted, creates=self._creates,
            link_guard=self.link_scope if guarded else None, approval=self._approval, owner_chat=self._user_started,
            site_fresh=self._site_fresh, check_model=self._check_model,
        )

    def snapshot(self) -> RunnerSnapshot:
        """The taint, link scope, effective link guard (D4 and R2) and records flag, as they stand now."""
        guarded = self._link_guard or (self.tainted and self._sees_records)
        return RunnerSnapshot(self.tainted, self.link_scope, guarded, self._sees_records)

    async def run(self, call: ToolCallRequested) -> str:
        """One call, told to the activity pill as a step that starts and then ends (``failed`` if it raised)."""
        if self._run_steps is None:
            return await self._run_call(call)
        step = await self._run_steps.tool_start(call.name, call.arguments)
        try:
            text = await self._run_call(call)
        except BaseException:
            await self._run_steps.tool_end(step, ok=False)
            raise
        await self._run_steps.tool_end(step, ok=True)
        return text

    async def _run_call(self, call: ToolCallRequested) -> str:
        if self.block is not None:
            return STUCK_NOT_PERFORMED_TEXT   # R1: the turn stops after this step, and nothing more runs in it
        if self.parked is not None:
            return NOT_PERFORMED_TEXT         # the turn stops after the step that asked; nothing more runs in it
        if self._approval is not None and self._mac_writes_now is not None:
            self._approval = replace(self._approval, mac_writes=self._mac_writes_now())   # the floor counts live
        if call.name in CU_TOOLS:
            return await self._screen(call)
        verdict = await self._gate.decide(self._user_id, self._bot_id, call.name, call.arguments, self._context(),
                                          owner=self._owner)
        if verdict.decision in ("do", "plan") and await self._resolved_floor(call):
            verdict = replace(verdict, decision="ask")   # the resolved text hits the hard floor: asks in every mode
            if not self._cards_open():
                return NEEDS_YOUR_OK_TEXT
        if verdict.decision == "ask":
            return await self._park(call, open_url=verdict.url if call.name == OPEN_PAGE else None)
        if verdict.decision == "plan":
            return await self._plan_step(call)
        if verdict.decision != "do":   # fail closed: only a "do" verdict runs here
            if call.name == "send_helpers" and self._helper_number is not None:
                return NO_NESTED_HELPERS_TEXT   # depth is 1; the gate has already audited it as never
            offered = await self._offer(call) if verdict.reason == "tainted_refused" else None
            return offered or verdict.text or REFUSAL_TEXT
        approved = _to_matched_url(call, verdict.url)
        if verdict.reason == "fresh_open":
            await self._allow_fresh_site(str(approved.arguments["url"]))
        label = describe_call(approved)
        await self._set_inflight((*self._inflight, label))
        text = await self._dispatch(approved, checked=verdict.reason == "checked_create",
                                    owner_ok=verdict.reason == OWNER_CHAT_REASON and call.name in OWNER_CHAT_OWN_TOOLS)
        # Deliberately not in a ``finally`` (see Night-1): a call cancelled by
        # Stop stays recorded as "interrupted, outcome unknown".
        await self._set_inflight(_without_one(self._inflight, label))
        self._note_done(call.name)
        return text

    def _note_done(self, name: str) -> None:
        """Steer: a completed call. A write, an act or a call that leaves something behind is a side effect."""
        if self._steer is None:
            return
        kind = CATALOG[name].kind if name in CATALOG else "act"
        domain = self._domain is not None and self._domain.handles(name)
        self._steer.note_done(name, self._domain.activity(name) if domain else None,
                              side_effect=kind != "read" or name in STEER_SIDE_EFFECT_TOOLS)

    async def _offer(self, call: ToolCallRequested) -> str | None:
        """A taint refusal the user can overcome with one click (a refused ``remember``): the handler posts the
        line and says so; nothing runs."""
        if self._domain is None or not self._domain.handles(call.name):
            return None
        return await self._domain.offer(call.name, dict(call.arguments), self._record_context())

    def _cards_open(self) -> bool:
        return self._approval is not None and self._approval.cards

    async def _resolved_floor(self, call: ToolCallRequested) -> bool:
        """True when a Mac write's RESOLVED text (what it would add, not its argument fragments) hits the floor."""
        if (self._approval is None or self._domain is None or not self._domain.handles(call.name)
                or CATALOG[call.name].kind == "read" or topics.topic_of(call.name) != "files"):
            return False
        ctx = self._record_context()
        pending = await self._domain.prepare(call.name, dict(call.arguments), ctx)
        return isinstance(pending, PendingCall) and pending.floor is not None

    async def _park(self, call: ToolCallRequested, *, open_url: str | None = None) -> str:
        """An ``ask`` verdict: remember the call as the step the card will show, and stop the run after this
        step. A handler may refuse first with a plain sentence (no card). An address off the link scope is the
        Open card's step, built from the canonical address the gate checked."""
        ctx = self._record_context()
        pending = page_step(open_url) if open_url is not None else await self._pending_for(call, ctx)
        if isinstance(pending, str):
            return pending
        floor = None
        if self._approval is not None and CATALOG[call.name].kind != "read":
            floor = hard_floor(call.name, call.arguments, self._approval)
        pending = replace(pending, floor=floor or pending.floor)
        try:
            steps_json((pending,))
        except CardTooBig:
            return CARD_TOO_BIG_TEXT
        self.parked = pending
        await self._announce("asking you")
        return PARKED_TEXT

    async def _plan_step(self, call: ToolCallRequested) -> str:
        """A ``plan`` verdict: build the step the Proposal card will show and keep it. Nothing runs."""
        ctx = self._record_context()
        pending = await self._pending_for(call, ctx)
        if isinstance(pending, str):
            return pending
        longer = self.plan.add(replace(pending, floor=None))
        try:
            steps_json(longer.steps)
        except CardTooBig:
            return CARD_TOO_BIG_TEXT
        self.plan = longer
        if self._approval is not None:
            self._approval = replace(self._approval, plan_steps=len(longer.steps))
        return PLANNED_TEXT.format(n=len(longer.steps))

    async def _pending_for(self, call: ToolCallRequested, ctx: RecordContext) -> PendingCall | str:
        if self._domain is None or not self._domain.handles(call.name):
            return NOT_ASKABLE_TEXT      # a tool a card can't run later (the team's): never parked half-done
        prepared = await self._domain.prepare(call.name, dict(call.arguments), ctx)
        if isinstance(prepared, str):
            return prepared
        step = prepared if prepared is not None else preview_call(call.name, call.arguments, topics.topic_of(call.name))
        shown = with_rows(step)      # every stored argument becomes a row, or there is no card
        return CANT_SHOW_TEXT if shown is None else shown

    async def _dispatch(self, call: ToolCallRequested, *, checked: bool = False, owner_ok: bool = False) -> str:
        """``checked``: the create check let a tainted ``create_bot`` through (its card says so). ``owner_ok``: the
        gate let one of the bot's own things run in your own chat (``owner_chat_change``), so its handler runs clean."""
        if call.name == "get_time":
            await self._announce("checking the time")
            return datetime.now(local_tz()).isoformat()
        if call.name in ("open_page", "read_page"):
            refusal = await self._hands_refusal()
            if refusal is not None:
                return refusal
            return await (self._open_page(call.arguments) if call.name == "open_page" else self._read_page())
        if call.name == "web_search":
            return await self._hands_refusal() or await self._web_search(call.arguments)
        if call.name == "ask_bot" and self._team is not None:
            outcome = await self._team.ask_bot(call.arguments, tainted=self.tainted,
                                               link_scope=self.link_scope.as_tuple(), announce=self._announce)
            return self._absorb_answer(outcome)
        if call.name == "list_bots" and self._team is not None:
            await self._announce("checking on the team")
            return (await self._team.list_bots()).text
        if call.name == "suggest_bot" and self._team is not None:
            return (await self._team.suggest_bot(call.arguments, tainted=self.tainted)).text
        if call.name == "create_bot" and self._team is not None:
            # No announce here: create_bot announces the name only after CreateBotArgs validates it.
            return (await self._team.create_bot(call.arguments, tainted=self.tainted,
                                                checked=checked, announce=self._announce)).text
        if call.name in ("suggest_model", "set_bot_model") and self._team is not None:
            return await self._run_model_tool(call, owner_ok=owner_ok)
        if call.name == "send_helpers":
            return await self._send_helpers(call.arguments)
        if call.name == "ask_choice":
            return await self._ask_choice(call.arguments)
        if call.name == "ask_for_help":
            return await self._ask_for_help(call.arguments)   # needs no browser: never behind _hands_refusal
        if call.name == "request_sign_in":
            return await self._request_sign_in(call.arguments)
        if call.name == "ask_secret_field":
            return await self._ask_secret_field(call.arguments)
        if self._domain is not None and self._domain.handles(call.name):
            return await self._run_domain(call, owner_ok=owner_ok)
        return REFUSAL_TEXT

    async def _screen(self, call: ToolCallRequested) -> str:
        """C3: a screen tool. You holding the computer comes first; a look, wait or scroll is judged like any
        read; a click, typing or key press is judged inside ``ComputerUse`` on what the page shows."""
        if self._computer is None or call.name not in self._allowed:
            verdict = await self._gate.decide(self._user_id, self._bot_id, call.name, call.arguments, self._context())
            return verdict.text or REFUSAL_TEXT
        refusal = await self._hands_refusal()
        if refusal is not None:
            if call.name in CU_ACT_TOOLS:   # an act refused before any judging still leaves its audit row
                await self._gate.record_refused(self._user_id, self._bot_id, call.name, dict(call.arguments),
                                                tainted=self.tainted, refused=_HANDS_KEYS.get(refusal, "held"))
            return refusal
        if call.name not in CU_ACT_TOOLS:
            verdict = await self._gate.decide(self._user_id, self._bot_id, call.name, call.arguments, self._context())
            if verdict.decision != "do":
                return verdict.text or REFUSAL_TEXT
        label = f"{call.name}()"   # never the arguments: typed text must not ride in a note
        await self._set_inflight((*self._inflight, label))
        outcome = await self._computer.handle(call, self._context())
        await self._set_inflight(_without_one(self._inflight, label))
        self._note_done(call.name)
        return await self._absorb_screen(outcome)

    async def _absorb_screen(self, outcome: CuOutcome) -> str:
        if outcome.looked:
            self.tainted = True                       # the page reached the model, like read_page
        if outcome.url:
            self.last_url = outcome.url
            self.last_host = host_of(outcome.url)
        if outcome.parked is not None:
            self.parked = outcome.parked
            await self._announce("asking you")
            return PARKED_TEXT
        if outcome.block is None:
            return outcome.text
        if outcome.block.reason == SIGN_IN_REASON:    # owner, 2026-11-03: the bot signs in itself
            return f"{outcome.text}\n{SIGN_IN_PAGE_NOTE}"
        return self._screen_block(outcome.text, outcome.block)

    def _screen_block(self, text: str, block: Block) -> str:
        """A look that met a sign-in or code page answers like read_page; a second miss or a spent budget carries
        its own note. A Stuck card only in your own chat (R5); anywhere else a loud result."""
        if block.reason != "asked":
            return self._answer_block(PageText(url=block.url, title="", text="", truncated=False), block)
        if not self._cards:
            self.wall = block
            return f"Blocked: {text} {block.note} You can't get past it in this task. Tell whoever asked."
        self.block = block
        return f"{text} Stuck: the user has been asked for help ({block.note})."

    async def _send_helpers(self, arguments: dict[str, Any]) -> str:
        if self._helpers is None:
            return NO_HELPERS_TEXT
        try:
            args = SendHelpersArgs.model_validate(arguments)
        except ValidationError:
            return BAD_HELPERS_ARGS_TEXT
        await self._announce(sending_line(args))
        outcome = await self._helpers.send(args, snapshot=self.snapshot(), allowed=self._allowed)
        return self._absorb_answer(outcome)   # a helper's pages taint this run, and its links join the scope

    async def _run_model_tool(self, call: ToolCallRequested, *, owner_ok: bool = False) -> str:
        if call.name == "suggest_model":
            return (await self._team.models.suggest_model(call.arguments, tainted=self.tainted)).text
        return (await self._team.models.set_bot_model(call.arguments, tainted=self.tainted and not owner_ok,
                                                      announce=self._announce)).text

    async def _run_domain(self, call: ToolCallRequested, *, owner_ok: bool = False) -> str:
        await self._announce(self._domain.activity(call.name))
        ctx = self._record_context()
        if owner_ok:
            ctx = replace(ctx, tainted=False)   # your own chat asked for it: saved clean, with its Undo line
        outcome = await self._domain.run(call.name, call.arguments, ctx)
        self.saw_content(tainted=outcome.tainted)       # loading a tainted record taints the run (§8.2)
        self._sees_records = True                         # R2: record text is now in this run's context
        self._creates += int(outcome.created)
        return outcome.text

    async def _hands_refusal(self) -> str | None:
        """S1.8: while the user holds control, a browser call waits for them and is never performed."""
        if self._control is None or self._control.held(self._bot_id) is None:
            return None
        await self._announce("waiting: you have control of my computer")   # tests match this text
        outcome = await self._control.wait_for_hands(self._bot_id)
        if outcome == "free":
            return None
        return CONTROL_HANDED_BACK_TEXT if outcome == "handed_back" else CONTROL_HELD_TEXT

    async def _open_page(self, arguments: dict[str, Any]) -> str:
        url = str(arguments.get("url", ""))
        await self._announce(f"opening {host_of(url)}")
        plain = plain_address(url)
        text = await self._load(lambda: self._desk.open_page(url), reload_errors=True,
                                plain=(lambda: self._desk.open_page(plain)) if plain else None)
        if self._computer is not None:                         # a Linux computer: the computer card's step
            host = steps.step_host(url)
            await self._computer.publish_step("open_page", f"Opened {host or 'a page'}", host)
        return text

    async def _allow_fresh_site(self, url: str) -> None:
        """W6/W7: a site a fresh run opens itself stays open to this run after its page taints it: open_page may go
        back to it (a ``host:`` entry) and the computer's fence lets it browse there. A page never widens either."""
        site = fresh_site(url)
        if not site:
            return
        self.link_scope = self.link_scope.merge(LinkScope.of((f"{HOST_PREFIX}{site}",)))
        self._own_sites = self._own_sites | {site}
        if self._computer is None:
            return
        try:
            await self._computer.allow_site(site)
        except Exception:   # the guards keep the narrower fence: the open is refused by the browser, never widened
            logger.warning("Could not widen the browser guards of bot %s", self._bot_id, exc_info=True)

    async def _web_search(self, arguments: dict[str, Any]) -> str:
        """A3: the fixed search host's results, read like a page (it taints the run); each result's host joins the
        link scope so open_page may open it."""
        query = search_query(arguments)
        if query is None:
            return BAD_QUERY_TEXT
        await self._announce(SEARCH_ACTIVITY)
        try:
            found = await self._desk.search_page(search_url(query))
        except UrlBlocked:
            return _BLOCKED_TEXT
        except DeskBusy:
            return COMPUTERS_BUSY_TEXT
        except DeskUnavailable:
            return _DESK_UNAVAILABLE_TEXT
        results = parse_results(found.html)
        self._note_page(replace(found.page, text=""))
        self.link_scope = self.link_scope.merge(result_scope(results))
        return wrap_results(query, results)

    async def _read_page(self) -> str:
        await self._announce(f"reading {self.last_host}" if self.last_host else "reading the page")
        return await self._load(self._desk.read_page)

    async def _load(self, fetch: Fetch, *, reload_errors: bool = False, plain: Fetch | None = None) -> str:
        """Loads a page and runs rung 1 on it. The repeat is the same call (R4), so it
        keeps the URL check, the status capture and the reconnect. ``reload_errors``: a server error is loaded
        again first (owner, 2026-10-31), its plain address tried before that (``plain``, owner, 2026-11-01)."""
        try:
            page = await fetch()
            if reload_errors:
                page, fetch = await reload_on_server_error(page, fetch, plain=plain, sleep=asyncio.sleep,
                                                           announce=self._announce)
            checked = await check_page(page, fetch, wait_seconds=STUCK_CHALLENGE_WAIT_SECONDS,
                                       announce=self._announce, hands_taken=self._hands_taken,
                                       control=self._control, bot_id=self._bot_id)
        except UrlBlocked:
            return _BLOCKED_TEXT
        except DeskBusy:
            return COMPUTERS_BUSY_TEXT
        except PageKeepsCrashing as exc:    # §4: the fresh tab failed too; its own words, never "unavailable"
            return str(exc)
        except DeskUnavailable:
            return _DESK_UNAVAILABLE_TEXT
        if checked.block is None:
            return page_result_text(checked.page, self._absorb_page(checked.page))
        if checked.block.reason == SIGN_IN_REASON:   # owner, 2026-11-03: the bot signs in itself
            return f"{page_result_text(checked.page, self._absorb_page(checked.page))}\n{SIGN_IN_PAGE_NOTE}"
        return self._answer_block(checked.page, checked.block)

    def _hands_taken(self) -> bool:
        """The user holds this bot's computer right now (Take control)."""
        return self._control is not None and self._control.held(self._bot_id) is not None

    def _answer_block(self, page: PageText, block: Block) -> str:
        """A page still blocked after rung 1. It counts as read (taint, host, URL), but its
        text never reaches the model, so only its address joins the link scope, never the
        links in its text. The first refusal on a host is only a result (design §1).
        Outside your own chat a block is a loud result and never a card (R5)."""
        self._note_page(replace(page, text=""))
        if block.reason == "refused" and block.host not in self._refused_hosts:
            self._refused_hosts = self._refused_hosts | {block.host}
            return refused_once_text(block.host, page.status or 0)   # a refusal always carries 403 or 429
        if not self._cards:
            self.wall = block
            return blocked_result_text(block)
        self.block = block
        return stuck_result_text(block)

    def _note_page(self, page: PageText) -> None:
        self.last_host = host_of(page.url)
        self.last_url = page.url
        self.tainted = True
        self.link_scope = self.link_scope.with_page(page.url, page.text)

    def _absorb_page(self, page: PageText) -> str:
        self._note_page(page)
        return wrap_page(page)

    async def _ask_choice(self, arguments: dict[str, Any]) -> str:
        """Park this run on an options card (your own chat only); a decided question opens nothing."""
        pending = await park_choice(
            arguments, cards=self._cards, tainted=self.tainted, decisions=self._decisions, user_id=self._user_id,
            bot_id=self._bot_id, has_question_book="note_question" in self._allowed)
        if isinstance(pending, str):
            return pending
        self.parked = pending
        await self._announce("asking you")
        return CHOICE_PARKED_TEXT

    async def _ask_for_help(self, arguments: dict[str, Any]) -> str:
        """A block the detector can't see, such as a payment or identity check. The bot
        asks, and the turn stops after this step. Only in your own chat (R5)."""
        if not self._cards:
            return ASK_ONLY_IN_CHAT_TEXT
        try:
            args = AskForHelpArgs.model_validate(arguments)
        except ValidationError:
            return BAD_HELP_ARGS_TEXT
        url = self._card_address()
        await self._announce("asking you for help")
        self.block = Block(reason="asked", url=url, host=host_of_url(url), note=args.reason,
                           suggest_main_browser=args.suggest_main_browser, sign_in=names_sign_in(args.reason))
        return ASKED_FOR_HELP_TEXT

    async def _request_sign_in(self, arguments: dict[str, Any]) -> str:
        """The Sign-in card: the bot asks you to sign in on a site, and the turn stops after this step."""
        block = sign_in_block(arguments, cards=self._cards)
        if isinstance(block, str):
            return block
        if not self._may_sign_in_on(block):
            return SITE_NOT_IN_SCOPE_TEXT
        await self._announce(f"asking you to sign in on {block.host}")
        self.block = block
        return SIGN_IN_REQUESTED_TEXT.format(host=block.host)

    async def _ask_secret_field(self, arguments: dict[str, Any]) -> str:
        """B3: a Sign-in card with a masked field for the box in front; the turn stops after this step."""
        refusal = await self._hands_refusal()
        if refusal is not None:
            return refusal
        page = self._desk.page() if hasattr(self._desk, "page") else None
        block = await secret_field_block(arguments, cards=self._cards, page=page)
        if isinstance(block, str):
            return block
        await self._announce(f"asking you for your {block.field} on {block.host}")
        self.block = block
        return SECRET_ASKED_TEXT.format(kind=block.field, host=block.host)

    def _may_sign_in_on(self, block: Block) -> bool:
        """D4 for request_sign_in, as for open_page: a tainted or link-guarded run may ask only for the page it has
        open or a site already in its link scope, so web content can't plant the address you are sent to."""
        if not (self.tainted or self._link_guard):
            return True
        return block.host == host_of_url(self.last_url or "") or self.link_scope.allows(block.url)

    def _card_address(self) -> str:
        """The open page's address for an asked card, as ``check_url`` returns it, or ``""``
        when there is no web page to point at: nothing opened yet, or a fresh tab's
        ``about:blank``. The card then never names a page it can't open (Task 7 answers 400)."""
        if not self.last_url:
            return ""
        try:
            return check_url(self.last_url)
        except UrlBlocked:
            return ""

    def _absorb_answer(self, outcome: ToolOutcome) -> str:
        """A teammate's tainted answer taints this run and switches on the
        link guard for the rest of it (D4); the links its chain read join
        this run's scope. Any answer may carry the user's records (R2)."""
        self.saw_content(tainted=outcome.tainted)
        self._sees_records = True
        self.link_scope = self.link_scope.merge(LinkScope.of(outcome.link_scope))
        if outcome.tainted:
            self._link_guard = True
        return outcome.text

    async def _announce(self, activity: str) -> None:
        if self._helper_number is not None:
            activity = f"{activity} (helper {self._helper_number})"
        self._activity.set(self._bot_id, activity, tainted=self.tainted)
        await self._events.publish(self._user_id, {
            "type": "bot_status", "bot_id": self._bot_id,
            "status": BotStatus.ON_IT.value, "activity": activity,
        })

    async def _set_inflight(self, labels: tuple[str, ...]) -> None:
        self._inflight = labels
        if self._record_inflight is not None:
            await self._record_inflight("; ".join(labels) or None)
