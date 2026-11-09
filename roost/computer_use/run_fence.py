"""The site fence of one chat, rebuilt for each run (C3 design §6.4): the hosts in your own messages in the chat
and the hosts you said Yes to on its new-site cards. A page never widens it. Every query names ``user_id``."""

from __future__ import annotations

import logging
from typing import Iterable

from roost.approvals.models import steps_from_json
from roost.computer_use.fence import SiteFence, fence_from
from roost.computer_use.routine_sites import routine_chat_hosts
from roost.computer_use.text_source import load_approved_texts
from roost.config import Config
from roost.constants import CU_APPROVED_CARDS_MAX
from roost.crypto.encryption import decrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.talk.link_scope import HOST_PREFIX, named_site_entries
from roost.talk.new_site import open_card_host, url_host

logger = logging.getLogger(__name__)

NEW_SITE = "new_site"


def _new_site_hosts(steps_text: str) -> Iterable[str]:
    """A new-site card's host: a click's link (its frozen resolution) or an Open card's address."""
    for step in steps_from_json(steps_text):
        host = (step.act or {}).get("nav_host") if step.floor == NEW_SITE else None
        host = host or open_card_host(step)
        if isinstance(host, str) and host:
            yield host


async def approved_site_hosts(config: Config, user_id: str, thread_id: str) -> tuple[str, ...]:
    """The hosts of the new-site cards you approved in this chat (newest ``CU_APPROVED_CARDS_MAX`` cards)."""
    async with db_session(config) as db:
        rows = await (await db.execute(
            "SELECT steps FROM approval_cards WHERE user_id = ? AND thread_id = ? AND state = 'approved' "
            "ORDER BY created_at DESC LIMIT ?", (user_id, thread_id, CU_APPROVED_CARDS_MAX))).fetchall()
    if not rows:
        return ()
    dek = await get_user_dek(config, user_id)
    aad = user_aad(user_id, "approval_cards:steps")
    return tuple(host for row in rows for host in _new_site_hosts(decrypt_field(row["steps"], dek, aad, fallback="[]") or "[]"))


async def routine_named_hosts(config: Config, user_id: str, thread_id: str) -> tuple[str, ...]:
    """Owner, 2026-11-04: the well-known sites a routine's own instructions name ("Open WhatsApp Web") join its run
    log's fence, as they join its link scope (``turn._routine_named_sites``); only ``NAMED_SITES`` words count, never
    an address in them, and never a routine line a bot wrote. An address or domain they name counts too once the bot
    opened that site from your own chat (``routine_sites``, owner 2026-11-05)."""
    bodies = await _routine_bodies(config, user_id, thread_id)
    entries = (entry for body in bodies for entry in named_site_entries(body))
    named = tuple(dict.fromkeys(entry.removeprefix(HOST_PREFIX) for entry in entries))
    return (*named, *await _chat_opened(config, user_id, thread_id, bodies))


async def routine_chat_sites(config: Config, user_id: str, thread_id: str) -> tuple[str, ...]:
    """Owner, 2026-11-05: the sites this run log's routine names that its bot opened from your own chat; they join
    the routine run's link scope too, so opening them needs no Open card."""
    return await _chat_opened(config, user_id, thread_id, await _routine_bodies(config, user_id, thread_id))


async def _routine_bodies(config: Config, user_id: str, thread_id: str) -> tuple[str, ...]:
    """The newest routine lines in this run log that no bot wrote."""
    async with db_session(config) as db:
        rows = await (await db.execute(
            "SELECT body FROM messages WHERE user_id = ? AND thread_id = ? AND role = 'user' AND kind = 'routine' "
            "AND author_bot_id IS NULL ORDER BY seq DESC LIMIT ?",
            (user_id, thread_id, CU_APPROVED_CARDS_MAX))).fetchall()
    if not rows:
        return ()
    dek = await get_user_dek(config, user_id)
    aad = user_aad(user_id, "messages:body")
    return tuple(decrypt_field(row["body"], dek, aad, fallback="") or "" for row in rows)


async def _chat_opened(config: Config, user_id: str, thread_id: str, bodies: tuple[str, ...]) -> tuple[str, ...]:
    """The sites ``bodies`` name that the run log's bot opened from your own chat (``routine_sites``)."""
    if not bodies:
        return ()
    async with db_session(config) as db:
        row = await (await db.execute(
            "SELECT bot_id FROM threads WHERE user_id = ? AND id = ?", (user_id, thread_id))).fetchone()
    return await routine_chat_hosts(config, user_id, row["bot_id"], bodies) if row and row["bot_id"] else ()


async def routine_watch_hosts(config: Config, user_id: str, thread_id: str) -> tuple[str, ...]:
    """Owner, 2026-11-04: the page a routine watches joins its run log's fence (the owner typed it, or a clean run of
    the owner's own chat set it, and it passed ``askable_url``; never a page's link)."""
    async with db_session(config) as db:
        rows = await (await db.execute(
            "SELECT watch_url FROM routines WHERE user_id = ? AND thread_id = ? AND watch_every_min IS NOT NULL",
            (user_id, thread_id))).fetchall()
    if not rows:
        return ()
    dek = await get_user_dek(config, user_id)
    aad = user_aad(user_id, "routines:watch_url")
    urls = (decrypt_field(row["watch_url"], dek, aad, fallback="") or "" for row in rows)
    return tuple(host for url in urls if (host := url_host(url)))


def widened(fence: SiteFence, sites: Iterable[str]) -> SiteFence:
    """W6: the fence with the sites a fresh run of your own chat opened itself (never a page's)."""
    for site in sites:
        fence = fence.with_host(site)
    return fence


async def chat_fence(config: Config, user_id: str, thread_id: str | None) -> SiteFence:
    """This chat's fence; a run with no chat has an empty one (every link asks, or is never outside cards)."""
    if thread_id is None:
        return SiteFence(frozenset())
    texts = await load_approved_texts(config, user_id, thread_id, ())
    approved = (*await approved_site_hosts(config, user_id, thread_id),
                *await routine_named_hosts(config, user_id, thread_id),
                *await routine_watch_hosts(config, user_id, thread_id))
    return fence_from(texts.messages, approved)
