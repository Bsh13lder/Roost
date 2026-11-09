"""A package name the gateway accepts: Debian's rule, and never on the deny list."""

from __future__ import annotations

import fnmatch
import hashlib
import hmac
import re

from roost.apps.constants import APP_DENIED_PATTERNS, APP_IMAGE_PACKAGES, APP_NAME_PATTERN
from roost.apps.texts import BAD_NAME, BUILT_IN, DENIED

_NAME = re.compile(APP_NAME_PATTERN)
_KEY_LABEL = b"roost:bot-app:v1"


def valid_name(name: object) -> bool:
    return isinstance(name, str) and _NAME.fullmatch(name) is not None


def is_denied(name: str) -> bool:
    return name in APP_IMAGE_PACKAGES or any(fnmatch.fnmatchcase(name, p) for p in APP_DENIED_PATTERNS)


def package_refusal(name: object) -> str | None:
    """None for a name that may be asked for, else the sentence the bot is told."""
    if not isinstance(name, str) or not valid_name(name):
        return BAD_NAME
    if name in APP_IMAGE_PACKAGES:
        return BUILT_IN.format(package=name)
    return DENIED.format(package=name) if is_denied(name) else None


def package_key(dek: bytes, name: str) -> str:
    """A keyed HMAC of the name (a sub-key of the DEK), so the database never holds the name in plaintext."""
    sub = hmac.new(dek, _KEY_LABEL, hashlib.sha256).digest()
    return hmac.new(sub, name.encode("utf-8"), hashlib.sha256).hexdigest()
