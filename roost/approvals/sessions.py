"""``SessionOks``: "Yes for this session" on a read, in memory only.

A live OK lets one bot read one folder without a card for ``MAC_SESSION_MINUTES``. It ends when the
grant is revoked, when the bot goes off duty, when the time is up or when the process restarts. The gate
never uses it in a tainted run."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from roost.constants import MAC_SESSION_MINUTES


@dataclass(frozen=True)
class _Ok:
    user_id: str
    bot_id: str
    grant_id: str
    label: str            # casefolded
    expires_at: float


class SessionOks:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._oks: tuple[_Ok, ...] = ()

    def grant(self, user_id: str, bot_id: str, grant_id: str, label: str) -> None:
        """Start (or renew) the OK for this bot and grant."""
        kept = tuple(o for o in self._live() if not (o.user_id == user_id and o.bot_id == bot_id
                                                     and o.grant_id == grant_id))
        self._oks = (*kept, _Ok(user_id, bot_id, grant_id, label.casefold(),
                                self._clock() + MAC_SESSION_MINUTES * 60))

    def folders(self, user_id: str, bot_id: str) -> frozenset[str]:
        """The casefolded labels this bot may read without asking right now."""
        return frozenset(o.label for o in self._live() if o.user_id == user_id and o.bot_id == bot_id)

    def end_for_grant(self, user_id: str, grant_id: str) -> None:
        self._oks = tuple(o for o in self._live() if not (o.user_id == user_id and o.grant_id == grant_id))

    def end_for_bot(self, user_id: str, bot_id: str) -> None:
        self._oks = tuple(o for o in self._live() if not (o.user_id == user_id and o.bot_id == bot_id))

    def _live(self) -> tuple[_Ok, ...]:
        now = self._clock()
        return tuple(o for o in self._oks if o.expires_at > now)
