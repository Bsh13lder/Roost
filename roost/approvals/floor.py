"""The hard floor: calls that ask in every mode, Plan mode included, and that no session OK covers.

``hard_floor`` judges a write call by its arguments; ``floor_of`` (C3) judges a click or keystroke by its
resolution from the live page, never by the model's arguments."""

from __future__ import annotations

import re
from typing import Any, Iterator, Mapping

from roost.approvals import topics
from roost.approvals.models import ApprovalState, FloorKind
from roost.computer_use.commit_words import commit_class
from roost.computer_use.fence import SiteFence
from roost.computer_use.models import ActResolution
from roost.constants import MAC_WRITES_PER_RUN
from roost.memory.secrets import looks_secret

# Clicks that commit nothing (C3, design §6.1): consent counts as browsing (R4).
ORDINARY_CLASSES = frozenset({"browsing", "consent"})


# Arguments that name a thing and never hold the user's words: a file's hash looks like a token, but it is not a secret.
_NOT_CONTENT_KEYS = frozenset({"base_hash", "base_sha256", "expected_sha256", "grant_id", "folder", "path", "new_path"})


# A whole value that is a record's id (Roost's ids are UUIDs: a task, a step, a memory) names a thing; it looked like
# a secret token, so adding a step to a task hit the floor (owner, 2026-10-29). Inside other words it still counts.
_RECORD_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _strings(value: Any) -> Iterator[str]:
    """Every string value in ``value``, walking dicts and lists (keys are names, not content; a bare record id is
    not content either)."""
    if isinstance(value, str):
        if not _RECORD_ID.fullmatch(value.strip()):
            yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            if key not in _NOT_CONTENT_KEYS:
                yield from _strings(item)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from _strings(item)


def hard_floor(name: str, arguments: Mapping[str, Any], state: ApprovalState) -> FloorKind | None:
    """The floor kind this write call hits, or None."""
    listed = topics.FLOOR_TOOLS.get(name)
    if listed is not None:
        return listed
    topic = topics.topic_of(name)
    if topic == "posting":
        return "posting"
    if any(looks_secret(text) for text in _strings(arguments)):
        return "secret"
    if topic == "files" and state.mac_writes >= MAC_WRITES_PER_RUN:
        return "mass_edit"
    return None


def act_commits(r: ActResolution) -> bool:
    """Whether an act commits something. A click is re-read from its own control, so a resolution that
    was classed as browsing for a "Buy now" button still commits; nothing resolvable always commits on the page.
    A screen act (anything but Brave in front, full computer D1) has no page and commits nothing."""
    if r.space == "screen":
        return False
    if r.tool == "click" and (r.target is None or commit_class(r.target) not in ORDINARY_CLASSES):
        return True
    return r.commit not in ORDINARY_CLASSES


def _your_sign_in_name(r: ActResolution) -> bool:
    """B3: your own email or user name (your words, nothing secret) into a sign-in page's email box."""
    return (r.text_ok is True and r.text_flags == frozenset({"contact"}) and r.target is not None
            and r.target.sign_in_box and not r.target.secret_field)


def _typed_floor(r: ActResolution) -> FloorKind | None:
    """Owner, 2026-11-03: typing never asks, on any site, in the bot's own words or yours. Only a secret, or an email
    address or phone number you never gave the bot, still asks; what sends the text keeps its Send card."""
    if "secret" in r.text_flags:
        return "secret"
    if "contact" in r.text_flags and not _your_sign_in_name(r):
        return "contact"
    return None


def floor_of(r: ActResolution, fence: SiteFence | None = None, *, typed_chars: int | None = None) -> FloorKind | None:
    """The floor kind a click or keystroke hits, or None. ``fence``: a link or a form sent to a host outside
    it is ``new_site``. ``typed_chars`` is accepted for the callers that still pass it: since typing stopped
    asking (owner, 2026-11-03) its length decides nothing. A screen act is outside Brave: no floor (full computer,
    D1)."""
    if r.space == "screen":
        return None
    if r.nav_host and (fence is None or not fence.allows(r.nav_host)):
        return "new_site"
    if act_commits(r):
        return "commit_click"
    if r.tool == "type":
        return _typed_floor(r)
    return None
