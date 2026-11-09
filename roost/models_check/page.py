"""Reading Anthropic's public models page: which API model ids it lists, and which of them are news.

Only the page's own "Claude API" ids count. Bedrock (``anthropic.…-v1:0``) and Vertex (``…@date``)
spellings are skipped, and so are models older than the ones bots can already pick, and Haiku
(background jobs only), so a long "legacy models" table never shows up as a new model."""

from __future__ import annotations

import re

from roost.llm.registry import BOT_MODELS, KNOWN_MODEL_IDS

_API_ID = re.compile(r"(?<![\w.@:/-])claude-[a-z0-9]+(?:-[a-z0-9]+)*(?![\w@:-]|\.\w)")
_DATE_DIGITS = 8   # a trailing 20251001
_BACKGROUND_FAMILY = "haiku"


def parse_model_ids(html: str) -> tuple[str, ...]:
    """Every distinct API model id on the page, in page order."""
    return tuple(dict.fromkeys(match.group(0) for match in _API_ID.finditer(html)))


def _parts(model_id: str) -> tuple[str, tuple[int, ...]]:
    """The family word and the version numbers after it: a Sonnet 5.5 id gives ``("sonnet", (5, 5))``."""
    words = model_id.split("-")[1:]
    family = next((word for word in words if not word.isdigit()), "")
    after = words[words.index(family) + 1:] if family else []
    numbers = tuple(int(word) for word in after if word.isdigit() and len(word) < _DATE_DIGITS)
    return family, numbers


def label_for(model_id: str) -> str:
    """An Opus 6 id reads as "Opus 6"; a Sonnet 5.5 id as "Sonnet 5.5"."""
    family, numbers = _parts(model_id)
    if not family:
        return model_id
    return " ".join(part for part in (family.capitalize(), ".".join(map(str, numbers))) if part)


def _oldest_pickable() -> tuple[int, ...]:
    return min(_parts(choice.id)[1] for choice in BOT_MODELS)


def is_news(model_id: str) -> bool:
    """A model this app doesn't know yet that is at least as recent as the ones bots can pick."""
    if model_id in KNOWN_MODEL_IDS:
        return False
    family, numbers = _parts(model_id)
    return bool(family) and family != _BACKGROUND_FAMILY and numbers >= _oldest_pickable()
