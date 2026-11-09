"""``Gate`` — the one choke point every ``ToolCallRequested`` goes through
before ``roost/talk/turn.py`` ever runs it (contract's "Talk tools + gate"
section).

Per-tool gate kinds (M1 D1/D3): a name outside the run's own allowlist, or
outside the catalog, is ``"never"``. D3's tainted-write rule: a tainted run
may create — the row is stored tainted, at most ``MAX_TAINTED_CREATES_PER_RUN``
per run — but never change or delete. D4's link guard: when a run's
``GateContext.link_guard`` is set, its ``open_page`` calls are refused
unless the url is in that ``LinkScope`` — and the verdict carries the
scope's own stored entry, which is what the browser actually opens, never
the model's spelling of it (ruling R3).

Every decision writes one encrypted ``audit`` row (``user_id``, ``bot_id``,
the tool name, the decision, its reason, the run's taint and the call's
arguments as ``audit.detail``, redacted: a write's file text, diff or note body is never kept), so the refusal path stays auditable.

Fails closed like everything else in this gate's family: a name that
isn't recognized gets ``"never"``, never a default "allow".

C3: an ``act`` tool (click, type, press_key) is judged by
``roost/computer_use/gate_rules.py:judge_act`` on the resolution the runner read
from the live page (``decide(..., act=)``), before D3's tainted-write rule: every
computer-use loop is tainted after its first look, and committing acts already
ask at the hard floor whatever the taint.

Standing permissions (docs/plans/2026-10-23-roost-full-computer.md Steps 2-3): in a routine run, ``judge_act`` may
answer ``standing_ok`` for a hard-floor act the routine's permission names; ``decide`` then has the
``StandingGuard`` re-check it live and ask the bot's own model (``roost/standing/check.py``) before the act runs, so it can only
stay ``do`` or become the hard-floor ask. The audit row carries the final reason.

Your words count (docs/plans/2026-10-23-roost-owner-words.md W2): in a run of your own chat, ``judge_act`` may answer
``owner_words`` for a send, submit, accept or delete (or typing) that quotes your own message; ``decide`` has the
``OwnerWordsGuard`` ask the bot's own model whether the words fit the act, so it stays ``do`` or becomes the hard-floor ask.

Full auto (owner, 2026-10-25): in a run of your own chat with the bot's ``auto_review`` on, ``judge_act`` may answer
``auto_review`` for a click or key on a button Roost can't read (commit class exactly ``unknown``); ``decide`` has the
``AutoReviewGuard`` read your newest request and the page title (the runner's ``review`` source) and ask the bot's own
model as the reviewer, so it stays ``do`` only on an exact ``safe`` and is otherwise the hard-floor ask.

Opening sites in your own chat (W6/W7, widened by the owner on 2026-11-03): in a run of your own 1:1 chat that can
show a card, ``open_page`` opens any address ``askable_url`` accepts, with no Open card (reason ``fresh_open``), before
D4's link guard, even after the run read pages; the runner widens the run's link scope and fence to that site. An
unsafe address is never opened. Outside your own chat D4 and the Open card are unchanged.

The create check (owner, 2026-10-29): in a run of your own chat, a tainted ``create_bot`` is judged by the approval
mode as if clean; where that is ``do`` it becomes ``checked_create``, and ``decide`` has the ``CreateCheckGuard`` read
your newest own messages (the runner's ``owner`` source) and ask the bot's own model, so it stays ``do`` only on an exact ``fits``
and is otherwise the old refusal that points to ``suggest_bot``. The created card says it was auto-checked.

Your own chat (owner, 2026-11-03, ``roost/talk/owner_chat.py``): in a run of your own chat that can show a card, a
tainted change to your records, a memory, a routine, a bot's model or the bot's own instructions (``OWNER_CHAT_TOOLS``)
is judged by the approval mode exactly as in a clean run; its ``do`` carries the reason ``owner_chat_change``. No model
check. Routines, handoffs, rooms and helpers keep D3's refusal.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Literal, Mapping

from roost.approvals import topics
from roost.approvals.floor import hard_floor
from roost.approvals.models import ApprovalState
from roost.approvals.texts import NEEDS_YOUR_OK_TEXT, PLAN_FULL_TEXT
from roost.auto_review.guard import AutoReviewGuard, ReviewSource
from roost.create_check.guard import REFUSED as CREATE_REFUSED
from roost.create_check.constants import CREATE_CHECK_MESSAGES
from roost.create_check.guard import CreateCheckGuard, OwnerSource
from roost.llm.types import Model
from roost.computer_use.gate_rules import judge_act, typed_chars_of
from roost.computer_use.models import ActResolution
from roost.config import Config
from roost.constants import APPROVAL_PLAN_MAX_STEPS, FRESH_RUN_OPENS_ANY_SITE, MAX_TAINTED_CREATES_PER_RUN
from roost.crypto.encryption import encrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.mac.redact import redact_for_audit
from roost.owner_words.guard import OwnerWordsGuard
from roost.standing.guard import StandingGuard, floor_ask
from roost.talk.link_scope import LinkScope
from roost.talk.new_site import UNSAFE_ADDRESS_TEXT, askable_url
from roost.talk.owner_chat import OWNER_CHAT_ACT_REASON, OWNER_CHAT_REASON, OWNER_CHAT_TOOLS, owner_chat_run
from roost.talk.tool_catalog import CATALOG
from roost.talk.tool_def import ToolDef
from roost.talk.verdict import Decision, GateContext, Reason, Verdict

__all__ = [
    "Decision", "Gate", "GateContext", "LINK_REFUSAL_TEXT", "REFUSAL_TEXT", "Reason", "TAINTED_CHANGE_TEXT",
    "TAINTED_CREATE_CAP_TEXT", "Verdict", "judge",
]

logger = logging.getLogger(__name__)

REFUSAL_TEXT = "Refused: that action is not available yet."
# D3: outside your own chat (a routine, a handoff, a room, a helper) a run that read outside content changes
# nothing; in your own chat the same change just runs (roost/talk/owner_chat.py), so that is where to ask.
TAINTED_CHANGE_TEXT = (
    "Not changed: this task read outside web content and nobody is here to ask, so I don't change or delete "
    "your data from it. Ask me in our own chat and I'll do it."
)
TAINTED_CREATE_CAP_TEXT = (
    f"I read outside web content in this request, so I add at most {MAX_TAINTED_CREATES_PER_RUN} items in it. "
    "Ask me again in a new message for the rest."
)
LINK_REFUSAL_TEXT = (
    "I didn't open that link: nobody is here to OK a new site, so in this request I open only sites named or "
    "linked in your own messages, or links from a page already read for it."
)

_DETAIL_AAD = "audit:detail"

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _guard_link(arguments: Mapping[str, Any], guard: LinkScope, ctx: GateContext) -> Verdict:
    """D4/R3: allowed with the stored entry when the scope holds the link, which is what the browser opens
    (open_page is ``read``, so D3 has nothing to add). Any other address asks you once with an Open card in a
    run that can show one (owner, 2026-10-23), with the canonical address the card stores; otherwise refused."""
    matched = guard.match(str(arguments.get("url", "")))
    if matched is not None:
        return Verdict("do", "allowed", url=matched)
    offered = askable_url(arguments.get("url"))
    if offered is not None and ctx.approval is not None and ctx.approval.cards:
        return Verdict("ask", "new_site", url=offered)
    return Verdict("never", "link_not_trusted", LINK_REFUSAL_TEXT)


def _owner_opens(ctx: GateContext) -> bool:
    """Owner, 2026-11-03: a run of your own chat that can show a card opens any safe site, fresh or not."""
    return bool(FRESH_RUN_OPENS_ANY_SITE and owner_chat_run(ctx))


def _fresh_open(arguments: Mapping[str, Any]) -> Verdict:
    """Any address a card could offer opens at once, as its canonical form; anything else is never opened."""
    offered = askable_url(arguments.get("url"))
    if offered is None:
        return Verdict("never", "link_not_trusted", UNSAFE_ADDRESS_TEXT)
    return Verdict("do", "fresh_open", url=offered)


def _session_ok(arguments: Mapping[str, Any], ctx: GateContext) -> bool:
    """A Mac read skips its card only in a clean run, inside a folder with a live session OK."""
    folder = arguments.get("folder")
    return (not ctx.tainted and isinstance(folder, str) and ctx.approval is not None
            and folder.casefold() in ctx.approval.session_folders)


def _write_verdict(tool: ToolDef, name: str, arguments: Mapping[str, Any], ctx: GateContext,
                   state: ApprovalState) -> Verdict:
    """What a write does under the run's approval mode (floor, then mode, then topic switch)."""
    if hard_floor(name, arguments, state) is not None:
        return Verdict("ask", "hard_floor")
    if state.mode == "ask":
        return Verdict("ask", "approval_ask")
    if topics.topic_of(name) in state.ask_topics:
        return Verdict("ask", "topic_asks")
    if state.mode == "plan":
        if state.plan_steps >= APPROVAL_PLAN_MAX_STEPS:
            return Verdict("never", "plan_full", PLAN_FULL_TEXT)
        return Verdict("plan", "planned")
    if ctx.tainted and tool.kind == "write_change":
        return Verdict("do", "tainted_mac_edit")   # only a RELAX_TAINTED_TOOLS name gets this far when tainted
    return Verdict("do", "tainted_create" if ctx.tainted else "auto_edit")


def _by_approval(tool: ToolDef, name: str, arguments: Mapping[str, Any], ctx: GateContext,
                 state: ApprovalState) -> Verdict:
    if tool.kind == "read":
        if topics.topic_of(name) == "files" and not _session_ok(arguments, ctx):
            return Verdict("ask", "mac_read_asks")
        return Verdict("do", "allowed")
    return _write_verdict(tool, name, arguments, ctx, state)


def _taint_refusal(tool: ToolDef, name: str, ctx: GateContext) -> Verdict | None:
    """D3's tainted-write rule. Only a RELAX_TAINTED_TOOLS name, in Auto-edit or Plan mode, escapes a change refusal."""
    if not ctx.tainted or tool.allowed_when_tainted:
        return None
    if tool.refused_when_tainted:
        return Verdict("never", "tainted_refused", tool.tainted_refusal or TAINTED_CHANGE_TEXT)
    if tool.kind == "write_change":
        relaxed = (name in topics.RELAX_TAINTED_TOOLS and ctx.approval is not None
                   and ctx.approval.mode in ("auto_edit", "plan"))
        if not relaxed:
            return Verdict("never", "tainted_change", tool.tainted_refusal or TAINTED_CHANGE_TEXT)
    if tool.kind == "write_create" and ctx.creates >= MAX_TAINTED_CREATES_PER_RUN:
        return Verdict("never", "tainted_create_cap", TAINTED_CREATE_CAP_TEXT)
    return None


def _sandbox_verdict(name: str, ctx: GateContext) -> Verdict:
    """Programs: a tool on the bot's own workspace runs in a clean run whatever the mode (the modes govern the
    user's things), and asks in a tainted run, since web content could be steering the code (but in your own chat,
    owner 2026-11-05, they run). The ``programs``
    topic switch makes it ask in a clean run too. Where no card can open, an ask is refused."""
    state = ctx.approval
    yours = ctx.tainted and owner_chat_run(ctx)   # owner, 2026-11-05: your own chat runs them after web content
    if ctx.tainted and not yours:
        verdict = Verdict("ask", "hard_floor")
    elif state is not None and topics.topic_of(name) in state.ask_topics:
        verdict = Verdict("ask", "topic_asks")
    else:
        return Verdict("do", OWNER_CHAT_ACT_REASON if yours else "allowed")
    if state is None or not state.cards:
        return Verdict("never", "needs_your_ok", NEEDS_YOUR_OK_TEXT)
    return verdict


def _always_asks(ctx: GateContext) -> Verdict:
    """A connector write: the hard floor asks in every mode, tainted or not; with no card to show it is never."""
    if ctx.approval is None or not ctx.approval.cards:
        return Verdict("never", "needs_your_ok", NEEDS_YOUR_OK_TEXT)
    return Verdict("ask", "hard_floor")


def _own_settings_verdict(ctx: GateContext) -> Verdict:
    """Voice §4 (set_my_voice): the bot's own settings change with no card in a run of your own 1:1 chat that has
    read no outside content (clean, or site-fresh for your own new message), whatever the mode. Anywhere else (your
    chat after outside content, a routine, a handoff, a room) it is an ordinary Ask card, or never where none opens."""
    if ctx.owner_chat and (not ctx.tainted or ctx.site_fresh or owner_chat_run(ctx)):
        return Verdict("do", "allowed")   # owner, 2026-11-03: your own chat may change them after web content too
    # A routine, handoff or room never changes a bot's settings on its own, not even on a rig with no approval
    # state: with no card to show, the answer is never (needs_your_ok), as for every other hard-floor call.
    return _always_asks(ctx)


def judge(tool: ToolDef | None, name: str, arguments: Mapping[str, Any], ctx: GateContext,
          act: ActResolution | None = None) -> Verdict:
    """The pure decision. Order: unknown / not this run's -> never; an ``act`` tool -> ``judge_act`` on the
    page's resolution (never on the arguments); a site-fresh open (W6/W7); D4's link guard; D3: a tainted run
    never changes (but for the one relaxed Mac edit) and creates at most the cap; then, when the run has an approval state, the mode's
    verdict (ask, plan or do), which only a run in the user's own chat may park."""
    if tool is None or name not in ctx.allowed:
        return Verdict("never", "not_allowed", REFUSAL_TEXT)
    if tool.kind == "act":
        return judge_act(name, act, ctx, ctx.fence, typed_chars=typed_chars_of(name, arguments))
    if name == "open_page" and _owner_opens(ctx):
        return _fresh_open(arguments)
    if ctx.link_guard is not None and name == "open_page":
        return _guard_link(arguments, ctx.link_guard, ctx)
    kind = tool.kind_for(arguments)
    if kind != tool.kind:
        tool = replace(tool, kind=kind)
    if tool.asks_always and kind != "read":
        return _always_asks(ctx)
    if tool.sandbox:
        return _sandbox_verdict(name, ctx)
    if tool.own_settings:
        return _own_settings_verdict(ctx)
    if name == "create_bot" and ctx.tainted and ctx.owner_chat:
        return _checked_create(tool, name, arguments, ctx)
    if ctx.tainted and name in OWNER_CHAT_TOOLS and owner_chat_run(ctx):
        return _owner_chat_change(tool, name, arguments, ctx)
    refused = _taint_refusal(tool, name, ctx)
    if refused is not None:
        return refused
    if ctx.approval is None or tool.no_ask:
        return Verdict("do", "tainted_create" if ctx.tainted and tool.kind == "write_create" else "allowed")
    verdict = _by_approval(tool, name, arguments, ctx, ctx.approval)
    if verdict.decision in ("ask", "plan") and not ctx.approval.cards:
        return Verdict("never", "needs_your_ok", NEEDS_YOUR_OK_TEXT)
    return verdict


def _checked_create(tool: ToolDef, name: str, arguments: Mapping[str, Any], ctx: GateContext) -> Verdict:
    """The create check: the mode's verdict as for a clean run; a ``do`` goes to the model check."""
    if ctx.approval is None:
        return Verdict("do", "checked_create")
    verdict = _write_verdict(tool, name, arguments, ctx, ctx.approval)
    if verdict.decision in ("ask", "plan") and not ctx.approval.cards:
        return Verdict("never", "needs_your_ok", NEEDS_YOUR_OK_TEXT)
    return Verdict("do", "checked_create") if verdict.decision == "do" else verdict


def _owner_chat_change(tool: ToolDef, name: str, arguments: Mapping[str, Any], ctx: GateContext) -> Verdict:
    """Your own chat: the verdict of the same call in a clean run; its ``do`` says so (``owner_chat_change``)."""
    verdict = judge(tool, name, arguments, replace(ctx, tainted=False))
    return Verdict("do", OWNER_CHAT_REASON) if verdict.decision == "do" else verdict


class Gate:
    def __init__(self, config: Config, *, catalog: Mapping[str, ToolDef] = CATALOG,
                 standing: StandingGuard | None = None, owner_words: OwnerWordsGuard | None = None,
                 auto_review: AutoReviewGuard | None = None, create_check: Model | None = None) -> None:
        self._config = config
        self._catalog = MappingProxyType(dict(catalog))
        self._standing = standing    # None: built on the first standing_ok (the worker model, the bot's model id)
        self._owner_words = owner_words   # None: built on the first owner_words verdict (W2)
        self._auto_review = auto_review   # None: built on the first auto_review verdict (Full auto)
        self._create_check = None if create_check is None else CreateCheckGuard(create_check)

    def _review_guard(self) -> AutoReviewGuard:
        if self._auto_review is None:
            from roost.llm.registry import make_worker_model   # here: scripted mode never imports the SDK
            self._auto_review = AutoReviewGuard(make_worker_model(self._config))
        return self._auto_review

    async def _checked_auto_review(self, user_id: str, verdict: Verdict, arguments: Mapping[str, Any],
                                   ctx: GateContext, act: ActResolution | None,
                                   review: ReviewSource | None) -> Verdict:
        """Full auto: a reviewer (the bot's own model) says this unknown button is safe; anything else is the hard-floor ask."""
        try:
            return await self._review_guard().confirm(verdict, arguments, ctx, act, review)
        except Exception as exc:
            logger.warning("The auto-review check failed for user %s: %s", user_id, type(exc).__name__)
            return floor_ask(ctx)

    def owner_source(self, user_id: str, thread_id: str) -> OwnerSource:
        """The create check's source for one chat: your newest own, untainted messages, read only when it runs."""
        async def read() -> tuple[str, ...]:
            from roost.computer_use.text_source import your_messages   # here: the screen loop imports this gate
            return await your_messages(self._config, user_id, thread_id, limit=CREATE_CHECK_MESSAGES)
        return read

    def _create_guard(self) -> CreateCheckGuard:
        if self._create_check is None:
            from roost.llm.registry import make_worker_model   # here: scripted mode never imports the SDK
            self._create_check = CreateCheckGuard(make_worker_model(self._config))
        return self._create_check

    async def _checked_create(self, user_id: str, verdict: Verdict, arguments: Mapping[str, Any],
                              owner: OwnerSource | None, model_id: str | None) -> Verdict:
        """The bot's own model says the bot fits your own words; anything else is the refusal that points to suggest_bot."""
        try:
            return await self._create_guard().confirm(verdict, arguments, owner, model_id=model_id)
        except Exception as exc:
            logger.warning("The create check failed for user %s: %s", user_id, type(exc).__name__)
            return CREATE_REFUSED

    def _owner_guard(self) -> OwnerWordsGuard:
        if self._owner_words is None:
            from roost.llm.registry import make_worker_model   # here: scripted mode never imports the SDK
            self._owner_words = OwnerWordsGuard(make_worker_model(self._config))
        return self._owner_words

    async def _checked_owner_words(self, user_id: str, verdict: Verdict, arguments: Mapping[str, Any],
                                   ctx: GateContext, act: ActResolution | None) -> Verdict:
        """W2: the bot's own model confirms your words ask for this act; anything else is the hard-floor ask."""
        try:
            return await self._owner_guard().confirm(verdict, arguments, ctx, act)
        except Exception as exc:
            logger.warning("The owner words check failed for user %s: %s", user_id, type(exc).__name__)
            return floor_ask(ctx)

    def _standing_guard(self) -> StandingGuard:
        if self._standing is None:
            from roost.llm.registry import make_worker_model   # here: scripted mode never imports the SDK
            from roost.standing.store import PermissionStore
            self._standing = StandingGuard(PermissionStore(self._config), make_worker_model(self._config))
        return self._standing

    async def _checked_standing(self, user_id: str, verdict: Verdict, arguments: Mapping[str, Any],
                                ctx: GateContext, act: ActResolution | None) -> Verdict:
        """Steps 2 and 3: a standing_ok is re-checked live and by the bot's own model; it can only stay or become the ask."""
        try:
            return await self._standing_guard().confirm(user_id, verdict, arguments, ctx, act)
        except Exception as exc:
            logger.warning("The standing check failed for user %s: %s", user_id, type(exc).__name__)
            return floor_ask(ctx)

    async def decide(
        self, user_id: str, bot_id: str, name: str, arguments: dict[str, Any], ctx: GateContext,
        act: ActResolution | None = None, review: ReviewSource | None = None, owner: OwnerSource | None = None,
    ) -> Verdict:
        """Decide one call and write exactly one audit row. An error while
        judging refuses; an error writing the audit row propagates, so the
        call never runs (spec §4.4: no audit row, no execution). ``act``: the
        page's resolution of a click or key (C3); an act tool without one is never.
        ``review``: where an ``auto_review`` verdict reads your request and the page title (Full auto).
        ``owner``: where a ``checked_create`` verdict reads your newest own messages."""
        try:
            verdict = judge(self._catalog.get(name), name, arguments, ctx, act=act)
        except Exception:
            logger.exception("Gate failed to judge %s for bot %s", name, bot_id)
            verdict = Verdict("never", "not_allowed", REFUSAL_TEXT)
        if verdict.reason == "standing_ok":
            verdict = await self._checked_standing(user_id, verdict, arguments, ctx, act)
        elif verdict.reason == "owner_words":
            verdict = await self._checked_owner_words(user_id, verdict, arguments, ctx, act)
        elif verdict.reason == "auto_review":
            verdict = await self._checked_auto_review(user_id, verdict, arguments, ctx, act, review)
        elif verdict.reason == "checked_create":
            verdict = await self._checked_create(user_id, verdict, arguments, owner, ctx.check_model)
        await self._record_audit(user_id, bot_id, name, verdict, arguments, ctx.tainted, act)
        return verdict

    async def record_approved(
        self, user_id: str, bot_id: str, name: str, arguments: dict[str, Any], *,
        reason: Literal["approved", "plan_accepted"], tainted: bool, act: ActResolution | None = None,
    ) -> None:
        """The audit row for a call the user approved (a card's Yes, or an accepted plan): decision ``do``."""
        await self._record_audit(user_id, bot_id, name, Verdict("do", reason), arguments, tainted, act)

    async def record_refused(
        self, user_id: str, bot_id: str, name: str, arguments: dict[str, Any], *, tainted: bool,
        act: ActResolution | None = None, refused: str = "",
    ) -> None:
        """The audit row for an act the screen loop refused before the gate judged it: decision ``never``.
        ``refused`` is the fixed key of the loop's refusal (``roost/computer_use/refusal_keys.py``), kept in the
        row's detail so the logs say why."""
        await self._record_audit(user_id, bot_id, name, Verdict("never", "loop_refused"), arguments, tainted, act,
                                 refused=refused)

    async def check(
        self, user_id: str, bot_id: str, name: str, arguments: dict[str, Any], *, allowed: frozenset[str] | None = None,
    ) -> Decision:
        """Decision-only shortcut for a clean run (tests, simple callers);
        ``allowed`` defaults to the whole catalog, the old global bound."""
        ctx = GateContext(allowed=frozenset(self._catalog) if allowed is None else allowed)
        return (await self.decide(user_id, bot_id, name, arguments, ctx)).decision

    async def _record_audit(
        self, user_id: str, bot_id: str, action: str, verdict: Verdict, arguments: dict[str, Any], tainted: bool,
        act: ActResolution | None = None, *, refused: str = "",
    ) -> None:
        dek = await get_user_dek(self._config, user_id)
        redacted = redact_for_audit(action, arguments, dek, act=act)
        if refused:
            redacted = {**redacted, "refused": refused}
        detail = encrypt(json.dumps(redacted), dek, user_aad(user_id, _DETAIL_AAD))
        async with db_session(self._config) as db:
            await db.execute(
                "INSERT INTO audit (user_id, bot_id, action, decision, detail, created_at, reason, tainted) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (user_id, bot_id, action, verdict.decision, detail, _now_iso(), verdict.reason, int(tainted)),
            )
            await db.commit()
