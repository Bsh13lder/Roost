"""``AutoReviewGuard``: what the gate does with an ``auto_review`` verdict before the act runs.

The pure judge only saw that the act is a click or key on a button Roost can't read, in Full auto, in your own chat;
the guard reads your newest request and the page title (through the runner's ``ReviewSource``) and asks the bot's
own model. Any
"no", a missing request or an error is the hard-floor ask, so auto-review can only ever skip a card for an unknown
button, never widen what a bot may do."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping

from roost.auto_review.check import ReviewFacts, review_says_safe
from roost.auto_review.rules import class_of
from roost.computer_use.models import ActResolution
from roost.llm.registry import check_model
from roost.llm.types import Model
from roost.standing.guard import floor_ask
from roost.talk.verdict import GateContext, Verdict


@dataclass(frozen=True)
class ReviewPage:
    """What the runner reads for a review: your newest own messages in this chat and the page's title."""
    request: str
    title: str


ReviewSource = Callable[[], Awaitable[ReviewPage]]


def review_facts(act: ActResolution, arguments: Mapping[str, Any], page: ReviewPage) -> ReviewFacts:
    """The control as the page resolved it; ``expect`` is the one thing taken from the call (the bot's own words)."""
    target = act.target
    expect = arguments.get("expect")
    return ReviewFacts(
        request=page.request, host=act.host, title=page.title,
        label=target.text if target is not None else "",
        visible_text=target.visible_text if target is not None else "",
        kind=target.kind if target is not None else "",
        in_dialog=target.in_dialog if target is not None else "",
        expect=expect if isinstance(expect, str) else "", crop=act.crop, commit=class_of(act),
    )


class AutoReviewGuard:
    def __init__(self, worker: Model) -> None:
        self._worker = worker

    async def confirm(self, verdict: Verdict, arguments: Mapping[str, Any], ctx: GateContext,
                      act: ActResolution | None, source: ReviewSource | None) -> Verdict:
        """``verdict`` when the bot's own model says the click is safe, else the hard-floor ask."""
        if act is None or source is None:
            return floor_ask(ctx)
        page = await source()
        if not page.request.strip():
            return floor_ask(ctx)
        facts = review_facts(act, arguments, page)
        if not await review_says_safe(self._worker, facts, model_id=check_model(ctx.check_model)):
            return floor_ask(ctx)
        return verdict
