"""The hearing context (docs/plans/2026-11-06-roost-voice-tuning.md D1): the names and site names the hearing model
and the correction read before they write, built per user and bot from words the owner wrote or chose and nothing
else — the bots' names, proper nouns in the owner's own untainted memories and own recent messages in that bot's
chat, the hosts in Vault: site logins as site names (never a login's label), and the fixed ``COMMON_SITE_NAMES``.
Never a bot's reply, a web page, a tainted memory, an address or a number: ``clean_term`` drops those too.

``HearHints.for_bot`` is the one door: it reads the stores once per (user, bot) every ``VOICE_CONTEXT_CACHE_S`` (the
live partials ask every second) and returns a frozen ``HearHint`` with the bot's chosen language."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from roost.voice.constants import (
    COMMON_SITE_NAMES,
    VOICE_CONTEXT_CACHE_S,
    VOICE_CONTEXT_MEMORY_TERMS_MAX,
    VOICE_CONTEXT_RECENT_MESSAGES,
    VOICE_LANGUAGE_AUTO,
    VOICE_LANGUAGE_BY_ID,
)
from roost.voice.envelope import HearHint, bounded_terms

_WORD = re.compile(r"[^\W\d_][\w'’-]*", re.UNICODE)
_SENTENCE_END = re.compile(r"[.!?…\n]+")
_SHORT_CAPS_MIN, _SHORT_CAPS_MAX = 2, 6
_RUN_MAX = 3
# Hosts' front labels that say nothing about the site.
_HOST_PREFIXES = frozenset({"www", "web", "m", "mail", "app", "accounts", "login", "my", "api", "en", "es"})
_SECOND_LEVEL = frozenset({"co", "com", "org", "net", "gov", "edu", "ac"})
# A site's name as people say it, by the host's main label; anything else is the label capitalised.
KNOWN_SITES: Mapping[str, str] = MappingProxyType({
    name.lower().replace(" ", ""): name for name in COMMON_SITE_NAMES
} | {"whatsapp": "WhatsApp", "youtube": "YouTube", "linkedin": "LinkedIn", "github": "GitHub", "paypal": "PayPal",
     "tiktok": "TikTok", "gmail": "Gmail", "meet": "Google Meet", "drive": "Google Drive", "x": "X",
     "twitter": "Twitter", "bbva": "BBVA", "ing": "ING", "alsa": "ALSA", "renfe": "Renfe"})


def _is_cap(word: str) -> bool:
    return word[0].isupper()


def _is_short_caps(word: str) -> bool:
    return word.isupper() and _SHORT_CAPS_MIN <= len(word) <= _SHORT_CAPS_MAX


def _runs(words: list[str]) -> Iterable[tuple[int, int]]:
    """The spans of two or more capitalised words in a row: a name like "Maka Eremadze", anywhere in the sentence.
    A run that opens the sentence and is three words or longer loses its first word (a verb: "Ask Tamar
    Kiknadze"); a two-word one is kept whole ("Nino Beridze called")."""
    start = None
    for at, word in enumerate([*words, ""]):
        if word and _is_cap(word):
            start = at if start is None else start
            continue
        if start is not None and at - start >= 2:
            first = start + 1 if start == 0 and at - start >= 3 else start
            yield first, min(at, first + _RUN_MAX)
        start = None


def _sentence_nouns(sentence: str) -> Iterable[str]:
    words = _WORD.findall(sentence)
    covered: set[int] = set()
    for first, end in _runs(words):
        covered.update(range(first, end))
        yield " ".join(words[first:end])
    for at, word in enumerate(words):
        if at not in covered and ((at > 0 and _is_cap(word)) or _is_short_caps(word)):
            yield word


def proper_nouns(text: str) -> tuple[str, ...]:
    """The words in ``text`` that look like names: runs of two or three capitalised words, a capitalised word that
    does not open its sentence, and a short all-caps word (ALSA, BBVA) anywhere. In order of first sight, without
    repeats. Scripts with no case (Georgian) give nothing here."""
    found: list[str] = []
    seen: set[str] = set()
    for sentence in _SENTENCE_END.split(text):
        for term in _sentence_nouns(sentence):
            if term.casefold() not in seen:
                seen.add(term.casefold())
                found.append(term)
    return tuple(found)


def site_name(host: str) -> str | None:
    """A host as a site people name: ``web.whatsapp.com`` → ``WhatsApp``, ``upwork.com`` → ``Upwork``; ``None``
    for a host with no name in it (an address, a bare label)."""
    labels = [label for label in host.lower().strip().strip(".").split(".") if label]
    while labels and labels[0] in _HOST_PREFIXES:
        labels = labels[1:]
    if len(labels) < 2:
        return None
    main = labels[-2]
    if main in _SECOND_LEVEL and len(labels) >= 3:
        main = labels[-3]
    if not main.isalpha():
        return None
    return KNOWN_SITES.get(main, main.capitalize())


class _Bots(Protocol):
    async def list(self, user_id: str) -> list[Any]: ...

    async def get(self, user_id: str, bot_id: str) -> Any: ...


class _Memories(Protocol):
    async def list_for_bot(self, user_id: str, bot_id: str, **kwargs: Any) -> tuple[Any, ...]: ...


class _Talk(Protocol):
    async def main_thread(self, user_id: str, bot_id: str) -> Any: ...

    async def list_latest_messages(self, user_id: str, thread_id: str, limit: int | None = None,
                                   **kwargs: Any) -> list[Any]: ...


class _Vault(Protocol):
    async def list_all(self, user_id: str, limit: int = ...) -> tuple[Any, ...]: ...


def asr_language(code: str | None) -> str | None:
    """The hearing model's own name for a bot's chosen language; ``None`` for auto-detect or no bot."""
    if code is None or code == VOICE_LANGUAGE_AUTO:
        return None
    lang = VOICE_LANGUAGE_BY_ID.get(code)
    return None if lang is None else lang.asr


class HearHints:
    def __init__(self, bots: _Bots, memories: _Memories, talk: _Talk, vault: _Vault,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._bots, self._memories, self._talk, self._vault = bots, memories, talk, vault
        self._clock = clock
        self._kept: Mapping[tuple[str, str | None], tuple[float, HearHint]] = MappingProxyType({})

    def forget(self) -> None:
        """Drop every remembered hint (a test, or a change the next hint should see at once)."""
        self._kept = MappingProxyType({})

    async def for_bot(self, user_id: str, bot_id: str | None, *, partial: bool = False) -> HearHint:
        """The hint for a recording spoken to ``bot_id`` (or to no bot in particular), remembered for
        ``VOICE_CONTEXT_CACHE_S``; ``partial`` only marks the hint."""
        key = (user_id, bot_id)
        now = self._clock()
        found = self._kept.get(key)
        if found is None or now - found[0] >= VOICE_CONTEXT_CACHE_S:
            hint = await self._build(user_id, bot_id)
            self._kept = MappingProxyType({**self._kept, key: (now, hint)})
        else:
            hint = found[1]
        return HearHint(terms=hint.terms, language=hint.language, partial=partial)

    async def _build(self, user_id: str, bot_id: str | None) -> HearHint:
        bots = await self._bots.list(user_id)
        language = None
        if bot_id is not None:
            bot = next((b for b in bots if b.id == bot_id), None)
            language = asr_language(bot.voice.language) if bot is not None else None
        terms = [*(bot.name for bot in bots), *await self._vault_sites(user_id), *await self._recent(user_id, bot_id),
                 *await self._memory_nouns(user_id, bot_id), *COMMON_SITE_NAMES]
        return HearHint(terms=bounded_terms(terms), language=language)

    async def _vault_sites(self, user_id: str) -> list[str]:
        names = (site_name(login.host) for login in await self._vault.list_all(user_id))
        return [name for name in names if name]

    async def _recent(self, user_id: str, bot_id: str | None) -> list[str]:
        """Proper nouns in the owner's own newest messages in the bot's chat (never the bot's replies)."""
        if bot_id is None:
            return []
        thread = await self._talk.main_thread(user_id, bot_id)
        if thread is None:
            return []
        messages = await self._talk.list_latest_messages(user_id, thread.id, VOICE_CONTEXT_RECENT_MESSAGES)
        own = "\n".join(m.body for m in messages if m.role == "user" and m.kind == "text")
        return list(proper_nouns(own))

    async def _memory_nouns(self, user_id: str, bot_id: str | None) -> list[str]:
        """Proper nouns in the owner's untainted memories (About you and the bot's)."""
        memories = await self._memories.list_for_bot(user_id, bot_id or "")
        text = "\n".join(m.text for m in memories if not m.tainted)
        return list(proper_nouns(text))[:VOICE_CONTEXT_MEMORY_TERMS_MAX]
