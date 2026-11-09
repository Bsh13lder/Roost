"""Which Ask card is a Pay card (P2): one stored click or key on the bot's own computer whose class is ``spend``,
parked by the hard floor. Only such a card offers card fields, and only in your own chat (checked by the route)."""

from __future__ import annotations

from roost.approvals.models import ApprovalCard, PendingCall

_COMMIT_FLOOR = "commit_click"
_SPEND = "spend"


def _act_class(step: PendingCall) -> str | None:
    from roost.computer_use.commit_words import commit_class          # here: the screen modules build on approvals
    from roost.computer_use.models import resolution_from_json
    try:
        act = resolution_from_json(step.act or {})
    except ValueError:
        return None
    return commit_class(act.target) if act.tool == "click" else act.commit


def pay_host(card: ApprovalCard) -> str:
    """The host the Pay button was on when the card was made ("" when the card is no Pay card)."""
    from roost.computer_use.models import resolution_from_json
    if not is_pay_card(card):
        return ""
    return resolution_from_json(card.steps[0].act or {}).host


def is_pay_card(card: ApprovalCard) -> bool:
    if card.kind != "ask" or len(card.steps) != 1:
        return False
    step = card.steps[0]
    return step.act is not None and step.floor == _COMMIT_FLOOR and _act_class(step) == _SPEND
