"""W10 (owner, 2026-10-31): a button you said Yes to on a card clicks again with no new card.

Upwork's approved "Apply now" left the page where it was, so the bot clicked it again and every click asked again.
``repeats_approved`` is pure: the live act names the very control of an approved card's step (``same_target``: the
same page address, host, label, structure, class and place), so the page has not moved on, and its class is one that
is safe to press twice (``OWNER_AGAIN_CLASSES``: submit and accept; a second Send or Pay would send or pay twice).
``approved_before`` reads this chat's cards approved in the last ``OWNER_AGAIN_WINDOW_S``."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable

from roost.approvals.models import steps_from_json
from roost.computer_use.commit_words import commit_class
from roost.computer_use.models import ActResolution, resolution_from_json, same_target
from roost.config import Config
from roost.crypto.encryption import decrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.owner_words.constants import OWNER_AGAIN_CARDS_MAX, OWNER_AGAIN_CLASSES, OWNER_AGAIN_WINDOW_S

logger = logging.getLogger(__name__)

_CLASSES = frozenset(OWNER_AGAIN_CLASSES)
_CLICK = "click"


def repeats_approved(approved: Iterable[ActResolution], live: ActResolution) -> bool:
    """True when ``live`` clicks the same submit or accept control as one of ``approved``, on the same page."""
    if live.tool != _CLICK or live.target is None or commit_class(live.target) not in _CLASSES:
        return False
    return any(same_target(stored, live) for stored in approved)


def _stored_clicks(steps_text: str) -> tuple[ActResolution, ...]:
    found: list[ActResolution] = []
    for step in steps_from_json(steps_text):
        if step.tool != _CLICK or not step.act:
            continue
        try:
            found.append(resolution_from_json(step.act))
        except ValueError:
            logger.warning("An approved card's stored click could not be read; it is not reused")
    return tuple(found)


async def _approved_clicks(config: Config, user_id: str, thread_id: str, since: str) -> tuple[ActResolution, ...]:
    async with db_session(config) as db:
        rows = await (await db.execute(
            "SELECT steps FROM approval_cards WHERE user_id = ? AND thread_id = ? AND state = 'approved' "
            "AND closed_at >= ? ORDER BY closed_at DESC LIMIT ?",
            (user_id, thread_id, since, OWNER_AGAIN_CARDS_MAX))).fetchall()
    if not rows:
        return ()
    dek = await get_user_dek(config, user_id)
    aad = user_aad(user_id, "approval_cards:steps")
    return tuple(act for row in rows
                 for act in _stored_clicks(decrypt_field(row["steps"], dek, aad, fallback="[]") or "[]"))


async def approved_before(config: Config, user_id: str, thread_id: str, live: ActResolution, *,
                          now: str | None = None) -> bool:
    """You said Yes to this very control in this chat within the window (``now``: an ISO time, for tests)."""
    if not thread_id or live.tool != _CLICK or live.target is None:
        return False
    moment = datetime.fromisoformat(now) if now else datetime.now(timezone.utc)
    since = (moment - timedelta(seconds=OWNER_AGAIN_WINDOW_S)).isoformat()
    return repeats_approved(await _approved_clicks(config, user_id, thread_id, since), live)
