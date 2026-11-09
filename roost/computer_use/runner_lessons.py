"""Lessons, L1 (docs/plans/2026-10-31-roost-lessons.md): predict, then check. The screen loop's two signal producers.

- **expect_missed:** a click (not one into a text box, which only focuses it) or Enter / Back left the page as it was (the same address, a ``#fragment`` aside, the same title
  and the same page text, read before the input and after the page settled), or typing that the box would not hold.
  An approved card's re-run counts too: it is recorded under that re-run's own run id (``card_signal_key``).
- **asked_again:** a second Ask card for the same control (``same_target``) in one run, or a card of this chat for
  that control within ``OWNER_AGAIN_WINDOW_S`` (a parked run ends, so the second card comes in the next run).

A signal holds the kind, the host and the act's commit class, never a label, ``expect``, typed text or page text.
Watching is best-effort: with no registry (``signals=None``) nothing is read, and a failure is logged with its type
only and never changes what the loop does.

``ComputerUse`` (``roost/computer_use/runner.py``) mixes this in: every attribute it reads is the runner's."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from roost.approvals.models import steps_from_json
from roost.computer_use.commit_words import is_text_box
from roost.computer_use.models import ActResolution, resolution_from_json, same_target
from roost.config import Config
from roost.crypto.encryption import decrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.lessons.signals import LessonSignal, LessonSignals, SignalKind
from roost.owner_words.constants import OWNER_AGAIN_CARDS_MAX, OWNER_AGAIN_WINDOW_S

logger = logging.getLogger(__name__)

PageMark = tuple[str, str, str]          # the address without its #fragment, the title, the page text (memory only)
_TYPE = "type"
_CLICK = "click"
# The keys that are meant to move the page; Tab, arrows, Space and the like change focus or a box, not the page.
LESSON_MOVING_KEYS = frozenset({"Enter", "Back"})


def page_moves(tool: str, arguments: Mapping[str, Any]) -> bool:
    """A click, or a key that is meant to move the page: its page is compared before and after."""
    return tool == _CLICK or (tool == "press_key" and str(arguments.get("key", "")) in LESSON_MOVING_KEYS)


async def page_mark(page: Any) -> PageMark | None:
    """What says whether an act moved the page; None when the page can't be read (then nothing is recorded)."""
    if page is None:
        return None
    try:
        address = (await page.url()).split("#", 1)[0]
        facts = await page.facts()
    except Exception as exc:     # best-effort: a silent browser is the loop's to report, never the watch's
        logger.info("A lesson's page mark could not be read: %s", type(exc).__name__)
        return None
    return address, facts.title, facts.text


def _stored_acts(steps_text: str) -> tuple[ActResolution, ...]:
    found: list[ActResolution] = []
    for step in steps_from_json(steps_text):
        if not step.act:
            continue
        try:
            found.append(resolution_from_json(step.act))
        except ValueError:
            continue
    return tuple(found)


async def carded_before(config: Config, user_id: str, thread_id: str, live: ActResolution) -> bool:
    """A card of this chat, in any state, asked about this very control within the window."""
    if not thread_id or live.target is None:
        return False
    since = (datetime.now(timezone.utc) - timedelta(seconds=OWNER_AGAIN_WINDOW_S)).isoformat()
    async with db_session(config) as db:
        rows = await (await db.execute(
            "SELECT steps FROM approval_cards WHERE user_id = ? AND thread_id = ? AND created_at >= ? "
            "ORDER BY created_at DESC LIMIT ?", (user_id, thread_id, since, OWNER_AGAIN_CARDS_MAX))).fetchall()
    if not rows:
        return False
    dek = await get_user_dek(config, user_id)
    aad = user_aad(user_id, "approval_cards:steps")
    return any(same_target(stored, live) for row in rows
               for stored in _stored_acts(decrypt_field(row["steps"], dek, aad, fallback="[]") or "[]"))


class LessonWatch:
    """Mixed into ``ComputerUse``."""

    _signals: LessonSignals | None
    _parked_acts: tuple[ActResolution, ...]      # this run's Ask cards' controls (memory only)

    async def _mark_before(self, tool: str, arguments: Mapping[str, Any]) -> PageMark | None:
        """The page before a click or a moving key (typing is judged by its own read-back)."""
        if self._signals is None or not page_moves(tool, arguments):
            return None
        return await page_mark(self._desk.page())

    async def _watch_act(self, r: ActResolution, tool: str, before: PageMark | None, note: str) -> None:
        """After an act's result: nothing moved, or the box refused the text, is ``expect_missed``."""
        if self._signals is None:
            return
        try:
            if tool == _TYPE:
                missed = bool(note)
            elif tool == _CLICK and r.target is not None and is_text_box(r.target):
                missed = False                   # a click into a box only focuses it: the page stays on purpose
            else:
                missed = before is not None and before == await page_mark(self._desk.page())
        except Exception as exc:
            logger.warning("A lesson's act check failed: %s", type(exc).__name__)
            return
        if missed:
            self._lesson("expect_missed", r)

    async def _watch_park(self, r: ActResolution) -> None:
        """A new Ask card: the same control asked before in this run or chat is ``asked_again``."""
        if self._signals is None:
            return
        try:
            again = any(same_target(p, r) for p in self._parked_acts) or await carded_before(
                self._run.config, self._run.user_id, self._run.thread_id or "", r)
        except Exception as exc:
            logger.warning("A lesson's card check failed: %s", type(exc).__name__)
            return
        finally:
            self._parked_acts = (*self._parked_acts, r)
        if again:
            self._lesson("asked_again", r)

    def _lesson(self, kind: SignalKind, r: ActResolution) -> None:
        try:
            self._signals.record(self._run.run_id, LessonSignal(kind, r.host, r.commit))  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("A lesson signal could not be kept: %s", type(exc).__name__)
