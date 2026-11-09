"""Which acts a reviewer may judge instead of an Ask card (pure).

Only in Full auto (the bot's ``auto_review`` on and its Browsing actions not set to ask), only in a run that may show
cards and is no routine run, only a click or key on the page whose floor is ``commit_click`` and whose commit class
is ``unknown``, or (owner, 2026-11-05) ``send``, ``submit`` or ``accept``, which the reviewer checks against what you
asked; a send of text the bot wrote itself keeps its Send card. Never a covered control, a refusal, a consent box, a
cross-origin frame, a password or file box, typed text, or anything outside Brave. Paying, deleting, account changes
and every other floor keep their card."""

from __future__ import annotations

from roost.approvals.models import FloorKind
from roost.auto_review.constants import AUTO_REVIEW_ASKED_CLASSES, AUTO_REVIEW_CLASS, AUTO_REVIEW_TOOLS
from roost.computer_use.commit_words import commit_class
from roost.computer_use.models import ActResolution
from roost.talk.verdict import GateContext

BROWSING_TOPIC = "browsing"
FILE_INPUT = "file"


def _full_auto(ctx: GateContext) -> bool:
    state = ctx.approval
    return (state is not None and state.auto_review and state.cards and state.standing is None
            and BROWSING_TOPIC not in state.ask_topics)


def _plain_control(r: ActResolution) -> bool:
    target = r.target
    if target is None or r.covered_by or r.refusal or r.space != "page" or r.text_flags:
        return False
    return not (target.in_consent or target.cross_origin_frame or target.secret_field
                or target.input_type == FILE_INPUT)


def class_of(r: ActResolution) -> str:
    """A click is read again from its own control, as ``act_commits`` does; a key keeps its resolved class."""
    return commit_class(r.target) if r.tool == "click" and r.target is not None else r.commit


def may_auto_review(ctx: GateContext, r: ActResolution, kind: FloorKind) -> bool:
    """True when a reviewer may stand in for the card at floor ``kind`` (the model check still decides)."""
    if kind != "commit_click" or r.tool not in AUTO_REVIEW_TOOLS or not _full_auto(ctx):
        return False
    if not _plain_control(r):
        return False
    commit = class_of(r)
    return commit == AUTO_REVIEW_CLASS or (commit in AUTO_REVIEW_ASKED_CLASSES and not r.own_text)
