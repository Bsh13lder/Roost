"""Sites a routine names that its bot already opened from your own chat (owner, 2026-11-05: "I let him open it
yesterday"; Gela opened Wizz Air in your chat at night, then her 09:00 one-time check asked to open it again).

A site joins the routine run log's fence only when both hold: the routine's own instructions name it (an address or a
bare domain, in a routine line no bot wrote), and the audit shows the same bot opening it in a run of your own chat
(``ROUTINE_CHAT_SITE_REASONS``) within ``ROUTINE_CHAT_SITE_DAYS``. A page can't put a site there: it can't write your
chat's opens. Every query names ``user_id``."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable

from roost.config import Config
from roost.constants import ROUTINE_CHAT_SITE_DAYS, ROUTINE_CHAT_SITE_REASONS, ROUTINE_CHAT_SITE_ROWS
from roost.crypto.encryption import decrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.talk.link_scope import HOST_PREFIX, bare_entries_in, urls_in
from roost.talk.new_site import url_host

logger = logging.getLogger(__name__)


def _bare(host: str) -> str:
    host = host.lower()
    return host[4:] if host.startswith("www.") else host


def _same_site(a: str, b: str) -> bool:
    """One is the other, its ``www.`` or a subdomain of it."""
    a, b = _bare(a), _bare(b)
    return a == b or a.endswith(f".{b}") or b.endswith(f".{a}")


def named_hosts(text: str) -> tuple[str, ...]:
    """The hosts of the addresses and bare domains in ``text``."""
    entries = (*urls_in(text), *bare_entries_in(text))
    hosts = (e.removeprefix(HOST_PREFIX) if e.startswith(HOST_PREFIX) else url_host(e) or "" for e in entries)
    return tuple(dict.fromkeys(host for host in hosts if host))


def matched_hosts(named: Iterable[str], opened: Iterable[str]) -> tuple[str, ...]:
    """Every named host and opened host that share a site, in both spellings, so ``www.`` and bare both pass."""
    named, opened = tuple(named), tuple(opened)
    pairs = ((n, o) for n in named for o in opened if _same_site(n, o))
    return tuple(dict.fromkeys(host for pair in pairs for host in pair))


async def chat_opened_hosts(config: Config, user_id: str, bot_id: str) -> tuple[str, ...]:
    """The hosts this bot opened lately in runs of your own chat, newest first."""
    since = (datetime.now(timezone.utc) - timedelta(days=ROUTINE_CHAT_SITE_DAYS)).isoformat()
    marks = ",".join("?" for _ in ROUTINE_CHAT_SITE_REASONS)
    async with db_session(config) as db:
        rows = await (await db.execute(
            "SELECT detail FROM audit WHERE user_id = ? AND bot_id = ? AND action = 'open_page' AND decision = 'do' "
            f"AND reason IN ({marks}) AND created_at > ? ORDER BY id DESC LIMIT ?",
            (user_id, bot_id, *ROUTINE_CHAT_SITE_REASONS, since, ROUTINE_CHAT_SITE_ROWS))).fetchall()
    if not rows:
        return ()
    dek = await get_user_dek(config, user_id)
    aad = user_aad(user_id, "audit:detail")
    hosts = (_detail_host(decrypt_field(row["detail"], dek, aad, fallback="") or "") for row in rows)
    return tuple(dict.fromkeys(host for host in hosts if host))


def _detail_host(detail: str) -> str:
    try:
        url = json.loads(detail).get("url", "")
    except (ValueError, AttributeError):
        logger.warning("An audit row's detail could not be read for a routine's sites")
        return ""
    return url_host(url) or "" if isinstance(url, str) else ""


async def routine_chat_hosts(config: Config, user_id: str, bot_id: str, bodies: Iterable[str]) -> tuple[str, ...]:
    """The sites the routine lines ``bodies`` name that ``bot_id`` opened from your own chat."""
    named = tuple(dict.fromkeys(host for body in bodies for host in named_hosts(body)))
    if not named:
        return ()
    return matched_hosts(named, await chat_opened_hosts(config, user_id, bot_id))
