"""Token counts: one call's ``Usage`` read from the SDK, and ``UsageTotals`` summed for the API (all pure).

The SDK's ``ResultMessage.usage`` is a plain dict from the CLI, so it is external data: each count must be a
non-negative int no larger than ``USAGE_COUNT_MAX`` or it reads as 0, and a dict with no count at all is ``None``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from roost.constants import USAGE_COUNT_MAX
from roost.llm.types import Usage

_SDK_KEYS = (("input", "input_tokens"), ("output", "output_tokens"), ("cache_read", "cache_read_input_tokens"),
             ("cache_write", "cache_creation_input_tokens"))


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value <= USAGE_COUNT_MAX else None


def usage_from_sdk(raw: Any) -> Usage | None:
    """The four counts of an SDK usage dict; ``None`` when it holds none."""
    if not isinstance(raw, dict):
        return None
    counts = {field: _count(raw.get(key)) for field, key in _SDK_KEYS}
    if all(value is None for value in counts.values()):
        return None
    return Usage(**{field: value or 0 for field, value in counts.items()})


@dataclass(frozen=True)
class UsageTotals:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    calls: int = 0

    @classmethod
    def of(cls, usage: Usage) -> "UsageTotals":
        return cls(usage.input, usage.output, usage.cache_read, usage.cache_write, 1)

    def plus(self, other: "UsageTotals") -> "UsageTotals":
        return UsageTotals(self.input + other.input, self.output + other.output, self.cache_read + other.cache_read,
                           self.cache_write + other.cache_write, self.calls + other.calls)

    @property
    def tokens_in(self) -> int:
        return self.input + self.cache_read + self.cache_write

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.output

    def as_dict(self) -> dict[str, int]:
        return {"input": self.input, "output": self.output, "cache_read": self.cache_read,
                "cache_write": self.cache_write, "calls": self.calls, "tokens_in": self.tokens_in,
                "tokens_out": self.output, "tokens": self.tokens}
