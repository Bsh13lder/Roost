"""``TokenUsageStore``: the per-day token sums (schema v39 ``token_usage``).

One row per user, bot (``NULL`` for a job with no bot), local day, kind and model; ``add`` is one upsert that
adds a call's counts to its row, so two runs at once never lose a count. Every query names ``user_id``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import aiosqlite

from roost.config import RoostConfig
from roost.constants import USAGE_KINDS, USAGE_MODEL_MAX
from roost.db.connection import db_session
from roost.llm.types import Usage
from roost.usage.counts import UsageTotals
from roost.work.runs import madrid_today

Clock = Callable[[], datetime]

_UPSERT = (
    "INSERT INTO token_usage (user_id, bot_id, day, kind, model, input_tokens, output_tokens, cache_read_tokens, "
    "cache_write_tokens, calls, updated_at) VALUES (?,?,?,?,?,?,?,?,?,1,?) "
    "ON CONFLICT(user_id, IFNULL(bot_id, ''), day, kind, model) DO UPDATE SET "
    "input_tokens = input_tokens + excluded.input_tokens, output_tokens = output_tokens + excluded.output_tokens, "
    "cache_read_tokens = cache_read_tokens + excluded.cache_read_tokens, "
    "cache_write_tokens = cache_write_tokens + excluded.cache_write_tokens, calls = calls + 1, "
    "updated_at = excluded.updated_at"
)
_COLUMNS = ("day, bot_id, kind, model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, calls")


@dataclass(frozen=True)
class UsageRow:
    day: str
    bot_id: str | None
    kind: str
    model: str
    totals: UsageTotals


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _row(row: aiosqlite.Row) -> UsageRow:
    return UsageRow(day=row["day"], bot_id=row["bot_id"], kind=row["kind"], model=row["model"],
                    totals=UsageTotals(int(row["input_tokens"]), int(row["output_tokens"]),
                                       int(row["cache_read_tokens"]), int(row["cache_write_tokens"]),
                                       int(row["calls"])))


class TokenUsageStore:
    def __init__(self, config: RoostConfig, clock: Clock = _utc_now) -> None:
        self._config, self._clock = config, clock

    def today(self) -> str:
        return madrid_today(self._clock())

    async def add(self, user_id: str, bot_id: str | None, kind: str, model: str, usage: Usage) -> None:
        """Add one call's counts to today's row. ``ValueError`` for a kind Roost does not know."""
        if kind not in USAGE_KINDS:
            raise ValueError(f"unknown usage kind: {kind}")
        now = self._clock()
        async with db_session(self._config) as db:
            await db.execute(_UPSERT, (user_id, bot_id, madrid_today(now), kind, (model or "?")[:USAGE_MODEL_MAX],
                                       usage.input, usage.output, usage.cache_read, usage.cache_write,
                                       now.isoformat()))
            await db.commit()

    async def rows(self, user_id: str, *, since_day: str, bot_id: str | None = None) -> tuple[UsageRow, ...]:
        """This user's rows from ``since_day`` on (a local day), for one bot when ``bot_id`` is given."""
        extra, params = ("AND bot_id = ?", (bot_id,)) if bot_id is not None else ("", ())
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {_COLUMNS} FROM token_usage WHERE user_id = ? AND day >= ? {extra} "
                "ORDER BY day, bot_id, kind, model", (user_id, since_day, *params))).fetchall()
        return tuple(_row(row) for row in rows)
