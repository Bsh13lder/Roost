"""Approval models: a bot's mode and topic switches (frozen, no mutation)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Mapping, get_args

from pydantic import BaseModel, ConfigDict

from roost.constants import (
    APPROVAL_DIFF_SHOWN_LINES, APPROVAL_ROW_SHOWN_CHARS, APPROVAL_STEPS_MAX_BYTES, LOCKED_TOPICS, NEW_BOT_APPROVAL_MODE,
    NEW_BOT_AUTO_REVIEW,
)
from roost.standing.models import StandingState

ApprovalMode = Literal["ask", "auto_edit", "plan"]
# "browsing" (C3): clicks and keys on the bot's own computer. An ordinary opt-in topic, off by default
# (amendment 2026-10-21: no default-ask topic and no opt-out word, so old rows need no change).
Topic = Literal["files", "tasks", "money", "notes", "documents", "projects", "memory", "team", "routines", "posting", "browsing",
               "programs"]   # Programs: run_program and write_file in the bot's own workspace
FloorKind = Literal[
    "money_move", "delete_beyond_trash", "posting", "new_grant", "secret", "mass_edit",
    "commit_click", "typed_text", "contact", "new_site",   # C3: committing clicks, unapproved or contact text, off-fence
    "install_app",                                          # Install an app: software on the bot's computer
]

_TOPICS: frozenset[str] = frozenset(get_args(Topic))


@dataclass(frozen=True)
class BotApproval:
    """The mode, and the topics that always ask. ``posting`` is never stored: LOCKED_TOPICS adds it on the way out."""
    mode: ApprovalMode
    ask_topics: frozenset[Topic]
    auto_review: bool = False   # Full auto (schema v36): the bot's own model may review an unknown button instead of a card


@dataclass(frozen=True)
class ApprovalState:
    """What one run's gate needs to judge a call by approval mode."""
    mode: ApprovalMode
    ask_topics: frozenset[Topic]
    cards: bool                                      # this run may park on a card (your own chat)
    mac_writes: int = 0                              # this bot's unapproved Mac writes in MAC_WRITES_WINDOW_S
    session_folders: frozenset[str] = frozenset()    # casefolded labels with a live read OK
    plan_steps: int = 0
    standing: StandingState | None = None            # a routine run's standing permissions (None: any other run)
    auto_review: bool = False                        # Full auto: on only for the bot's own 1:1 chat runs (v36)


DEFAULT_BOT_APPROVAL = BotApproval(NEW_BOT_APPROVAL_MODE, frozenset(), NEW_BOT_AUTO_REVIEW)  # type: ignore[arg-type]


def parse_topics(raw: str) -> frozenset[Topic]:
    """The stored JSON list as topics; unknown words and bad JSON are ignored, never an error."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return frozenset()
    if not isinstance(data, list):
        return frozenset()
    return frozenset(word for word in data if isinstance(word, str) and word in _TOPICS)  # type: ignore[misc]


def topics_json(topics: frozenset[Topic] | set[str]) -> str:
    """The stored form: a sorted JSON list, without the locked topics."""
    return json.dumps(sorted(t for t in topics if t in _TOPICS and t not in LOCKED_TOPICS))


def locked_topics() -> list[str]:
    return sorted(LOCKED_TOPICS)


@dataclass(frozen=True)
class DiffView:
    """A unified, line-based diff and its counts."""
    text: str
    plus: int
    minus: int


@dataclass(frozen=True)
class ArgRow:
    """One stored argument as the card shows it: a fixed label and its whole value as plain text."""
    key: str
    label: str
    value: str


@dataclass(frozen=True)
class DraftBox:
    """One box a Send would send, as it held its text when the card was made (owner, 2026-11-03)."""
    label: str                            # the box's own label ("Cover letter"), its row's name on the card
    text: str
    node: int | None = None               # the box (a backend node id), read again on Yes
    yours: bool = False                   # the box holds your own words (from your message or an answered card)


DRAFT_DEFAULT_LABEL = "Message"           # a box with no label of its own


@dataclass(frozen=True)
class PendingCall:
    """One step of a card: the resolved call that Yes will run, and how the card describes it."""
    tool: str
    arguments: Mapping[str, Any]          # the resolved call; a Mac write holds grant_id, path, base_sha256, new_text
    topic: Topic | None
    title: str
    detail: str = ""
    diff: DiffView | None = None
    floor: FloorKind | None = None
    tainted_basis: bool = False           # a relaxed edit from a tainted run: "Based on outside content"
    session_offer: bool = False           # a read the user may OK once for the session
    rows: tuple[ArgRow, ...] = ()         # EVERY stored argument, in display order (rows.py); what shows is what runs
    crop: str | None = None               # C3: base64 JPEG (<= CU_CROP_MAX_BYTES) of the control; only in sealed steps
    act: Mapping[str, Any] | None = None  # C3: the frozen page resolution (resolution_to_json) the Yes re-checks
    # 2026-10-27 / 2026-11-03: what a Send sends, box by box as they held it; Yes needs every box to hold the same.
    drafts: tuple[DraftBox, ...] = ()


class CardTooBig(Exception):
    """The steps do not fit in one sealed card."""


def step_to_dict(step: PendingCall) -> dict[str, Any]:
    return {
        "tool": step.tool, "arguments": dict(step.arguments), "topic": step.topic, "title": step.title,
        "detail": step.detail, "floor": step.floor, "tainted_basis": step.tainted_basis,
        "session_offer": step.session_offer,
        "rows": [{"key": r.key, "label": r.label, "value": r.value} for r in step.rows],
        "diff": None if step.diff is None else {"text": step.diff.text, "plus": step.diff.plus, "minus": step.diff.minus},
        "crop": step.crop, "act": None if step.act is None else dict(step.act),
        "drafts": [{"label": d.label, "text": d.text, "node": d.node, "yours": d.yours} for d in step.drafts],
    }


def _drafts_from(data: Mapping[str, Any]) -> tuple[DraftBox, ...]:
    """The stored boxes; a card stored before 2026-11-03 kept one ``draft`` and its ``draft_node``."""
    stored = data.get("drafts")
    if isinstance(stored, list):
        return tuple(DraftBox(str(d.get("label") or DRAFT_DEFAULT_LABEL), str(d.get("text") or ""),
                              _node_id(d.get("node")), d.get("yours") is True)
                     for d in stored if isinstance(d, Mapping) and d.get("text"))
    old = str(data.get("draft") or "")
    return (DraftBox(DRAFT_DEFAULT_LABEL, old, _node_id(data.get("draft_node"))),) if old else ()


def step_from_dict(data: Mapping[str, Any]) -> PendingCall:
    diff = data.get("diff")
    crop, act = data.get("crop"), data.get("act")
    return PendingCall(
        tool=str(data["tool"]), arguments=dict(data["arguments"]), topic=data.get("topic"), title=str(data["title"]),
        detail=str(data.get("detail", "")), floor=data.get("floor"), tainted_basis=bool(data.get("tainted_basis")),
        session_offer=bool(data.get("session_offer")),
        rows=tuple(ArgRow(str(r["key"]), str(r["label"]), str(r["value"])) for r in data.get("rows", ())),
        diff=None if diff is None else DiffView(str(diff["text"]), int(diff["plus"]), int(diff["minus"])),
        crop=crop if isinstance(crop, str) else None, act=dict(act) if isinstance(act, Mapping) else None,
        drafts=_drafts_from(data),
    )


def _node_id(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def steps_json(steps: tuple[PendingCall, ...]) -> str:
    """The sealed form of a card's steps; ``CardTooBig`` when it is over APPROVAL_STEPS_MAX_BYTES."""
    text = json.dumps([step_to_dict(step) for step in steps])
    if len(text.encode()) > APPROVAL_STEPS_MAX_BYTES:
        raise CardTooBig
    return text


def steps_from_json(text: str) -> tuple[PendingCall, ...]:
    try:
        data = json.loads(text)
        return tuple(step_from_dict(item) for item in data)
    except (TypeError, ValueError, KeyError):
        return ()


class CardState(str, Enum):
    OPEN = "open"
    APPROVED = "approved"
    DECLINED = "declined"
    EDITED = "edited"
    FAILED = "failed"
    EXPIRED = "expired"


CardKind = Literal["ask", "plan"]


@dataclass(frozen=True)
class ApprovalDraft:
    """What a parked run hands the store."""
    bot_id: str
    thread_id: str
    work_item_id: str | None
    kind: CardKind
    steps: tuple[PendingCall, ...]
    request: str
    tainted: bool
    session_offer: bool = False


@dataclass(frozen=True)
class ApprovalCard:
    id: str
    user_id: str
    bot_id: str
    thread_id: str
    work_item_id: str | None
    kind: CardKind
    state: CardState
    steps: tuple[PendingCall, ...]
    request: str
    tainted: bool
    session_offer: bool
    answer_item_id: str | None
    created_at: str
    closed_at: str | None


@dataclass(frozen=True)
class StepOutcome:
    ok: bool
    text: str
    tainted: bool = False


class CardClosed(Exception):
    """The card was answered already (or replaced): the route answers 409."""


class BadAnswer(Exception):
    """An answer that does not fit this card: the route answers 422. The message is a plain sentence."""


class DiffOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    text: str
    plus: int
    minus: int
    truncated: bool


class RowOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    key: str
    label: str
    value: str
    truncated: bool


class StepOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tool: str
    topic: str | None
    title: str
    detail: str
    floor: str | None
    tainted_basis: bool
    session_offer: bool
    rows: list[RowOut]
    diff: DiffOut | None
    crop: str | None = None   # C3: the control's picture, only in GET /api/approvals/{id}?full=1


class ChoiceOut(BaseModel):
    """An options card's question and options, as stored."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    question: str
    options: list[str]
    safe: int
    own: bool
    why: str


class ApprovalCardOut(BaseModel):
    """The card's wire shape: no ``user_id``, no ``request``."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    bot_id: str
    thread_id: str
    kind: CardKind
    state: CardState
    tainted: bool
    session_offer: bool
    created_at: str
    closed_at: str | None
    steps: list[StepOut]
    choice: ChoiceOut | None = None
    send: bool = False         # a Send card: Send · Don't send · Change it… (roost/approvals/send_card.py)
    pay: bool = False          # a Pay card: card fields, then the same Pay click (roost/payments/pay_card.py)
    from_web: bool = False     # the red "from web content" badge (on a Send card: only when its text came from a page)
    routine_id: str | None = None   # a routine run's card: it shows in that routine's run log, not the bot's chat


def _diff_out(diff: DiffView | None, mode: Literal["full", "cut", "counts"]) -> DiffOut | None:
    if diff is None:
        return None
    if mode == "counts":
        return DiffOut(text="", plus=diff.plus, minus=diff.minus, truncated=bool(diff.text))
    lines = diff.text.split("\n")
    if mode == "cut" and len(lines) > APPROVAL_DIFF_SHOWN_LINES:
        return DiffOut(text="\n".join(lines[:APPROVAL_DIFF_SHOWN_LINES]), plus=diff.plus, minus=diff.minus,
                       truncated=True)
    return DiffOut(text=diff.text, plus=diff.plus, minus=diff.minus, truncated=False)


_WHOLE_ROW_PREFIX = "draft"    # a Send card's text is shown whole (owner, 2026-11-03: the full text, readable)


def _rows_out(rows: tuple[ArgRow, ...], full: bool) -> list[RowOut]:
    cut = APPROVAL_ROW_SHOWN_CHARS

    def whole(row: ArgRow) -> bool:
        return full or len(row.value) <= cut or row.key.startswith(_WHOLE_ROW_PREFIX)

    return [RowOut(key=r.key, label=r.label, value=r.value if whole(r) else r.value[:cut], truncated=not whole(r))
            for r in rows]


def approval_card_out(card: ApprovalCard, *, full: bool = False, counts_only: bool = False) -> ApprovalCardOut:
    """The wire card. ``full`` keeps whole diffs and the C3 crop; ``counts_only`` (live frames) drops the diff
    text and the crop, which only ``GET /api/approvals/{id}?full=1`` serves."""
    mode: Literal["full", "cut", "counts"] = "counts" if counts_only else ("full" if full else "cut")
    from roost.choices.models import choice_of   # here: choices.models builds on this module
    from roost.approvals.send_card import is_send_card, shows_web_badge
    from roost.payments.pay_card import is_pay_card
    view = choice_of(card)
    return ApprovalCardOut(
        id=card.id, bot_id=card.bot_id, thread_id=card.thread_id, kind=card.kind, state=card.state,
        tainted=card.tainted, session_offer=card.session_offer, created_at=card.created_at,
        closed_at=card.closed_at,
        steps=[StepOut(tool=s.tool, topic=s.topic, title=s.title, detail=s.detail, floor=s.floor,
                       tainted_basis=s.tainted_basis, session_offer=s.session_offer,
                       rows=_rows_out(s.rows, full), diff=_diff_out(s.diff, mode),
                       crop=s.crop if mode == "full" else None)
               for s in card.steps],
        choice=None if view is None else ChoiceOut(question=view.question, options=list(view.options),
                                                   safe=view.safe, own=view.own, why=view.why),
        send=is_send_card(card), from_web=shows_web_badge(card), pay=is_pay_card(card),
    )
