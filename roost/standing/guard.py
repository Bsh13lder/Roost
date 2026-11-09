"""``StandingGuard``: what the gate does with a ``standing_ok`` verdict before the act runs.

The judge matched against the permissions read when the run started; the guard checks again, live: the permission
is not revoked, has not ended and has some of today's (local) count left; then the model check reads the act; then
a committing act takes one of the count with an atomic compare-and-set. Any "no" on the way, or any error, is the
hard-floor ask (a never where no card can open). So a standing permission can only ever be narrowed, never widened."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from roost.approvals.texts import NEEDS_YOUR_OK_TEXT
from roost.computer_use.models import ActResolution
from roost.llm.registry import check_model
from roost.llm.types import Model
from roost.standing.check import ActFacts, act_fits
from roost.standing.models import StandingMatch
from roost.standing.store import PermissionStore
from roost.talk.verdict import GateContext, Verdict
from roost.work.runs import madrid_today


def floor_ask(ctx: GateContext) -> Verdict:
    """The verdict a standing act falls back to: the hard-floor ask, or never when the run can't show a card."""
    if ctx.approval is None or not ctx.approval.cards:
        return Verdict("never", "needs_your_ok", NEEDS_YOUR_OK_TEXT)
    return Verdict("ask", "hard_floor")


def act_facts(match: StandingMatch, act: ActResolution, arguments: Mapping[str, Any]) -> ActFacts:
    """The act as the page resolved it; the typed text is the one thing taken from the call (it is what types)."""
    target = act.target
    words = ""
    if target is not None:
        words = target.form_submit_text if act.tool == "press_key" else (target.text or target.visible_text)
    typed = arguments.get("text") if act.tool == "type" else None
    return ActFacts(host=act.host, action=match.action, words=words,
                    typed=typed if isinstance(typed, str) else ("" if act.tool == "type" else None))


class StandingGuard:
    def __init__(self, store: PermissionStore, worker: Model) -> None:
        self._store = store
        self._worker = worker

    async def confirm(self, user_id: str, verdict: Verdict, arguments: Mapping[str, Any], ctx: GateContext,
                      act: ActResolution | None) -> Verdict:
        """``verdict`` when every check passes, else the hard-floor ask."""
        match = verdict.standing
        state = ctx.approval.standing if ctx.approval is not None else None
        if match is None or state is None or act is None:
            return floor_ask(ctx)
        today = madrid_today(datetime.now(timezone.utc))
        if not await self._store.is_live(user_id, match.permission_id, today):
            return floor_ask(ctx)
        facts = act_facts(match, act, arguments)
        if not await act_fits(self._worker, state.instructions, facts, model_id=check_model(ctx.check_model)):
            return floor_ask(ctx)
        if match.consume and not await self._store.consume(user_id, match.permission_id, today):
            return floor_ask(ctx)
        return verdict
