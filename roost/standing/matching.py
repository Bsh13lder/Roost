"""Which standing permission covers a hard-floor act (pure; it reads only the page's resolution).

The act's action comes from the commit lexicon (``commit_class``), never from the model's arguments: the class
``send`` is ``post`` when the control's words say post, publish, share, tweet or comment and ``send`` otherwise;
the class ``submit`` is ``submit``. Spend, delete, account, accept and unknown never match, nor does a covered
control, a form sent to another site, a new site, contact details or a secret. Typing into a box on a permitted
site matches without using the day's count (the click or Enter that sends it does)."""

from __future__ import annotations

from roost.approvals.models import FloorKind
from roost.computer_use.commit_words import commit_class, normalise
from roost.computer_use.fence import SiteFence
from roost.computer_use.models import ActResolution, PageTarget
from roost.standing.constants import STANDING_POST_WORDS
from roost.standing.models import LivePermission, StandingAction, StandingMatch, StandingState

_POST = frozenset(normalise(word) for word in STANDING_POST_WORDS)


def _says_post(target: PageTarget, *, enter: bool) -> bool:
    texts = (target.form_submit_text,) if enter else (target.text, target.visible_text)
    words = {word for text in texts for word in normalise(text).split()}
    return bool(words & _POST)


def _class_of(r: ActResolution) -> str:
    """The act's commit class, read again from its own control for a click (as ``act_commits`` does)."""
    if r.tool == "click":
        return commit_class(r.target)
    return r.commit


def act_action(r: ActResolution) -> StandingAction | None:
    """The standing action a committing click or key is, or None when no permission may ever cover it."""
    if r.target is None or r.tool == "type":
        return None
    found = _class_of(r)
    if found == "submit":
        return "submit"
    if found == "send":
        return "post" if _says_post(r.target, enter=r.tool == "press_key") else "send"
    return None


def _on_site(permission: LivePermission, r: ActResolution) -> bool:
    site = SiteFence(frozenset({permission.host}))
    return site.allows(r.host) and (not r.nav_host or site.allows(r.nav_host))


def _usable(r: ActResolution) -> bool:
    return r.target is not None and not r.covered_by and not r.refusal and not r.text_flags


def match_act(state: StandingState | None, r: ActResolution, kind: FloorKind) -> StandingMatch | None:
    """The permission that covers this act at floor ``kind``, or None (the act asks as before)."""
    if state is None or not _usable(r):
        return None
    live = tuple(p for p in state.permissions if p.remaining > 0 and _on_site(p, r))
    if kind == "typed_text" and r.tool == "type":
        first = live[0] if live else None
        return StandingMatch(first.id, first.host, first.action, consume=False) if first else None
    action = act_action(r) if kind == "commit_click" else None
    chosen = next((p for p in live if p.action == action), None)
    return StandingMatch(chosen.id, chosen.host, chosen.action, consume=True) if chosen else None
