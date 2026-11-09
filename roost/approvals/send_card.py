"""The Send card (owner, 2026-11-03): an Ask card whose one step is a hard-floor send, submit or accept click or key on
the bot's own computer. It shows every box the bot typed and answers Send · Don't send · Change it…; Change it posts
your words as your own message. Its red "from web content" badge shows only when the text came from a page
(``PendingCall.tainted_basis``, set by the runner's copy check), never merely because the bot looked at one; the
card's own taint (what the answer carries on) never changes."""

from __future__ import annotations

from roost.approvals.models import ApprovalCard, PendingCall

SEND_CLASSES: frozenset[str] = frozenset({"send", "submit", "accept"})
_COMMIT_FLOOR = "commit_click"
_TYPE_TOOL = "type"


def _act_class(step: PendingCall) -> str | None:
    """The stored act's commit class: a click is read again from its own control, a key keeps its resolved class."""
    from roost.computer_use.commit_words import commit_class          # here: the screen modules build on approvals
    from roost.computer_use.models import resolution_from_json
    try:
        act = resolution_from_json(step.act or {})
    except ValueError:
        return None
    return commit_class(act.target) if act.tool == "click" else act.commit


def is_send_step(step: PendingCall) -> bool:
    return step.act is not None and step.floor == _COMMIT_FLOOR and _act_class(step) in SEND_CLASSES


def is_send_card(card: ApprovalCard) -> bool:
    return card.kind == "ask" and len(card.steps) == 1 and is_send_step(card.steps[0])


def _text_card(card: ApprovalCard) -> bool:
    """A Send card, or a card that types text on the page: its badge follows where the text came from."""
    if card.kind != "ask" or len(card.steps) != 1:
        return False
    step = card.steps[0]
    return is_send_step(step) or (step.act is not None and step.tool == _TYPE_TOOL)


def shows_web_badge(card: ApprovalCard) -> bool:
    if _text_card(card):
        return card.tainted and card.steps[0].tainted_basis
    return card.tainted
