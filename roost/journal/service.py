"""``JournalService`` — the rules both doors share (the bot's tools and the routes) and the live frame.

An append adds one ``- HH:MM text`` line to today's local day, making the day on its first entry. A day is
at most ``JOURNAL_DAY_MAX_CHARS``; a lost compare-and-swap is tried again. A day written in a tainted run
stays tainted. The ``journal_changed`` frame carries the bot and the day, never the text."""

from __future__ import annotations

from datetime import date, datetime
from typing import Callable

from roost.constants import JOURNAL_DAY_MAX_CHARS, JOURNAL_RECENT_DAYS, JOURNAL_SCAN_DAYS, JOURNAL_SEARCH_LIMIT
from roost.constants import JOURNAL_WRITE_RETRIES
from roost.events.hub import EventHub
from roost.journal.markdown import add_entry, entry_text, matching_lines, new_day
from roost.journal.models import JournalDay, JournalHit
from roost.journal.store import JournalStore
from roost.notes.search import query_terms
from roost.timezones import local_tz

FULL_DAY_TEXT = "Today's journal is full; keep it for tomorrow."
BUSY_TEXT = "The journal was busy; try again."
NO_BOT_TEXT = "That bot is not one of yours."
_TIME_LABEL = "%H:%M"
_HIT_LINES = 3


def madrid_now() -> datetime:
    return datetime.now(local_tz())


class JournalService:
    def __init__(self, store: JournalStore, events: EventHub, *,
                 clock: Callable[[], datetime] = madrid_now) -> None:
        self._store = store
        self._events = events
        self._clock = clock

    def today(self) -> date:
        return self._clock().date()

    async def append(self, user_id: str, bot_id: str, bot_name: str, text: str, *,
                     tainted: bool = False) -> JournalDay:
        """``ValueError`` (a plain sentence): empty or long text, a full day, a bot that is not the user's."""
        now = self._clock()
        line = entry_text(text)
        for _ in range(JOURNAL_WRITE_RETRIES):
            current = await self._store.get(user_id, bot_id, now.date())
            saved = await self._write(user_id, bot_id, bot_name, current, now, line, tainted)
            if saved is not None:
                await self._events.publish(user_id, {"type": "journal_changed", "bot_id": bot_id,
                                                     "day": saved.day.isoformat()})
                return saved
        raise ValueError(BUSY_TEXT)

    async def _write(self, user_id: str, bot_id: str, bot_name: str, current: JournalDay | None, now: datetime,
                     line: str, tainted: bool) -> JournalDay | None:
        base = current.content if current is not None else new_day(bot_name, now.date())
        content = add_entry(base, now.strftime(_TIME_LABEL), line)
        if len(content) > JOURNAL_DAY_MAX_CHARS:
            raise ValueError(FULL_DAY_TEXT)
        if current is not None:
            return await self._store.swap(current, content, tainted=current.tainted or tainted)
        made = await self._store.insert(user_id, bot_id, now.date(), content, tainted=tainted)
        if made is None and await self._store.get(user_id, bot_id, now.date()) is None:
            raise ValueError(NO_BOT_TEXT)   # not a race: the bot is not this user's
        return made

    async def read(self, user_id: str, bot_id: str, day: date) -> JournalDay | None:
        return await self._store.get(user_id, bot_id, day)

    async def recent(self, user_id: str, bot_id: str, limit: int = JOURNAL_RECENT_DAYS) -> tuple[JournalDay, ...]:
        return await self._store.recent(user_id, bot_id, limit)

    async def search(self, user_id: str, query: str, *, bot_id: str | None = None,
                     limit: int = JOURNAL_SEARCH_LIMIT) -> tuple[JournalHit, ...]:
        """Days whose entries hold every word of ``query``, newest first. An empty query finds nothing."""
        terms = query_terms(query)
        if not terms:
            return ()
        hits: list[JournalHit] = []
        for day in await self._store.newest(user_id, JOURNAL_SCAN_DAYS, bot_id=bot_id):
            lines = matching_lines(day.content, terms)
            if lines:
                hits.append(JournalHit(bot_id=day.bot_id, day=day.day, lines=lines[:_HIT_LINES], tainted=day.tainted))
            if len(hits) >= limit:
                break
        return tuple(hits)
