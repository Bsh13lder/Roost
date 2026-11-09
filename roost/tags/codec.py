"""A record's tags as one sealed JSON list (``enc:v2``); no tags is ``NULL``."""

from __future__ import annotations

import json
from typing import Iterable

from roost.crypto.encryption import decrypt_field, encrypt_field


def seal_tags(tags: Iterable[str], dek: bytes, aad: bytes) -> str | None:
    listed = list(tags)
    return encrypt_field(json.dumps(listed), dek, aad) if listed else None


def open_tags(raw: str | None, dek: bytes, aad: bytes) -> tuple[str, ...]:
    """The tags, or ``()`` for ``NULL`` or for a sealed value that is not a JSON list of strings."""
    if raw is None:
        return ()
    text = decrypt_field(raw, dek, aad)
    try:
        parsed = json.loads(text or "[]")
    except json.JSONDecodeError:
        return ()
    return tuple(item for item in parsed if isinstance(item, str)) if isinstance(parsed, list) else ()
