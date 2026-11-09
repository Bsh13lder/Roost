"""The token usage API's bodies, built from ``UsageRow``s (all pure): dense per-day rows oldest first, totals, today,
each bot busiest first, the background bucket and the busiest bot. The server reckons every sum; the web and the
phone only show them."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable, Mapping

from roost.constants import USAGE_RETIRED_BOT_NAME
from roost.usage.counts import UsageTotals
from roost.usage.store import UsageRow


def window(today: str, days: int) -> tuple[str, ...]:
    """The ``days`` local days ending ``today``, oldest first."""
    end = date.fromisoformat(today)
    return tuple((end - timedelta(days=n)).isoformat() for n in range(days - 1, -1, -1))


def _sum(rows: Iterable[UsageRow]) -> UsageTotals:
    total = UsageTotals()
    for row in rows:
        total = total.plus(row.totals)
    return total


def _series(rows: tuple[UsageRow, ...], days: tuple[str, ...], today: str) -> dict[str, Any]:
    """A group's total, today's total and one row per day of the window."""
    per_day = [{"day": day, **_sum(r for r in rows if r.day == day).as_dict()} for day in days]
    return {"total": _sum(rows).as_dict(), "today_total": _sum(r for r in rows if r.day == today).as_dict(),
            "per_day": per_day}


def bot_report(bot_id: str, rows: tuple[UsageRow, ...], *, today: str, days: int) -> dict[str, Any]:
    span = window(today, days)
    kept = tuple(r for r in rows if r.day in span and r.bot_id == bot_id)
    return {"bot_id": bot_id, "days": days, "today": today, **_series(kept, span, today)}


def _bots(rows: tuple[UsageRow, ...], span: tuple[str, ...], today: str,
          names: Mapping[str, str]) -> list[dict[str, Any]]:
    ids = sorted({r.bot_id for r in rows if r.bot_id is not None})
    bots = [{"bot_id": bot_id, "name": names.get(bot_id, USAGE_RETIRED_BOT_NAME),
             **_series(tuple(r for r in rows if r.bot_id == bot_id), span, today)} for bot_id in ids]
    return sorted(bots, key=lambda b: (-b["total"]["tokens"], b["name"]))


def user_report(rows: tuple[UsageRow, ...], *, today: str, days: int, names: Mapping[str, str]) -> dict[str, Any]:
    """Everything for ``GET /api/usage``: ``names`` maps the user's bot ids to their names (a missing id is a
    retired bot)."""
    span = window(today, days)
    kept = tuple(r for r in rows if r.day in span)
    bots = _bots(kept, span, today, names)
    busiest = next(({"bot_id": b["bot_id"], "name": b["name"], "tokens": b["total"]["tokens"]}
                    for b in bots if b["total"]["tokens"] > 0), None)
    return {"days": days, "today": today, **_series(kept, span, today), "bots": bots,
            "background": _series(tuple(r for r in kept if r.bot_id is None), span, today), "busiest": busiest}
