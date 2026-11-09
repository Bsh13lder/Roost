"""``OwnerWordsGuard``: what the gate does with an ``owner_words`` verdict before the act runs (W2).

The pure judge only saw that the act carries a quote that checked out as yours and is of a kind your words may
cover; the guard asks the bot's own model whether the words really ask for this act. Any "no" or error is the hard-floor ask (a
never where no card can open), so your words can only ever skip a card, never widen what a bot may do."""

from __future__ import annotations

from typing import Any, Mapping

from roost.computer_use.commit_words import commit_class
from roost.computer_use.models import ActResolution
from roost.llm.registry import check_model
from roost.llm.types import Model
from roost.owner_words.check import OwnerFacts, words_fit
from roost.standing.guard import floor_ask
from roost.talk.verdict import GateContext, Verdict


def owner_facts(act: ActResolution, arguments: Mapping[str, Any]) -> OwnerFacts:
    """The act as the page resolved it; the typed text is the one thing taken from the call (it is what types)."""
    target = act.target
    button = ""
    if target is not None:
        button = target.form_submit_text if act.tool == "press_key" else (target.text or target.visible_text)
    if act.tool == "type":
        typed = arguments.get("text")
        return OwnerFacts(act.owner_words, act.host, "type", button, typed if isinstance(typed, str) else "")
    action = commit_class(target) if act.tool == "click" else act.commit
    return OwnerFacts(act.owner_words, act.host, action, button, None)


class OwnerWordsGuard:
    def __init__(self, worker: Model) -> None:
        self._worker = worker

    async def confirm(self, verdict: Verdict, arguments: Mapping[str, Any], ctx: GateContext,
                      act: ActResolution | None) -> Verdict:
        """``verdict`` when the bot's own model says your words fit this act, else the hard-floor ask."""
        if act is None or not act.owner_words:
            return floor_ask(ctx)
        if not await words_fit(self._worker, owner_facts(act, arguments), model_id=check_model(ctx.check_model)):
            return floor_ask(ctx)
        return verdict
