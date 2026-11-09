"""The tag rules for everything a bot writes (obsidian track, part 1). Pure: no I/O.

A bot's new record carries ``bot:<slug>``, ``project:<slug>`` when it is linked to a project, and up to
``MAX_BOT_TOPIC_TAGS`` topic tags the bot gives. A topic tag is one word (``a-z 0-9 _ - /``, a leading
``#`` dropped, folded to lower case); anything else is refused with a plain sentence, never guessed at.
Obsidian tags cannot hold ``:``, so ``obsidian_tag`` writes ``bot:ana`` as ``bot/ana``."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

from roost.constants import (
    BOT_TAG_PREFIX, MAX_BOT_TOPIC_TAGS, PROJECT_TAG_PREFIX, TAG_SLUG_MAX_CHARS, TOPIC_TAG_MAX_CHARS,
)

# No apostrophes: the tools path escapes these sentences for the model.
BAD_TAG_TEXT = (f"A tag is one word: letters, digits, _ - or /, up to {TOPIC_TAG_MAX_CHARS} characters, "
                "like home or garden/roses.")
TOO_MANY_TAGS_TEXT = f"Give at most {MAX_BOT_TOPIC_TAGS} tags."
# The ``tags`` argument every bot tool that writes a record takes.
TOPIC_TAGS_SCHEMA: dict[str, Any] = {
    "type": "array", "items": {"type": "string"},
    "description": f"Up to {MAX_BOT_TOPIC_TAGS} one-word topic tags, like home or garden/roses.",
}
_TOPIC = re.compile(r"[a-z0-9][a-z0-9_/-]*")
_NOT_SLUG = re.compile(r"[^a-z0-9]+")
_NOT_OBSIDIAN = re.compile(r"[^a-z0-9_/-]+")
_SYSTEM_PREFIXES = (f"{BOT_TAG_PREFIX}:", f"{PROJECT_TAG_PREFIX}:")
_UNTITLED = "untitled"
_BOT_ID_CHARS = 8


def _ascii_lower(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()


def slug(text: str) -> str:
    """``"Nota Bené: Café!"`` -> ``"nota-bene-cafe"``; never empty."""
    cut = _NOT_SLUG.sub("-", _ascii_lower(text)).strip("-")[:TAG_SLUG_MAX_CHARS].strip("-")
    return cut or _UNTITLED


def topic_tags(raw: Iterable[str]) -> tuple[str, ...]:
    """The bot's topic tags, checked. ``ValueError`` (a plain sentence) for a word that is not a tag or for
    more than ``MAX_BOT_TOPIC_TAGS``. Blank entries are skipped; a repeat counts once."""
    words: list[str] = []
    for item in raw:
        word = item.strip().lstrip("#").lower()
        if not word:
            continue
        if len(word) > TOPIC_TAG_MAX_CHARS or not _TOPIC.fullmatch(word):
            raise ValueError(BAD_TAG_TEXT)
        if word not in words:
            words.append(word)
    if len(words) > MAX_BOT_TOPIC_TAGS:
        raise ValueError(TOO_MANY_TAGS_TEXT)
    return tuple(words)


def bot_tag(bot_name: str | None, bot_id: str) -> str:
    """``bot:<slug of the name>``; without a name (a caller that knows only the id) the id's first part."""
    name = slug(bot_name) if bot_name and bot_name.strip() else bot_id[:_BOT_ID_CHARS].lower()
    return f"{BOT_TAG_PREFIX}:{name}"


def project_tag(project_name: str) -> str:
    return f"{PROJECT_TAG_PREFIX}:{slug(project_name)}"


def is_system_tag(tag: str) -> bool:
    return tag.startswith(_SYSTEM_PREFIXES)


def _unique(tags: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(tags))


def record_tags(*, bot_name: str | None, bot_id: str, project_name: str | None,
                topics: Iterable[str]) -> tuple[str, ...]:
    """A bot's new record's tags: the bot, the project (when linked), then its topic tags."""
    system = [bot_tag(bot_name, bot_id)]
    if project_name:
        system.append(project_tag(project_name))
    return _unique([*system, *topics])


def keep_system_tags(current: Iterable[str], topics: Iterable[str]) -> tuple[str, ...]:
    """A bot replacing a record's tags keeps the record's ``bot:`` and ``project:`` tags."""
    return _unique([*(t for t in current if is_system_tag(t)), *topics])


def obsidian_tag(tag: str) -> str | None:
    """The tag as Obsidian writes it (no ``:``, no spaces); ``None`` when nothing usable is left."""
    text = _ascii_lower(tag.strip().lstrip("#")).replace(":", "/")
    cleaned = _NOT_OBSIDIAN.sub("-", text).strip("-/")
    return cleaned or None
