"""Connector shapes: the stored connector (never with its key), the user's draft and patch, and how an error
becomes one plain sentence (never the input, which may hold the key)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from roost.bots.limits import fits_on_one_line
from roost.connectors import texts
from roost.connectors.address import AddressRefused, check_base_url, check_prefix
from roost.constants import (
    CONNECTOR_HINT_CHARS, CONNECTOR_HINT_MIN_SECRET, CONNECTOR_NAME_MAX, CONNECTOR_PREFIXES_MAX,
    CONNECTOR_PURPOSE_MAX, CONNECTOR_SECRET_MAX, CONNECTOR_DEFAULT_BEARER_HEADER,
)

AuthStyle = Literal["bearer", "header", "query"]
_AUTH_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_FORBIDDEN_HEADERS = frozenset({"host", "content-length", "content-type", "transfer-encoding", "connection",
                                "cookie", "accept", "upgrade", "te", "trailer", "proxy-authorization"})
_PYDANTIC_PREFIX = "Value error, "
_OUR_SENTENCES = frozenset(v for k, v in vars(texts).items() if k.isupper() and isinstance(v, str))


@dataclass(frozen=True)
class Connector:
    """A connector as Roost shows it. The key is never on this object: ``ConnectorStore.secret_of`` reads it."""
    id: str
    user_id: str
    name: str
    purpose: str
    base_url: str
    host: str
    auth_style: AuthStyle
    auth_name: str
    key_hint: str
    allowed_prefixes: tuple[str, ...]
    bot_ids: tuple[str, ...] | None     # None: every bot
    created_at: str
    updated_at: str

    def usable_by(self, bot_id: str) -> bool:
        return self.bot_ids is None or bot_id in self.bot_ids


def key_hint(secret: str) -> str:
    """What the user sees of a saved key."""
    if len(secret) >= CONNECTOR_HINT_MIN_SECRET:
        return f"key set ••••{secret[-CONNECTOR_HINT_CHARS:]}"
    return "key set"


def check_secret(value: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > CONNECTOR_SECRET_MAX
            or any(ch.isspace() or not ch.isprintable() for ch in value)):
        raise ValueError(texts.BAD_SECRET)
    return value


def check_name(value: str) -> str:
    text = value.strip()
    if not text or len(text) > CONNECTOR_NAME_MAX or not fits_on_one_line(text):
        raise ValueError(texts.BAD_NAME)
    return text


def _check_purpose(value: str) -> str:
    text = value.strip()
    if len(text) > CONNECTOR_PURPOSE_MAX:
        raise ValueError(texts.BAD_PURPOSE)
    return text


def _check_base(value: str) -> str:
    try:
        return check_base_url(value).url
    except AddressRefused as exc:
        raise ValueError(exc.text) from None


def _check_prefixes(value: tuple[str, ...]) -> tuple[str, ...]:
    if len(value) > CONNECTOR_PREFIXES_MAX:
        raise ValueError(texts.TOO_MANY_PREFIXES)
    try:
        return tuple(dict.fromkeys(check_prefix(p.strip()) for p in value))
    except AddressRefused:
        raise ValueError(texts.BAD_PREFIX) from None


def check_auth_name(style: str, name: str | None) -> str:
    """The header or parameter name for ``style`` (a Bearer key defaults to ``Authorization``)."""
    chosen = (name or "").strip() or (CONNECTOR_DEFAULT_BEARER_HEADER if style == "bearer" else "")
    if not _AUTH_NAME.match(chosen) or (style != "query" and chosen.lower() in _FORBIDDEN_HEADERS):
        raise ValueError(texts.BAD_AUTH_NAME)
    if style != "query" and not re.fullmatch(r"[A-Za-z0-9-]+", chosen):
        raise ValueError(texts.BAD_AUTH_NAME)
    return chosen


class _Fields(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("name", check_fields=False)
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return None if v is None else check_name(v)

    @field_validator("purpose", check_fields=False)
    @classmethod
    def _purpose(cls, v: str | None) -> str | None:
        return None if v is None else _check_purpose(v)

    @field_validator("base_url", check_fields=False)
    @classmethod
    def _base(cls, v: str | None) -> str | None:
        return None if v is None else _check_base(v)

    @field_validator("secret", check_fields=False)
    @classmethod
    def _secret(cls, v: str | None) -> str | None:
        return None if v is None else check_secret(v)

    @field_validator("allowed_prefixes", check_fields=False)
    @classmethod
    def _prefixes(cls, v: tuple[str, ...] | None) -> tuple[str, ...] | None:
        return None if v is None else _check_prefixes(v)


class ConnectorDraft(_Fields):
    """A new connector, as the user (or an Add a key card) gives it."""
    name: str
    purpose: str = ""
    base_url: str
    auth_style: AuthStyle = "bearer"
    auth_name: str | None = None
    secret: str = Field(repr=False)
    allowed_prefixes: tuple[str, ...] = ()
    bot_ids: tuple[str, ...] | None = None


class ConnectorPatch(_Fields):
    """A change; ``None`` keeps a field. ``all_bots`` true sets ``bot_ids`` back to every bot."""
    name: str | None = None
    purpose: str | None = None
    base_url: str | None = None
    auth_style: AuthStyle | None = None
    auth_name: str | None = None
    secret: str | None = Field(default=None, repr=False)
    allowed_prefixes: tuple[str, ...] | None = None
    bot_ids: tuple[str, ...] | None = None
    all_bots: bool = False


def plain_error(exc: ValidationError) -> str:
    """The first problem as one plain sentence; anything not ours is the generic sentence (never the input)."""
    first = exc.errors(include_input=False, include_url=False)[0]
    message = str(first.get("msg", "")).removeprefix(_PYDANTIC_PREFIX)
    if message in _OUR_SENTENCES:
        return message
    field = first.get("loc", ("",))[0]
    return {"auth_style": texts.BAD_STYLE, "secret": texts.NEEDS_SECRET if first.get("type") == "missing"
            else texts.BAD_SECRET}.get(str(field), texts.BAD_BODY)
