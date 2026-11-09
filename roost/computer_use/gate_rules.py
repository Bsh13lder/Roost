"""The gate for clicks and keystrokes on the bot's own computer (C3, design §6.2; amendment 2026-10-21).

``judge_act`` is pure and judges only the ``ActResolution`` the runner read from the live page, never the
model's arguments (its one use of them is the typed text's length, for the search-box exemption). Order:

1. never: not this run's tool, nothing resolvable, a refusal from the page side, a password box, Mac Brave;
2. the site fence: a link or a form sent off the fence asks (``new_site``), except in your own chat (owner,
   2026-11-03), where the act is judged on with the fence widened to that site and its ``do`` says so
   (``owner_site``: the runner widens the browser guards before it acts);
3. the hard floor: committing clicks, unapproved text, contact details and secrets ask in every mode and
   every taint, with no session OK, except an act a routine run's standing permission covers
   (``roost/standing/matching.py``: ``standing_ok``, which the gate re-checks live and the model check may turn
   back into this ask), and an act your own message asked for (W2, ``owner_words``: a send, submit, accept or
   delete, or typing, quoting your words; the gate has the bot's own model confirm it, or it is this ask), and in Full auto a
   click or key on a button Roost can't read (``auto_review``, ``roost/auto_review/rules.py``: commit class exactly
   ``unknown``, your own chat only; the gate has a reviewer (the bot's own model) confirm it, or it is this ask).
   Owner, 2026-11-05: in your own chat only paying asks (``owner_chat_act``): a send, submit, accept, delete or
   account click runs, as does typing a secret that is your own words; a made-up contact detail, a spend or an
   unreadable button keeps the reviewer or its card;
4. taint: a tainted run never gets ``do`` on a committing act (the floor already asks, so this is defensive);
5. the Browsing actions topic asks for ordinary clicks when it is on; otherwise they just happen, in every mode
   (Plan included: clicks depend on the screen, so they are never planned);
6. with no cards in this run (handoffs, rooms, routines), every ask is never "needs your OK".

Full computer, Step 1 (D1): before all of that, a screen act (the runner saw another window than Brave in front,
``ActResolution.space == "screen"``) and ``open_app`` are ``do``: inside its own sealed computer a bot is free.
Inside Brave (D2) nothing changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from roost.approvals import floor as _floor
from roost.approvals.models import FloorKind
from roost.approvals.texts import NEEDS_YOUR_OK_TEXT
from roost.auto_review.rules import class_of, may_auto_review
from roost.computer_use.commit_words import commit_class, is_text_box
from roost.computer_use.fence import SiteFence
from roost.computer_use.models import ActResolution
from roost.constants import CU_ACT_TOOLS, CU_FREE_ACT_TOOLS
from roost.owner_words.constants import OWNER_AGAIN_CLASSES
from roost.owner_words.quote import words_may_cover
from roost.standing.matching import match_act
from roost.talk.owner_chat import OWNER_CHAT_ACT_REASON, OWNER_CHAT_STILL_ASKS, owner_chat_run
from roost.talk.verdict import GateContext, Verdict

BROWSING_TOPIC = "browsing"


@dataclass(frozen=True)
class ActTexts:
    """The plain sentences a refused act tells the bot."""

    not_found: str = "I couldn't find that on the page, so I didn't touch it. I'll look again."
    mac_brave: str = (
        "I can click and type only on my own Linux computer, and I'm using Mac Brave. "
        "Switch my computer to Linux on my Profile first."
    )
    password: str = "I don't type into password boxes. I'll ask you to take over."
    card: str = ("That's a card box: I never type card details. Fill in everything else and click Pay; "
                 "the owner types the card on the Pay card.")
    not_a_box: str = "That isn't a text box, so I didn't type there (letters can be a site's shortcuts)."
    not_allowed: str = "Refused: that action is not available yet."
    tainted_commit: str = (
        "I read outside content in this request, so I won't buy, send or submit anything because of it. "
        "Ask me in a new message."
    )


ACT_TEXTS = ActTexts()


def floor_of(r: ActResolution, fence: SiteFence | None = None, *, typed_chars: int | None = None) -> FloorKind | None:
    """The floor kind of an act (see ``roost.approvals.floor.floor_of``)."""
    return _floor.floor_of(r, fence, typed_chars=typed_chars)


def typed_chars_of(name: str, arguments: Mapping[str, Any]) -> int | None:
    """The length of the text a ``type`` call would type; None for anything else or a non-string."""
    text = arguments.get("text") if name == "type" else None
    return len(text) if isinstance(text, str) else None


def _refusal(name: str, r: ActResolution | None, ctx: GateContext, fence: SiteFence | None) -> Verdict | None:
    if name not in CU_ACT_TOOLS or name not in ctx.allowed:
        return Verdict("never", "not_allowed", ACT_TEXTS.not_allowed)
    if fence is None:
        return Verdict("never", "act_refused", ACT_TEXTS.mac_brave)
    if r is None or r.tool != name:
        return Verdict("never", "act_refused", ACT_TEXTS.not_found)
    if r.refusal:
        return Verdict("never", "act_refused", r.refusal)
    if r.tool == "type":
        return _typing_refusal(r)
    return None


def _typing_refusal(r: ActResolution) -> Verdict | None:
    if r.target is None:
        return Verdict("never", "act_refused", ACT_TEXTS.not_found)
    if r.target.card_field:
        return Verdict("never", "act_refused", ACT_TEXTS.card)
    if r.target.secret_field:
        return Verdict("never", "act_refused", ACT_TEXTS.password)
    if not is_text_box(r.target):
        return Verdict("never", "act_refused", ACT_TEXTS.not_a_box)
    return None


def _ask(ctx: GateContext, verdict: Verdict) -> Verdict:
    """Only a run in your own chat may park on a card; any other ask is a never."""
    if ctx.approval is None or not ctx.approval.cards:
        return Verdict("never", "needs_your_ok", NEEDS_YOUR_OK_TEXT)
    return verdict


def _free(name: str, r: ActResolution | None, ctx: GateContext) -> Verdict | None:
    """D1: ``open_app`` and a screen act just happen (when this run has the tool); None for a page act."""
    if name in CU_FREE_ACT_TOOLS:
        return Verdict("do", "allowed") if name in ctx.allowed else Verdict("never", "not_allowed", ACT_TEXTS.not_allowed)
    if r is None or r.space != "screen":
        return None
    if name not in CU_ACT_TOOLS or name not in ctx.allowed:
        return Verdict("never", "not_allowed", ACT_TEXTS.not_allowed)
    if r.tool != name:
        return Verdict("never", "act_refused", ACT_TEXTS.not_found)
    return Verdict("do", "allowed")


def _your_words(ctx: GateContext, r: ActResolution, kind: FloorKind) -> bool:
    """W2: only a run in your own chat (it may show cards, and is no routine run) may take your words for a card."""
    state = ctx.approval
    return state is not None and state.cards and state.standing is None and words_may_cover(r, kind)


def _yes_again(ctx: GateContext, r: ActResolution, kind: FloorKind) -> bool:
    """W10: your Yes on a card covers the same submit or accept control again, only in your own chat."""
    state = ctx.approval
    return (r.approved_again and kind == "commit_click" and state is not None and state.cards
            and state.standing is None and commit_class(r.target) in OWNER_AGAIN_CLASSES)


def _owner_chat_act(ctx: GateContext, r: ActResolution, kind: FloorKind) -> bool:
    """Owner, 2026-11-05: in your own chat only paying asks. A committing click runs unless it spends or can't be
    read; a secret runs when it is your own words (an ID number you gave). A contact detail you never gave (one the
    bot made up) still asks; the ones you gave never asked."""
    if not owner_chat_run(ctx):
        return False
    if kind == "commit_click":
        return class_of(r) not in OWNER_CHAT_STILL_ASKS
    return kind == "secret" and r.text_ok is True


def judge_act(name: str, r: ActResolution | None, ctx: GateContext, fence: SiteFence | None,
              *, typed_chars: int | None = None) -> Verdict:
    """The verdict for one click, type or key press, in the order above."""
    free = _free(name, r, ctx)
    if free is not None:
        return free
    refused = _refusal(name, r, ctx, fence)
    if refused is not None or r is None:
        return refused or Verdict("never", "act_refused", ACT_TEXTS.not_found)
    kind = floor_of(r, fence, typed_chars=typed_chars)
    widened = kind == "new_site" and owner_chat_run(ctx) and fence is not None
    if widened:
        kind = floor_of(r, fence.with_host(r.nav_host), typed_chars=typed_chars)   # your chat: that site joins
    if kind == "new_site":
        return _ask(ctx, Verdict("ask", "new_site"))
    if kind is not None:
        covered = match_act(ctx.approval.standing if ctx.approval else None, r, kind)   # a routine's standing permission
        if covered is not None:
            return Verdict("do", "standing_ok", standing=covered)
        if _owner_chat_act(ctx, r, kind):
            return Verdict("do", OWNER_CHAT_ACT_REASON)
        if _yes_again(ctx, r, kind):
            return Verdict("do", "approved")
        if _your_words(ctx, r, kind):
            return Verdict("do", "owner_words")
        if may_auto_review(ctx, r, kind):
            return Verdict("do", "auto_review")
        return _ask(ctx, Verdict("ask", "hard_floor"))
    if ctx.tainted and _floor.act_commits(r):
        return Verdict("never", "tainted_refused", ACT_TEXTS.tainted_commit)
    if ctx.approval is not None and BROWSING_TOPIC in ctx.approval.ask_topics:
        return _ask(ctx, Verdict("ask", "topic_asks"))
    return Verdict("do", "owner_site" if widened else "allowed")
