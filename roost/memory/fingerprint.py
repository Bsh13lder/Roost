"""A keyed fingerprint of a memory's kind and text, so a repeat is found without storing plaintext."""

from __future__ import annotations

import hashlib
import hmac
import re

from roost.notes.text import fold

_KEY_LABEL = b"roost:memory-fingerprint:v1"
_SPACES = re.compile(r"\s+")
_TRAILING = ".!?"


def memory_key(dek: bytes) -> bytes:
    """A sub-key derived from the DEK, so the fingerprint never reuses the DEK itself."""
    return hmac.new(dek, _KEY_LABEL, hashlib.sha256).digest()


def normalise(text: str) -> str:
    """fold() (roost/notes/text.py), whitespace collapsed to one space, stripped, trailing . ! ? removed."""
    return _SPACES.sub(" ", fold(text)).strip().rstrip(_TRAILING).strip()


def fingerprint(dek: bytes, kind: str, text: str) -> str:
    return hmac.new(memory_key(dek), f"{kind}\n{normalise(text)}".encode("utf-8"), hashlib.sha256).hexdigest()
