"""Small readers shared by the mapping modules (pure)."""

from __future__ import annotations

import json

from roost.migrate.lazyclaw.models import Row
from roost.migrate.lazyclaw.values import ValueAnomaly, utc_stamp


def text(row: Row, key: str) -> str | None:
    value = row.get(key)
    return None if value is None else str(value)


def required(row: Row, key: str) -> str:
    value = text(row, key)
    if value is None or not value.strip():
        raise ValueAnomaly(f"{key} is empty.")
    return value


def choice(row: Row, key: str, allowed: frozenset[str]) -> str:
    value = text(row, key)
    if value not in allowed:
        raise ValueAnomaly(f"Unknown {key} value.")
    return str(value)


def stamps(row: Row, fallback: str) -> tuple[str, str]:
    """``(created_at, updated_at)`` as ISO UTC. A missing created_at takes ``fallback``;
    a missing updated_at takes created_at."""
    created = utc_stamp(text(row, "created_at")) or fallback
    return created, utc_stamp(text(row, "updated_at")) or created


def json_list(value: str | None, what: str) -> list:
    if value is None or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueAnomaly(f"{what} is not valid JSON.") from exc
    if not isinstance(parsed, list):
        raise ValueAnomaly(f"{what} is not a list.")
    return parsed
