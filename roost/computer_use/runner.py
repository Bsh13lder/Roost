"""``ComputerUse``: one run's screen loop on its bot's Linux computer (C3 design §6–§7, Task 12).

``ToolRunner`` hands it every screen tool call after ``_hands_refusal`` (you hold the computer: nothing runs). Then:

1. **The lease:** one loop per computer (``ComputerUseLease``); the first call takes it and arms the browser guards
   with this chat's site fence, plus the sites a site-fresh run of your chat opened itself (W6/W7, ``allow_site``).
   ``close()`` (in ``run_turn``'s ``finally``) disarms them and frees the lease.
2. **The loop's rules:** ``precheck`` (budget, one screen action per step, a fresh look, the control epoch).
3. **look / wait_ready / scroll** run at once; a look's stuck check hands off to the Stuck flow as ``read_page`` does.
4. **An act** waits for the page, is resolved from the page (``resolve.py``), judged by the gate on that resolution
   only, then parks on a card (with the crop), is refused, or runs: move to the point, check the node under the
   pointer again, click / type / press through ``desk.send_input``, publish ``computer_pointer`` (no text), wait
   for the page, and report the address and what the guards saw.
5. **The ladder:** a miss (not found, covered) says "look again and try once more"; the second miss on the same
   aim, or a spent budget, ends in a Stuck card in your own chat (else a ``Blocked:`` result).

The approved re-run (``rerun``) resolves the page again and acts only when ``same_target`` holds.

Full computer, Step 1: before every look and act the runner asks the computer what is in front
(``Desk.front_window()``). Brave: all of the above, unchanged (the guards are armed then, so a closed Brave never
blocks the desktop). Anything else: a whole-screen look with Brave's windows black, and clicks, typing, keys and
scrolls anywhere but in Brave, free (D1) but under every loop rule (``roost/computer_use/desktop.py``). ``open_app``
opens a fixed app or an installed package.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ValidationError

from roost.approvals.floor import act_commits
from roost.approvals.models import CardTooBig, DraftBox, PendingCall, steps_json
from roost.approvals.rows import with_rows
from roost.approvals.texts import CARD_TOO_BIG_TEXT
from roost.auto_review.constants import AUTO_REVIEW_REQUEST_MESSAGES
from roost.auto_review.guard import ReviewPage
from roost.computer_use import aim
from roost.computer_use import session as loop
from roost.computer_use.commit_words import commit_class
from roost.computer_use.covered import closers_of, covered_text, point_miss_text
from roost.computer_use.fence import SiteFence
from roost.computer_use.gate_rules import floor_of, typed_chars_of
from roost.computer_use import steps, tabs
from roost.computer_use.inputs import NO_ARGS, TOOL_INPUTS
from roost.computer_use.lines import act_line, card_title, label_of, screen_line
from roost.computer_use.look import glance, look
from roost.computer_use.marks import PageMarks
from roost.computer_use.models import (
    COUNT_FREE_CLASSES, ActResolution, LookIn, OpenAppIn, PageTarget, ReadPdfIn, ReadTextIn, SavedLoginIn, VaultLoginIn,
    ScreenshotIn, ScrollIn,
    resolution_to_json,
)
from roost.computer_use.outcome import CuOutcome
from roost.computer_use.runner_desktop import DesktopActs
from roost.computer_use.runner_lessons import LessonWatch
from roost.computer_use.runner_read import PageReading
from roost.computer_use.runner_rerun import ApprovedRerun
from roost.computer_use.runner_typing import NOTHING_TYPED, CheckedTyping
from roost.computer_use.saved_login import SavedLogin
from roost.computer_use.vault_login import VaultLogin
from roost.computer_use.send_screen import send_screen
from roost.computer_use.screen_grab import ScreenGrabError
from roost.computer_use.scroll import scroll_pieces
from roost.computer_use.refusal_keys import refusal_key
from roost.computer_use.resolve import resolve_click, resolve_key, resolve_type
from roost.computer_use.run_tabs import RunTabs
from roost.computer_use.run_fence import chat_fence, widened
from roost.computer_use.text_source import load_approved_texts, text_flags, your_messages
from roost.owner_words.again import approved_before
from roost.owner_words.constants import OWNER_WORDS_CLASSES
from roost.owner_words.quote import your_quote
from roost.config import Config
from roost.constants import CU_BLIND_SCROLLS_MAX, COMPUTERS_BUSY_TEXT, CU_ACT_TOOLS, CU_KEYS, CU_LABEL_SHOWN_CHARS, CU_READY_TIMEOUT_S
from roost.desk import DeskAsleep, DeskBusy, DeskUnavailable, InputRefusedByComputer, ScreenInput
from roost.desk.cdp import CdpClientError
from roost.desk.control import ControlLock
from roost.desk.page_geometry import viewport_to_screen
from roost.desk.ready import wait_ready
from roost.desk.stuck import Block, host_of_url
from roost.desk.url_policy import UrlBlocked, check_url
from roost.events.hub import EventHub
from roost.lessons.signals import LessonSignals
from roost.llm.types import SCREENSHOT_SHOWN, ToolCallRequested
from roost.talk.verdict import GateContext

from roost.talk.plain_address import apply_address, plain_address
from roost.computer_use.texts import (  # noqa: F401  (re-exported: the tests and ToolRunner read them here)
    _INPUT_WORDS, AREA_OFF_SCREEN_TEXT, ASLEEP_TEXT, BAD_ARGS_TEXT, BLIND_SCROLL_TEXT, BLOCKED_NOTE, BROWSER_SILENT_TEXT, BUDGET_NOTE,
    CHANGED_TEXT, CHECK_TEXT, CHOOSER_NOTE, COVERED_TEXT, FOCUS_MOVED_TEXT, GUARDS_TEXT, HELD_TEXT, INDEX_KEY_TEXT,
    APPLY_FORM_NOTE, KEPT_TAB_NOTE, MISS_NOTE, PLAIN_ADDRESS_NOTE, MISS_TEXT, MOVED_TEXT, NO_AREA_TEXT, NO_MARK_TEXT, NO_SCREEN_TEXT, POPUP_NOTE, STALE_MARK_TEXT,
    SCROLLED_TEXT, SENT_THEN_SILENT_TEXT, SENT_WHAT, STEP_MARKS, WAKING_LINE, WOKE_LOOK_FIRST_TEXT, YOU_ASKED_MARK,
)

logger = logging.getLogger(__name__)

Announce = Callable[[str], Awaitable[None]]
LINUX = "linux"
GLANCE_TEXT = "What the page shows now (check what you expected here; look with a picture only to see images):"


@dataclass(frozen=True)
class CuRun:
    """Who and where one loop runs."""

    config: Config
    user_id: str
    bot_id: str
    thread_id: str | None
    run_id: str


@dataclass(frozen=True)
class ScreenKit:
    """What ``TurnRunner`` hands each run so its ``ToolRunner`` can build a ``ComputerUse``."""

    config: Config
    leases: loop.ComputerUseLease
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    signals: LessonSignals | None = None      # lessons: app.state.lesson_signals (None: nothing is recorded)


class _NoTyped:
    """``look`` reads the expect line only: whether a field still holds what was typed needs an in-page compare
    that isn't built yet, and a wrong "no" would make the bot type again."""

    def __init__(self, expect: str) -> None:
        self.expect = expect
        self.typed: dict[str, str] = {}


def _first_error(exc: ValidationError) -> str:
    errors = exc.errors()
    return str(errors[0].get("msg", "the call is not valid")) if errors else "the call is not valid"


def _same_node(a, b) -> bool:
    return a is not None and b is not None and (a.node_id, a.kind, a.text) == (b.node_id, b.kind, b.text)


def _aim_words(call: ToolCallRequested) -> str:
    """What a missed click or type looked for: its target's words, one line and cut short, else "that"."""
    target = call.arguments.get("target")
    text = target.get("text") if isinstance(target, dict) else None
    words = " ".join(text.split())[:CU_LABEL_SHOWN_CHARS] if isinstance(text, str) else ""
    return f"'{words}'" if words else "that"


def _by_point(call: ToolCallRequested) -> bool:
    """The click aimed at a point (x and y), not at a look's number or a control's words."""
    return call.arguments.get("index") is None and not call.arguments.get("target")


def _card_url(url: str) -> str:
    try:
        return check_url(url) if url else ""
    except UrlBlocked:
        return ""


class ComputerUse(DesktopActs, ApprovedRerun, PageReading, CheckedTyping, LessonWatch, SavedLogin, VaultLogin):
    def __init__(self, run: CuRun, *, desk: Any, gate: Any, events: EventHub, leases: loop.ComputerUseLease,
                 control: ControlLock | None, announce: Announce,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 signals: LessonSignals | None = None, own_sites: frozenset[str] = frozenset()) -> None:
        self._run = run
        self._desk = desk
        self._gate = gate
        self._events = events
        self._leases = leases
        self._control = control
        self._chat_line = announce
        self._announce = self._say                   # every line is also the computer card's step (steps.py)
        self._tool: str | None = None                # the screen tool ``handle`` is running (None: a card's re-run)
        self._front_brave = True                     # Brave was in front for this call (else no host)
        self._step_no = 0
        self._clock = clock
        self._sleep = sleep
        self._image: bytes | None = None
        self._fence: SiteFence | None = None
        self._own_sites = own_sites   # W6: sites this run opened while fresh, or a card's continue item carried in
        self._armed = False
        self._act_epoch = 0                          # ControlLock.epoch when this call began
        self._audited = False                        # the gate wrote this act's row
        self._resolved: ActResolution | None = None  # this act's resolution, for its audit row
        self._input_sent = False                     # a click, typing or key of this call reached the keeper
        # What this run typed into each field (target_key -> text), in memory only, so contact and secret are
        # judged on what the field ends up holding, not one piece at a time. Never logged, never in LoopState.
        self._field_text: MappingProxyType[str, str] = MappingProxyType({})
        self._typed_boxes: tuple[DraftBox, ...] = ()   # the Send card's boxes (runner_typing.py), memory only
        self._seen = ""                                 # the page text this run was shown (page_copy.py)
        self._tabs_listed: tuple[str, ...] = ()       # B1: the target ids of this run's newest list_tabs
        self._mark = ""                               # W2 / Full auto: why this act runs with no card
        self._run_tabs = RunTabs(desk, held=self._held)   # D5: the tabs this run opens close at its end
        self._marks = PageMarks.empty()               # fast pages: the newest look's numbers (memory only)
        self._glanced: CuOutcome | None = None        # the glance this act's result ended with (its block, if any)
        self._signals = signals                       # lessons (L1): what went wrong, by kind, host and class only
        self._parked_acts: tuple[ActResolution, ...] = ()
        self.state = loop.LoopState(run_id=run.run_id)

    # -- the run's side ----------------------------------------------------------------------------------

    def newest_image(self) -> bytes | None:
        return self._image

    def new_step(self) -> None:
        self.state = loop.new_step(self.state)

    def lines(self, call: ToolCallRequested, r: ActResolution | None) -> str:
        if r is not None and r.space == "screen":
            return screen_line(call.name, call.arguments)
        line = act_line(call.name, r, call.arguments)
        return f"{line} {self._mark}" if self._mark else line

    async def close(self) -> None:
        """The run ended (or failed): close the tabs it opened, disarm the guards, then free the computer.
        Never raises."""
        await self._run_tabs.cleanup()
        if self._armed:
            self._armed = False
            try:
                await self._desk.disarm_guards()
            except Exception:
                logger.warning("Could not disarm the browser guards of bot %s", self._run.bot_id, exc_info=True)
        self._leases.release(self._run.bot_id, self._run.run_id)

    async def _take(self) -> str | None:
        """The lease, or the sentence why not."""
        if not self._leases.acquire(self._run.bot_id, self._run.run_id):
            return loop.BUSY_TEXT
        return None

    async def _arm(self) -> str | None:
        """Brave is in front: the armed guards, or the sentence why not."""
        if self._desk.page() is None:
            return NO_SCREEN_TEXT
        if self._armed:
            return None
        try:
            chat = await chat_fence(self._run.config, self._run.user_id, self._run.thread_id)
            self._fence = widened(chat, self._own_sites)
            await self._desk.arm_guards(self._fence)
        except (DeskAsleep, DeskUnavailable):
            return NO_SCREEN_TEXT
        except Exception:
            logger.warning("Could not arm the browser guards of bot %s", self._run.bot_id, exc_info=True)
            return GUARDS_TEXT
        self._armed = True
        await self._run_tabs.snapshot()
        return None

    @property
    def own_sites(self) -> frozenset[str]:
        """The sites that joined this run's fence beyond the chat's own (carried to the run after a card)."""
        return self._own_sites

    async def allow_site(self, site: str) -> None:
        """W6/W7: a site this site-fresh run opened itself joins its fence; armed guards take the wider fence at once."""
        self._own_sites = self._own_sites | {site}
        if self._armed and self._fence is not None:
            self._fence = widened(self._fence, (site,))
            await self._desk.arm_guards(self._fence)

    async def _widen_for(self, r: ActResolution) -> None:
        """Owner, 2026-11-03: the gate let an act in your own chat go to another site (only there does a ``do`` leave
        the fence), so the browser guards take that site before the act, or the browser would refuse it."""
        if r.nav_host and self._fence is not None and not self._fence.allows(r.nav_host):
            await self.allow_site(r.nav_host)

    def _epoch(self) -> int:
        return self._control.epoch(self._run.bot_id) if self._control is not None else 0

    def _held(self) -> bool:
        return self._control is not None and self._control.held(self._run.bot_id) is not None

    def _require_hands(self) -> None:
        """You took the computer (or took it and gave it back) since this call began: nothing more is sent."""
        if self._held() or self._epoch() != self._act_epoch:
            raise InputRefusedByComputer("held")

    async def handle(self, call: ToolCallRequested, ctx: GateContext) -> CuOutcome:
        """One screen call. An act the loop refuses before the gate judged it still writes one ``never`` row."""
        self._audited, self._resolved, self._input_sent = False, None, False
        self._tool, self._front_brave = call.name, True
        try:
            outcome = await self._handle(call, ctx)
        finally:
            self._tool = None
        if outcome.looked:
            self._note_seen(outcome.text)
        await self._audit_refusal(call, ctx.tainted, outcome.text)
        return outcome

    async def _say(self, line: str) -> None:
        """The chat's activity line, then (in a live run's call) the computer card's ``computer_step``."""
        await self._chat_line(line)
        if self._tool is not None:
            await self.publish_step(self._tool, line, await self._step_host())

    async def _step_host(self) -> str | None:
        if self._tool == "open_app" or not self._front_brave or self._desk.page() is None:
            return None
        try:
            return steps.step_host(await self._desk.page().url())
        except (DeskAsleep, DeskUnavailable, CdpClientError):
            return None

    async def publish_step(self, tool: str, line: str, host: str | None) -> None:
        self._step_no += 1
        await self._events.publish(self._run.user_id, steps.step_frame(
            bot_id=self._run.bot_id, thread_id=self._run.thread_id, run_id=self._run.run_id, step=self._step_no,
            tool=tool, line=line, host=host))

    async def _audit_refusal(self, call: ToolCallRequested, tainted: bool, text: str) -> None:
        if call.name in CU_ACT_TOOLS and not self._audited:
            await self._gate.record_refused(self._run.user_id, self._run.bot_id, call.name, dict(call.arguments),
                                            tainted=tainted, act=self._resolved, refused=refusal_key(text))
            self._audited = True

    async def _handle(self, call: ToolCallRequested, ctx: GateContext) -> CuOutcome:
        refusal = await self._take()
        if refusal is not None:
            return CuOutcome(refusal)
        why = loop.precheck(self.state, call.name, self._epoch(), call.arguments)
        if why == loop.BUDGET_TEXT:
            return await self._stuck(BUDGET_NOTE.format(host=await self._host() or "this site"), why)
        if why is not None:
            return CuOutcome(why)
        self._act_epoch = self._epoch()
        try:
            return await self._dispatch_awake(call, ctx)
        except DeskAsleep:
            return CuOutcome(ASLEEP_TEXT)
        except DeskUnavailable:
            return CuOutcome(NO_SCREEN_TEXT)
        except InputRefusedByComputer as exc:
            return CuOutcome(_INPUT_WORDS.get(exc.word, NO_SCREEN_TEXT))
        except ScreenGrabError:
            logger.warning("The screen grab of bot %s failed", self._run.bot_id)
            return CuOutcome(NO_SCREEN_TEXT)
        except CdpClientError as exc:
            logger.warning("The browser of bot %s did not answer: %s", self._run.bot_id, type(exc).__name__)
            return CuOutcome(self._silent_text(call.name))

    def _silent_text(self, tool: str) -> str:
        """A browser that stopped answering: nothing was touched, or (an input already went out) it was sent."""
        if self._input_sent:
            return SENT_THEN_SILENT_TEXT.format(what=SENT_WHAT.get(tool, "input"))
        return BROWSER_SILENT_TEXT

    async def _dispatch_awake(self, call: ToolCallRequested, ctx: GateContext) -> CuOutcome:
        """A bot wakes its own computer: asleep, it is started once (as Open it on the Profile does) and the call
        runs again. Still asleep after that (no room, a failed start) is the usual sentence."""
        try:
            return await self._dispatch(call, ctx)
        except DeskAsleep:
            await self._chat_line(WAKING_LINE)
            try:
                await self._desk.start_browser()
            except DeskBusy:
                return CuOutcome(COMPUTERS_BUSY_TEXT)
            if call.name in CU_ACT_TOOLS:
                return CuOutcome(WOKE_LOOK_FIRST_TEXT)     # a woken screen is new: an act needs a fresh look
            return await self._dispatch(call, ctx)

    async def _dispatch(self, call: ToolCallRequested, ctx: GateContext) -> CuOutcome:
        try:
            args = TOOL_INPUTS[call.name].model_validate(call.arguments) if call.name not in NO_ARGS else None
        except ValidationError as exc:
            return CuOutcome(BAD_ARGS_TEXT.format(error=_first_error(exc)))
        if isinstance(args, OpenAppIn):
            return await self._open_app(args)
        if call.name in tabs.TAB_TOOLS:
            return await self._tab(call, args)
        if isinstance(args, ScreenshotIn):
            return await send_screen(self._run, self._desk.page(), self._events, args, ctx, self._arm)
        front = await self._desk.front_window()        # asked before every look and act; never the model's say
        self._front_brave = front.kind == "brave"
        if front.kind != "brave":
            return await self._on_desktop(call, args, ctx, front)
        refusal = await self._arm()
        if refusal is not None:
            return CuOutcome(refusal)
        if isinstance(args, LookIn):
            return await self._look(args.picture)
        if isinstance(args, ReadTextIn):
            return await self._read_text(args)
        if isinstance(args, ReadPdfIn):
            return await self._read_pdf(args)
        if isinstance(args, SavedLoginIn):
            return await self._saved_login(args)
        if isinstance(args, VaultLoginIn):
            return await self._vault_login(args, ctx)
        if call.name == "wait_ready":
            await self._announce(act_line("wait_ready", None, call.arguments))
            word = await self._ready(args.timeout_s)
            self.state = loop.after_wait(self.state)
            return CuOutcome(f"Page: {word}.")
        if call.name == "scroll":
            return await self._scroll(args, call)
        return await self._act(call, args, ctx)

    async def _tab(self, call: ToolCallRequested, args: BaseModel | None) -> CuOutcome:
        """B1: list, switch or close a tab (free, D1). A switch or close moves the screen: look before acting."""
        if call.name != "list_tabs":
            self._require_hands()
        if call.name == "list_tabs":
            done = await tabs.list_tabs(self._desk)
        elif call.name == "switch_tab":
            done = await tabs.switch_tab(self._desk, self._tabs_listed, args)  # type: ignore[arg-type]
        else:
            done = await tabs.close_tab(self._desk, self._tabs_listed, args)   # type: ignore[arg-type]
        self._tabs_listed = done.listed
        self.state = loop.after_open(self.state) if done.moved else loop.after_wait(self.state)
        await self._announce(act_line(call.name, None, call.arguments))
        return CuOutcome(done.text, looked=done.looked)

    # -- look, scroll --------------------------------------------------------------------------------------

    async def _look(self, picture: bool = True) -> CuOutcome:
        await self._announce(act_line("look", None, {}))
        result = await look(self._desk.page(), _NoTyped(self.state.expect), notes=self._guard_notes(),
                            picture=picture)
        self.state = loop.after_look(self.state, self._epoch())
        self._image, self._marks = result.image, result.marks
        text = f"{result.text}\n{SCREENSHOT_SHOWN}" if result.image is not None else result.text
        if plain := plain_address(result.url):         # Roost's own line, outside the page's wrapper
            text = f"{text}\n{PLAIN_ADDRESS_NOTE.format(url=plain)}"
        if form := apply_address(result.url):
            text = f"{text}\n{APPLY_FORM_NOTE.format(url=form)}"
        return CuOutcome(text, block=result.block, url=result.url, looked=True)

    def _guard_notes(self) -> tuple[str, ...]:
        guards = self._desk.guards() if hasattr(self._desk, "guards") else None
        if guards is None:
            return ()
        notes = [POPUP_NOTE.format(url=url) for url in guards.closed_targets()]
        kept = guards.kept_targets() if hasattr(guards, "kept_targets") else ()
        notes += [KEPT_TAB_NOTE.format(host=host_of_url(url)) for url in kept]
        if guards.blocked_last():
            notes.insert(0, BLOCKED_NOTE.format(host=guards.blocked_last()))
        if guards.chooser_opened():
            notes.append(CHOOSER_NOTE)
        return tuple(notes)

    def _scroll_point(self, args: ScrollIn, geo) -> tuple[tuple[int, int] | None, str]:
        """Where to scroll: a point, the middle of an area from the newest look, or the page's middle."""
        if args.area is None:
            return ((args.at["x"], args.at["y"]) if args.at else (geo.inner_w // 2, geo.inner_h // 2)), ""
        area = self._marks.area(args.area)
        if area is None:
            return None, NO_AREA_TEXT.format(index=args.area)
        if area.box is None:
            return None, AREA_OFF_SCREEN_TEXT.format(index=args.area)
        return area.box.center(), ""

    async def _scroll(self, args: ScrollIn, call: ToolCallRequested) -> CuOutcome:
        if self.state.blind_scrolls >= CU_BLIND_SCROLLS_MAX:
            return CuOutcome(BLIND_SCROLL_TEXT)
        page = self._desk.page()
        geo = await page.geometry()
        point, why = self._scroll_point(args, geo)
        if point is None:
            return CuOutcome(why)
        try:
            x, y = viewport_to_screen(point, geo)
        except ValueError:
            return CuOutcome(_INPUT_WORDS["outside"])
        for notches in scroll_pieces(args.amount if args.direction == "down" else -args.amount):
            await self._send(ScreenInput("scroll", x, y, notches=notches, window=geo.window_rect), x, y, "scroll")
        self.state = loop.after_scroll(self.state)
        await self._announce(act_line("scroll", None, call.arguments))
        return CuOutcome(SCROLLED_TEXT.format(direction=args.direction))

    # -- acts ------------------------------------------------------------------------------------------------

    async def _ready(self, timeout_s: float = CU_READY_TIMEOUT_S) -> str:
        """Wait for the page, with the bot's tab brought to the front first: Chromium never answers a screenshot
        of a tab behind another one (B2: the approved re-run has no look before it to do this)."""
        page = self._desk.page()
        await page.geometry()
        return await wait_ready(page, timeout_s, clock=self._clock, sleep=self._sleep)

    async def resolve(self, name: str, args: BaseModel, *, aimed: PageTarget | None = None,
                      pinned: PageTarget | None = None) -> ActResolution:
        """``aimed``: the live control a look's number named; ``pinned``: a card's stored control, read again."""
        if pinned is not None and (getattr(args, "index", None) is not None or getattr(args, "target", None)):
            aimed = await aim.pinned(self._desk.page(), pinned,       # a card's control, its counts aside for a Send
                                     counts_free=commit_class(pinned) in COUNT_FREE_CLASSES)
        r = await self._resolve_page(name, args, aimed)
        quote = await your_quote(self._run.config, self._run.user_id, self._run.thread_id or "",
                                 getattr(args, "owner_words", None))
        r = replace(r, owner_words=quote) if quote else r        # W2: only a quote that is really yours
        if await approved_before(self._run.config, self._run.user_id, self._run.thread_id or "", r):
            r = replace(r, approved_again=True)                      # W10: you said Yes to this control just now
        if r.tool != "type" and r.commit in OWNER_WORDS_CLASSES:     # the Send card: is the text on the page yours?
            r = replace(r, own_text=any(not box.yours for box in await self._drafts(r)))
        return r

    async def _resolve_page(self, name: str, args: BaseModel, aimed: PageTarget | None) -> ActResolution:
        page = self._desk.page()
        url = await page.url()
        if name == "click":
            return await resolve_click(page, args, url, aimed)
        if name == "type":
            refs = tuple(source for source in (args.source,) if source is not None)
            texts = await load_approved_texts(self._run.config, self._run.user_id, self._run.thread_id or "", refs,
                                              bot_id=self._run.bot_id)
            r = await resolve_type(page, args, url, texts, aimed)
            return self._with_field_flags(r, args.text, texts.contacts)
        return await resolve_key(page, args, url, aimed)

    def _with_field_flags(self, r: ActResolution, text: str, contacts: frozenset[str]) -> ActResolution:
        """Contact and secret are judged on everything typed into this field in the run, joined both ways."""
        prior = self._field_text.get(loop.target_key(r), "") if r.target is not None else ""
        if not prior:
            return r
        joined = text_flags(prior + text, contacts) | text_flags(f"{prior} {text}", contacts)
        return replace(r, text_flags=r.text_flags | joined)

    async def _aimed(self, args: BaseModel) -> tuple[PageTarget | None, str]:
        """The live control an index names, or the sentence why not (then the next act looks first)."""
        index = getattr(args, "index", None)
        if index is None:
            return None, ""
        found, why = await aim.indexed(self._desk.page(), self._marks, index, await self._desk.page().url())
        if why:
            self.state = loop.forget_look(self.state)
        return found, why

    async def _act(self, call: ToolCallRequested, args: BaseModel, ctx: GateContext) -> CuOutcome:
        await self._ready()
        self._require_hands()                      # you may have taken the computer while the page settled
        aimed, why = await self._aimed(args)
        if why:
            return CuOutcome(why)
        r = await self.resolve(call.name, args, aimed=aimed)
        self._resolved = r
        if self._stale_click(call, r):
            return CuOutcome(loop.LOOK_FIRST_TEXT)
        missed = await self._missed(call, r)
        if missed is not None:
            return await self._miss(call, r, *missed)
        if call.name == "type" and not self._typing_where_clicked(r):
            return CuOutcome(loop.LOOK_FIRST_TEXT)
        verdict = await self._gate.decide(self._run.user_id, self._run.bot_id, call.name, dict(call.arguments),
                                          replace(ctx, fence=self._fence), act=r, review=self._review_page)
        self._audited = True
        self._mark = STEP_MARKS.get(verdict.reason, "")
        if verdict.decision == "ask":
            return await self._park(call, r, ctx.tainted)
        if verdict.decision != "do":
            return CuOutcome(verdict.text or NO_SCREEN_TEXT)
        await self._widen_for(r)
        self._glanced = None
        text = await self.act(r, call)
        seen = self._glanced
        return CuOutcome(text, url=await self._desk.page().url(), looked=seen is not None,
                         block=seen.block if seen is not None else None)

    async def _review_page(self) -> ReviewPage:
        """Full auto: your newest own messages in this chat (oldest first) and the page's title, read only when a
        review runs."""
        mine = await your_messages(self._run.config, self._run.user_id, self._run.thread_id or "",
                                   limit=AUTO_REVIEW_REQUEST_MESSAGES)
        return ReviewPage(request="\n".join(mine), title=await self._desk.page().title())

    def _typing_where_clicked(self, r: ActResolution) -> bool:
        """``type`` without a fresh look must go into the very box the last click focused."""
        if self.state.looked_at_version == self.state.screen_version:
            return True
        return r.target is not None and loop.target_key(replace(r, tool="click")) == self.state.focused_by_click

    def _stale_click(self, call: ToolCallRequested, r: ActResolution) -> bool:
        """``precheck`` let a click through on a stale look only for the covering dialog's own close buttons: any
        other control it resolved to looks first (the page may have changed under the bot)."""
        stale = self.state.looked_at_version != self.state.screen_version
        return stale and call.name == "click" and not loop.closes_cover(self.state, r)

    async def _missed(self, call: ToolCallRequested, r: ActResolution) -> tuple[str, frozenset[int]] | None:
        """The miss's sentence and, for a covered control, the covering dialog's close buttons it names."""
        if r.refusal:
            return None
        if r.target is None and call.name in ("click", "type"):
            if call.name == "click" and r.point is not None and _by_point(call):
                return point_miss_text(r.point, self._marks), frozenset()
            return MISS_TEXT.format(aim=_aim_words(call)), frozenset()
        if r.covered_by:
            closers = await closers_of(self._desk.page(), r.covered_by)
            text = covered_text(f"'{label_of(r)}'", r.covered_by, closers, self._marks)
            return text, frozenset(t.node_id for t in closers)
        return None

    async def _miss(self, call: ToolCallRequested, r: ActResolution, text: str,
                    closers: frozenset[int] = frozenset()) -> CuOutcome:
        self.state, last = loop.after_miss(self.state, loop.aim_key(call.name, call.arguments), closers=closers)
        if not last:
            return CuOutcome(text)
        aim = f"'{label_of(r)}'" if r.target is not None else _aim_words(call)
        return await self._stuck(MISS_NOTE.format(aim=aim, host=r.host or "this page"), text)

    async def _stuck(self, note: str, text: str) -> CuOutcome:
        url = _card_url(await self._desk.page().url()) if self._desk.page() is not None else ""
        block = Block(reason="asked", url=url, host=host_of_url(url), note=note)
        return CuOutcome(text, block=block, url=url)

    async def _host(self) -> str:
        page = self._desk.page()
        try:
            return host_of_url(await page.url()) if page is not None else ""
        except (DeskAsleep, DeskUnavailable):
            return ""            # Brave may be closed on the full computer

    async def _park(self, call: ToolCallRequested, r: ActResolution, tainted: bool) -> CuOutcome:
        typed = typed_chars_of(call.name, call.arguments)
        drafts = await self._drafts(r)
        step = PendingCall(
            tool=call.name, arguments=dict(call.arguments), topic="browsing", title=card_title(call.name, r, call.arguments),
            floor=floor_of(r, self._fence, typed_chars=typed),
            tainted_basis=self._text_basis(r, str(call.arguments.get("text", "")), drafts, tainted),
            crop=base64.b64encode(r.crop).decode("ascii") if r.crop else None, act=resolution_to_json(r),
            drafts=drafts,
        )
        shown = with_rows(step)
        if shown is None:
            return CuOutcome(NO_SCREEN_TEXT)
        try:
            steps_json((shown,))
        except CardTooBig:
            shown = replace(shown, crop=None)            # the card still asks, with its words and no picture
            try:
                steps_json((shown,))
            except CardTooBig:
                return CuOutcome(CARD_TOO_BIG_TEXT)
        await self._watch_park(r)
        return CuOutcome("", parked=shown)

    async def act(self, r: ActResolution, call: ToolCallRequested, *, with_glance: bool = True) -> str:
        """Do one resolved act: aim, check the node under the pointer again, then click / type / press."""
        page = self._desk.page()
        geo = await page.geometry()
        note = ""
        before = await self._mark_before(call.name, call.arguments)
        if call.name == "click":
            try:
                x, y = viewport_to_screen(r.point or (0, 0), geo)
            except ValueError:
                return _INPUT_WORDS["outside"]
            await self._input(ScreenInput("move", x, y, window=geo.window_rect))
            if not _same_node(await page.node_at(*(r.point or (0, 0))), r.target):
                return MOVED_TEXT
            await self._send(ScreenInput("click", x, y, window=geo.window_rect), x, y, "click")
        else:
            x, y = self._pointer_at(r, geo)
            if call.arguments.get("index") is not None and not await self._focus_box(page, r, geo):
                return MOVED_TEXT
            if not self._same_focus(await page.focused(), r, call):
                return FOCUS_MOVED_TEXT
            if call.name == "type":
                text = str(call.arguments.get("text", ""))
                note = await self._type_checked(page, r, text, geo.window_rect, x, y)
                if note in NOTHING_TYPED:
                    return note                  # nothing went in: no step, no glance
                self._note_typed(r, text)
            else:
                key = CU_KEYS[str(call.arguments.get("key"))]
                await self._send(ScreenInput("key", key=key, window=geo.window_rect), x, y, "key")
        digest = loop.typed_digest(str(call.arguments.get("text", ""))) if call.name == "type" else None
        if call.name == "type" and r.target is not None:
            key = loop.target_key(r)
            typed = self._field_text.get(key, "") + str(call.arguments.get("text", ""))
            self._field_text = MappingProxyType({**self._field_text, key: typed})
        self.state = loop.after_act(self.state, r, str(call.arguments.get("expect", "")), typed_digest=digest)
        await self._announce(self.lines(call, r))
        result = await self._result(r, call, with_glance=with_glance)
        await self._watch_act(r, call.name, before, note)
        return f"{note}\n{result}" if note else result

    async def _focus_box(self, page, r: ActResolution, geo) -> bool:
        """Fast pages: typing or a key aimed by a look's number clicks its text box first (a text box click is
        browsing), with the node under the pointer checked again. False when something else is there now."""
        if _same_node(await page.focused(), r.target):
            return True
        x, y = self._pointer_at(r, geo)
        await self._input(ScreenInput("move", x, y, window=geo.window_rect))
        if not _same_node(await page.node_at(*(r.point or (0, 0))), r.target):
            return False
        await self._send(ScreenInput("click", x, y, window=geo.window_rect), x, y, "click")
        self.state = loop.forget_look(self.state)      # the screen may have moved: if typing stops here, look first
        return True

    @staticmethod
    def _same_focus(now, r: ActResolution, call: ToolCallRequested) -> bool:
        """The control that has focus right before the send is the one the verdict judged (and, for a key, still
        of the same class)."""
        if r.target is None:
            return now is None
        if not _same_node(now, r.target):
            return False
        return call.name != "press_key" or commit_class(now, key=str(call.arguments.get("key"))) == r.commit

    def _pointer_at(self, r: ActResolution, geo) -> tuple[int, int]:
        point = r.point or (geo.inner_w // 2, geo.inner_h // 2)
        try:
            return viewport_to_screen(point, geo)
        except ValueError:
            return viewport_to_screen((geo.inner_w // 2, geo.inner_h // 2), geo)

    async def _input(self, action: ScreenInput) -> None:
        """Every input checks your hands first, and tells the keeper whether you hold the computer (its 409). A
        click, typing or key counts as sent unless the keeper refused it: one that failed on the way may have run."""
        if self._epoch() != self._act_epoch:
            raise InputRefusedByComputer("held")
        try:
            await self._desk.send_input(action, held=self._held())
        except InputRefusedByComputer:
            raise
        except BaseException:
            self._input_sent = self._input_sent or action.verb != "move"
            raise
        self._input_sent = self._input_sent or action.verb != "move"

    async def _send(self, action: ScreenInput, x: int, y: int, kind: str) -> None:
        await self._input(action)
        await self._events.publish(self._run.user_id, {
            "type": "computer_pointer", "bot_id": self._run.bot_id, "x": x, "y": y, "kind": kind,
        })

    async def _result(self, r: ActResolution, call: ToolCallRequested, *, with_glance: bool = True) -> str:
        await self._run_tabs.trim()
        word = await self._ready()
        address = await self._desk.page().url()
        parts = [f"{self.lines(call, r)}. Page: {word}. Address: {address or 'unknown'}.", *self._guard_notes()]
        if act_commits(r) or floor_of(r, self._fence) is not None:
            parts.append(CHECK_TEXT)
        if not with_glance:                  # a card's re-run: its line goes under the card, never page text
            return " ".join([*parts, "Look to check what you expected."])
        seen = await glance(self._desk.page(), _NoTyped(self.state.expect))
        self.state = loop.after_glance(self.state)
        self._image, self._marks = None, seen.marks       # the last picture is stale now; the numbers are new
        self._glanced = CuOutcome(seen.text, block=seen.block, url=seen.url, looked=True)
        return " ".join(parts) + f"\n{GLANCE_TEXT}\n{seen.text}"
