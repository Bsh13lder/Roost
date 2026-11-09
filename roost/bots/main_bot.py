"""The main bot from the start (S1 D4).

``ensure_main_bot`` is idempotent:
- A user who already has a main bot keeps it.
- Otherwise their oldest Chief gets the star. The Chief is the bot made from
  the "chief" template or, failing that, the bot named "Chief" (any case,
  ignoring a leading/trailing space).
- Otherwise a Chief is created from the template and starred.

It runs on registration and once per boot for every account, so an account
made before S1 ends up with exactly one main bot and never a duplicate.
``idx_bots_one_primary`` (schema v2) makes two impossible."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from roost.bots.models import Bot, BotDraft, DuplicateBotName
from roost.bots.store import BotStore, normalize_bot_name
from roost.bots.templates import CHIEF
from roost.config import Config
from roost.db.connection import db_session

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MainBot:
    bot: Bot
    created: bool
    starred: bool


def _chief_in(team: list[Bot]) -> Bot | None:
    """The oldest Chief (``BotStore.list`` is ordered by ``created_at``).
    The by-name match uses the same normalization as the store's own
    uniqueness key (``normalize_bot_name``), so a name that only differs by
    case or a trailing/leading space — which ``BOT_NAME_PATTERN`` allows and
    some clients send — is still recognized as the same Chief instead of
    colliding with it on create."""
    by_template = [bot for bot in team if bot.template_id == CHIEF.id]
    chief_key = normalize_bot_name(CHIEF.name)
    by_name = [bot for bot in team if normalize_bot_name(bot.name) == chief_key]
    found = by_template or by_name
    return found[0] if found else None


async def _star(bots: BotStore, user_id: str, bot: Bot) -> Bot:
    changed = await bots.set_primary(user_id, bot.id)
    return changed[0] if changed else bot


def _chief_draft() -> BotDraft:
    return BotDraft(name=CHIEF.name, job=CHIEF.job, instructions=CHIEF.instructions,
                    avatar=CHIEF.avatar, template_id=CHIEF.id)


async def ensure_main_bot(bots: BotStore, user_id: str) -> MainBot:
    primary = await bots.get_primary(user_id)
    if primary is not None:
        return MainBot(primary, created=False, starred=False)
    existing = _chief_in(await bots.list(user_id))
    if existing is not None:
        return MainBot(await _star(bots, user_id, existing), created=False, starred=True)
    try:
        made = await bots.create(user_id, _chief_draft())
    except DuplicateBotName:
        # A Chief appeared since the listing (a concurrent ensure): star that one.
        raced = _chief_in(await bots.list(user_id))
        if raced is None:
            raise
        return MainBot(await _star(bots, user_id, raced), created=False, starred=True)
    return MainBot(await _star(bots, user_id, made), created=True, starred=True)


async def ensure_main_bots(config: Config, bots: BotStore) -> tuple[MainBot, ...]:
    """Boot: every account gets its main bot. One account's failure is logged
    and never stops the gateway or the other accounts."""
    async with db_session(config) as db:
        rows = await (await db.execute("SELECT id FROM users ORDER BY created_at")).fetchall()
    results: tuple[MainBot, ...] = ()
    for row in rows:
        try:
            result = await ensure_main_bot(bots, row["id"])
        except Exception:
            logger.exception("Could not make sure user %s has a main bot", row["id"])
            continue
        if result.created or result.starred:
            logger.warning("Main bot for user %s: %s %s", row["id"], "created" if result.created else "starred",
                           result.bot.id)
        results = (*results, result)
    return results
