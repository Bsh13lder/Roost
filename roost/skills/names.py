"""A skill's name, folded for uniqueness, and its keyed HMAC, so the database never holds the name in plaintext."""

from __future__ import annotations

import hashlib
import hmac

from roost.memory.fingerprint import normalise

_KEY_LABEL = b"roost:skill-name:v1"


def fold_name(name: str) -> str:
    """Case, accents and runs of spaces folded: "Pöst  on X" and "post on x" are one name."""
    return normalise(name)


def skill_key(dek: bytes) -> bytes:
    """A sub-key derived from the DEK, so the name key never reuses the DEK itself."""
    return hmac.new(dek, _KEY_LABEL, hashlib.sha256).digest()


def name_key(dek: bytes, name: str) -> str:
    return hmac.new(skill_key(dek), fold_name(name).encode("utf-8"), hashlib.sha256).hexdigest()
