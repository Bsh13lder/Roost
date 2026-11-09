"""The computer-use loop's rules (C3 design §7; the loop rules R1, R4 and R8).

- **One loop per computer:** ``ComputerUseLease`` (``app.state.cu_leases``) lets one run at a time use a bot's
  screen. It lives in memory, so a restart clears it, like the ``ControlLock``.
- **Act, then check (R1):** every click, type or key press needs a ``look`` taken after the last thing that moved
  the screen (an act or a scroll). The one exception is ``type`` right after the click that focused the field.
- **One screen action per model step,** so a blind chain can't happen.
- **Take control (R8):** when ``ControlLock.epoch`` has moved since the run's last look, the next act looks first.
- **The ladder (R4):** a second miss on the same aim ends in a Stuck card.
- **Closing a pop-up (owner, 2026-11-05):** Escape needs no fresh look, and right after a click a dialog covered, a
  click on that dialog's own close button (named in the miss, ``closers``) needs none either. Both still go through
  the gate; a committing click always looks first.
- **The budget:** ``CU_MAX_ACTS_PER_RUN`` acts and ``CU_MAX_LOOKS_PER_RUN`` looks per run.

``LoopState`` is frozen: every ``after_*`` returns a new state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Mapping

from roost.approvals.floor import ORDINARY_CLASSES
from roost.computer_use.commit_words import commit_class, is_text_box
from roost.computer_use.models import ActResolution
from roost.constants import (
    CU_ACT_TOOLS, CU_LOOK_FREE_KEYS, CU_MAX_ACTS_PER_RUN, CU_MAX_LOOKS_PER_RUN, CU_TOOLS, CU_TRIES_PER_TARGET,
)

LOOK_FIRST_TEXT = "Look first: the screen changed since your last look, so look at it before you act."
TAKEN_TEXT = "Look first: the screen may have changed while you had it."
ONE_ACTION_TEXT = "One screen action per step: look at the result first."
BUDGET_TEXT = (
    f"I used this job's screen budget ({CU_MAX_ACTS_PER_RUN} actions, {CU_MAX_LOOKS_PER_RUN} looks), so I stopped."
)
BUSY_TEXT = "My computer is busy with another job of mine."

_EMPTY: Mapping[str, Any] = MappingProxyType({})


class ComputerUseLease:
    """Which run uses each bot's screen. In memory on purpose: a restart frees every computer."""

    def __init__(self) -> None:
        self._holders: Mapping[str, str] = MappingProxyType({})

    def acquire(self, bot_id: str, run_id: str) -> bool:
        """True when the computer is free or already this run's (it is then this run's)."""
        current = self._holders.get(bot_id)
        if current is not None and current != run_id:
            return False
        self._holders = MappingProxyType({**self._holders, bot_id: run_id})
        return True

    def release(self, bot_id: str, run_id: str) -> None:
        """Only the run that holds it releases it; anyone else's release changes nothing."""
        if self._holders.get(bot_id) == run_id:
            self._holders = MappingProxyType({k: v for k, v in self._holders.items() if k != bot_id})

    def holder(self, bot_id: str) -> str | None:
        return self._holders.get(bot_id)


@dataclass(frozen=True)
class LoopState:
    run_id: str
    looks: int = 0
    acts: int = 0
    screen_version: int = 0
    looked_at_version: int = -1
    control_epoch: int = 0
    focused_by_click: str = ""                                  # the target key the last click focused
    tries: Mapping[str, int] = field(default_factory=lambda: _EMPTY)   # aim key -> misses
    typed: Mapping[str, str] = field(default_factory=lambda: _EMPTY)   # field label -> digest of what was typed
    expect: str = ""
    acted_this_step: bool = False
    used_screen: bool = False
    blind_scrolls: int = 0                                      # scrolls since the last look
    closers: frozenset[int] = frozenset()                       # the covering dialog's close buttons (a covered miss)


def target_key(r: ActResolution) -> str:
    """Names the control an act resolved to (host, kind and label), or the point when nothing resolved."""
    t = r.target
    if t is None:
        return json.dumps(["point", r.host, list(r.point) if r.point else None])
    return json.dumps(["target", r.host, t.kind, t.tag, t.text])


def aim_key(name: str, arguments: Mapping[str, Any]) -> str:
    """Names what the model aimed at (for the try-once-more ladder): the target text, kind and nth, or the
    point, or the key. Built from the model's own arguments, which is fine: it only counts misses."""
    target = arguments.get("target")
    if isinstance(target, Mapping):
        aim: Any = ["target", str(target.get("text", "")), str(target.get("kind", "any")), target.get("nth", 1)]
    elif "x" in arguments or "y" in arguments:
        aim = ["point", arguments.get("x"), arguments.get("y")]
    else:
        aim = ["key", str(arguments.get("key", ""))]
    return json.dumps([name, *aim], default=str)


def budget_left(state: LoopState) -> str | None:
    """None while the run may still act and look; else the budget sentence."""
    if state.acts >= CU_MAX_ACTS_PER_RUN or state.looks >= CU_MAX_LOOKS_PER_RUN:
        return BUDGET_TEXT
    return None


def _closes_popup(name: str, arguments: Mapping[str, Any]) -> bool:
    """A key that only closes a pop-up (Escape), pressed wherever the focus is (an index would click a box first)."""
    return (name == "press_key" and arguments.get("index") is None
            and str(arguments.get("key", "")) in CU_LOOK_FREE_KEYS)


def _look_free(state: LoopState, name: str, arguments: Mapping[str, Any]) -> bool:
    """An act that may run on a stale look: Escape, or (judged again by ``closes_cover`` once it is resolved) a
    click right after a covered miss that named the dialog's close buttons."""
    return _closes_popup(name, arguments) or (name == "click" and bool(state.closers))


def closes_cover(state: LoopState, r: ActResolution) -> bool:
    """The resolved click is one of the covering dialog's own close buttons the miss named, and commits nothing."""
    return (r.tool == "click" and r.target is not None and r.target.node_id in state.closers
            and commit_class(r.target) in ORDINARY_CLASSES)


def precheck(state: LoopState, name: str, epoch: int, arguments: Mapping[str, Any] = _EMPTY) -> str | None:
    """Why this screen call may not run now, or None. ``epoch`` is ``ControlLock.epoch`` at this moment."""
    if name not in CU_TOOLS:
        return None
    spent = budget_left(state)
    if spent is not None:
        return spent
    if state.acted_this_step:
        return ONE_ACTION_TEXT
    if name not in CU_ACT_TOOLS:
        return None
    focused = name == "type" and bool(state.focused_by_click)
    if state.looked_at_version != state.screen_version and not focused and not _look_free(state, name, arguments):
        return LOOK_FIRST_TEXT
    if epoch != state.control_epoch:
        return TAKEN_TEXT
    return None


def new_step(state: LoopState) -> LoopState:
    """A new model step began: one more screen action may run."""
    return replace(state, acted_this_step=False) if state.acted_this_step else state


def after_look(state: LoopState, epoch: int) -> LoopState:
    return replace(state, looks=state.looks + 1, looked_at_version=state.screen_version, control_epoch=epoch,
                    acted_this_step=True, used_screen=True, blind_scrolls=0, closers=frozenset())


def after_wait(state: LoopState) -> LoopState:
    return replace(state, acted_this_step=True, used_screen=True)


def after_scroll(state: LoopState) -> LoopState:
    return replace(state, screen_version=state.screen_version + 1, focused_by_click="", acted_this_step=True,
                   used_screen=True, blind_scrolls=state.blind_scrolls + 1, closers=frozenset())


def _focuses_a_box(r: ActResolution) -> bool:
    return r.tool == "click" and r.target is not None and is_text_box(r.target)


def typed_digest(text: str) -> str:
    """What a ``type`` keeps of its text: a SHA-256 digest, never the text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def after_act(state: LoopState, r: ActResolution, expect: str, *, typed_digest: str | None = None) -> LoopState:
    """An act ran: the screen moved, so the next act looks first, except ``type`` into the box this click
    focused. A ``type`` records only a digest of its text against the field."""
    typed = state.typed
    if r.tool == "type" and typed_digest is not None and r.target is not None:
        typed = MappingProxyType({**state.typed, r.target.text: typed_digest})
    return replace(
        state, acts=state.acts + 1, screen_version=state.screen_version + 1,
        focused_by_click=target_key(r) if _focuses_a_box(r) else "", typed=typed, expect=expect,
        acted_this_step=True, used_screen=True, closers=frozenset(),
    )


def after_open(state: LoopState) -> LoopState:
    """open_app ran (full computer): a window came up, so the next act looks first. It counts as an act."""
    return replace(state, acts=state.acts + 1, screen_version=state.screen_version + 1, focused_by_click="",
                   acted_this_step=True, used_screen=True, closers=frozenset())


def after_miss(state: LoopState, key: str, *, closers: frozenset[int] = frozenset()) -> tuple[LoopState, bool]:
    """One more miss on ``key``; True when that was the last try (then the run goes Stuck). ``closers``: a dialog
    covered the control, and these are its own close buttons the miss named (only they may run before a look)."""
    count = state.tries.get(key, 0) + 1
    # The model's picture of the page was wrong, so its next act looks again first (R4: re-read, then retry).
    missed = replace(state, tries=MappingProxyType({**state.tries, key: count}), looked_at_version=-1,
                     acted_this_step=True, used_screen=True, closers=closers)
    return missed, count >= CU_TRIES_PER_TARGET


def after_glance(state: LoopState) -> LoopState:
    """Fast pages: an act's result ended with a text-only look read after the page settled. That is the check R1
    asks for, so the next act needs no separate look; it is no look of the budget's."""
    return replace(state, looked_at_version=state.screen_version, blind_scrolls=0)


def forget_look(state: LoopState) -> LoopState:
    """A look's number no longer names the same control: the bot's view is stale, so its next act looks first."""
    return replace(state, looked_at_version=-1, acted_this_step=True, used_screen=True, closers=frozenset())


def after_read(state: LoopState) -> LoopState:
    """read_text or read_pdf ran: nothing on the screen moved, so the newest look still holds. It counts as a look
    of the budget's and as this step's one screen action."""
    return replace(state, looks=state.looks + 1, acted_this_step=True, used_screen=True)
