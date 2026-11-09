"""Tasks shown as cards in the chat (owner, 2026-10-26: "when I ask task for it showed me beautiful").

``TaskTools`` notes the tasks a run added or listed; after the run, ``finish_run`` posts one quiet ``task_cards``
line (role ``activity``) under the bot's reply, so the chat draws them as task cards the user can tick and open.
Only a run of the user's own 1:1 chat collects them: never a routine, a handoff, a room, a helper or an approved
step with no run. The body is server-made: task ids only (at most ``TASK_CARDS_MAX``), ``verb`` ("added",
"listed", or "tasks" for both) and ``more`` (listed tasks not drawn). It is never replayed to a model, and the
clients fetch the tasks themselves (``GET /api/tasks?ids=``), so a task's own web-content mark travels with it."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Literal

from roost.constants import TASK_CARDS_MAX
from roost.events.hub import EventHub
from roost.talk.domain_tools import RecordContext
from roost.talk.store import TalkStore, message_out

log = logging.getLogger(__name__)

TASK_CARDS_KIND = "task_cards"
CardVerb = Literal["added", "listed"]


@dataclass(frozen=True)
class _Pending:
    user_id: str
    thread_id: str
    bot_id: str
    task_ids: tuple[str, ...] = ()
    verbs: frozenset[str] = frozenset()
    more: int = 0


def _wants_cards(ctx: RecordContext) -> bool:
    return ctx.user_started and not ctx.from_routine and ctx.thread_id is not None


def _merged(pending: _Pending, task_ids: tuple[str, ...], verb: CardVerb, more: int) -> _Pending:
    known = set(pending.task_ids)
    added = tuple(task_id for task_id in dict.fromkeys(task_ids) if task_id not in known)
    return _Pending(pending.user_id, pending.thread_id, pending.bot_id, (*pending.task_ids, *added),
                    pending.verbs | {verb}, max(pending.more, more))


def card_body(pending: _Pending) -> str:
    shown = pending.task_ids[:TASK_CARDS_MAX]
    verb = next(iter(pending.verbs)) if len(pending.verbs) == 1 else "tasks"
    more = pending.more + len(pending.task_ids) - len(shown)
    return json.dumps({"task_ids": list(shown), "verb": verb, "more": more})


class TaskCards:
    def __init__(self, talk: TalkStore, events: EventHub) -> None:
        self._talk = talk
        self._events = events
        self._runs: dict[str, _Pending] = {}   # run id -> what the run showed so far

    def note(self, ctx: RecordContext, task_ids: tuple[str, ...], verb: CardVerb, *, more: int = 0) -> None:
        """Remember the tasks a step of this run showed (posted by ``finish_run``)."""
        if not task_ids or not _wants_cards(ctx) or ctx.run_id is None:
            return
        start = self._runs.get(ctx.run_id) or _Pending(ctx.user_id, ctx.thread_id or "", ctx.bot_id)
        self._runs = {**self._runs, ctx.run_id: _merged(start, task_ids, verb, more)}

    async def note_now(self, ctx: RecordContext, task_ids: tuple[str, ...], verb: CardVerb, *,
                       more: int = 0) -> None:
        """A step with no run id: its line is posted at once."""
        if not task_ids or not _wants_cards(ctx):
            return
        await self._post(_merged(_Pending(ctx.user_id, ctx.thread_id or "", ctx.bot_id), task_ids, verb, more))

    async def finish_run(self, user_id: str, bot_id: str, run_id: str | None) -> None:
        """Post the run's one card line (if it showed tasks) and forget the run."""
        pending = self._runs.get(run_id or "")
        if pending is None:
            return
        self._runs = {key: value for key, value in self._runs.items() if key != run_id}
        if pending.user_id == user_id and pending.bot_id == bot_id:
            await self._post(pending)

    async def _post(self, pending: _Pending) -> None:
        try:
            message = await self._talk.add_message(pending.user_id, pending.thread_id, role="activity",
                                                   body=card_body(pending), tainted=False, kind=TASK_CARDS_KIND,
                                                   author_bot_id=pending.bot_id)
            await self._events.publish(pending.user_id, {"type": "message", "thread_id": pending.thread_id,
                                                         "message": message_out(message)})
        except Exception as exc:   # the cards are a courtesy: never break a run over them
            log.warning("a task card line was not posted: %s", type(exc).__name__)
