"""``RoutineHooks``: what the work queue and the scheduler call to close a routine run and say how it went.

``after_run`` is called by ``TurnRunner`` after a batch made only of routine items. It sets each run row's final
state and posts the Report (or one quiet line). ``report_slot`` posts the failure Report of a slot that never ran
(missed, held, skipped while waiting). Failures here are logged with ids and the exception's type name and never
raised: a Report that can't be posted must not stop the queue."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Collection, Sequence
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from roost.approvals.announce import publish_card
from roost.approvals.models import ApprovalCard, CardState
from roost.bots.models import BotStatus
from roost.constants import (
    REPORT_TEXT_MAX_CHARS, ROUTINE_ASK_MAX_WAIT_HOURS, ROUTINE_ERROR_RUN, ROUTINE_LATE_GRACE_SECONDS,
    ROUTINE_MODEL_FAILURES_MAX, ROUTINE_NAME_MAX,
)
from roost.desk.stuck import Block
from roost.events.hub import EventHub
from roost.llm.registry import model_label
from roost.routines.models import (
    AnswerLine, Clock, ReportBody, Routine, RoutinePatch, RoutineRun, RoutineSection, RunState,
)
from roost.routines.reports import (
    is_quiet, post_report, post_routine_note, publish_run, report_body, with_headline,
)
from roost.routines.runs import RoutineRunStore, utc_now
from roost.routines.store import RoutineStore
from roost.routines.watch_store import WatchStore
from roost.routines.watch_texts import change_section, watch_failing_line
from roost.routines.texts import (
    EXPIRED_NOTE, MODEL_FALLBACK_TEXT, RETRY_NOTE, STOPPED_NOTE, STUCK_TEXT, UNFINISHED_TEXT, UNFINISHED_TWICE_TEXT, clip, expired_text,
    headline, slot_line,
)
from roost.standing.models import StandingState
from roost.standing.store import PermissionStore
from roost.stuck.texts import routine_stuck_line
from roost.talk.instructions import routine_section
from roost.talk.store import TalkStore
from roost.talk.turn import TurnResult
from roost.work.models import ClaimedBatch, RunOutcome, WorkDraft, WorkItem, WorkKind
from roost.work.runs import madrid_today

logger = logging.getLogger(__name__)
_OPEN: Collection[str] = ("queued", "running")
AnswersFor = Callable[[str, str], Awaitable[Sequence[AnswerLine]]]   # (user_id, routine_id) -> its last answers


class RoutineHooks:
    def __init__(
        self, talk: TalkStore, events: EventHub, runs: RoutineRunStore, routines: RoutineStore,
        *, clock: Clock = utc_now, answers: AnswersFor | None = None, permissions: PermissionStore | None = None,
        watches: WatchStore | None = None,
    ) -> None:
        self._watches = watches             # None: no page watch tells a run what changed
        self._answers = answers
        self._permissions = permissions     # None: routine runs carry no standing permissions
        self._turns: Any = None     # the runner: its queue, ``submit`` and ``settle`` (attached once it exists)
        self._cards: Any = None     # the Ask-card store
        self._bots: Any = None
        self._talk = talk
        self._events = events
        self._runs = runs
        self._routines = routines
        self._clock = clock

    def attach(self, turns: Any, cards: Any, bots: Any) -> None:
        """Late wiring: the runner is built with these hooks, so it is handed over afterwards."""
        self._turns, self._cards, self._bots = turns, cards, bots

    async def prompt_section(self, user_id: str, items: Sequence[WorkItem]) -> RoutineSection | None:
        """What a routine run is told (nobody is watching, its slot, its last answers); ``None`` for any other run."""
        if not items or any(item.kind is not WorkKind.ROUTINE for item in items):
            return None
        run = await self._runs.for_item(user_id, items[0].id)
        routine = await self._routines.get(user_id, run.routine_id) if run is not None else None
        if run is None or routine is None:
            return None
        now = self._clock()
        late = now - run.slot_at > timedelta(seconds=ROUTINE_LATE_GRACE_SECONDS)
        answers = tuple(await self._answers(user_id, routine.id)) if self._answers is not None else ()
        text = routine_section(routine.name, slot_line(run.slot_at, now, late=late), tuple(a.text for a in answers))
        change = await self._watch_change(user_id, routine, run)
        if change is not None:
            return RoutineSection(f"{text}\n{change}", tainted=True, model=routine.model)   # page content taints it
        return RoutineSection(text, tainted=any(a.tainted for a in answers),   # a tainted question taints the run
                              model=routine.model)

    async def _watch_change(self, user_id: str, routine: Routine, run: RoutineRun) -> str | None:
        """The page watch's line and the escaped change, for the run the change started (else None)."""
        if self._watches is None or routine.watch is None:
            return None
        snap = await self._watches.get(user_id, routine.id)
        if snap is None or snap.change_run_id != run.id or not snap.change_text:
            return None
        return change_section(routine.watch, snap.change_text)

    async def standing_for(self, user_id: str, items: Sequence[WorkItem]) -> StandingState | None:
        """A routine run's standing permissions for its gate (live ones with some of today's count left), or None
        for any other run, an unknown routine or a routine with none."""
        if self._permissions is None or not items or any(item.kind is not WorkKind.ROUTINE for item in items):
            return None
        run = await self._runs.for_item(user_id, items[0].id)
        routine = await self._routines.get(user_id, run.routine_id) if run is not None else None
        if routine is None:
            return None
        today = madrid_today(self._clock())
        live = await self._permissions.live_for_routine(user_id, routine.id, today)
        return StandingState(routine.id, routine.instructions, live, today) if live else None

    async def ask_deadline(self, user_id: str, items: Sequence[WorkItem], now: datetime) -> datetime | None:
        """When an Ask card opened by this batch stops waiting: the routine's next slot, but never more than
        ``ROUTINE_ASK_MAX_WAIT_HOURS``. ``None`` for any batch that is not routine items (a chat keeps approval
        modes' own rule)."""
        if not items or any(item.kind is not WorkKind.ROUTINE for item in items):
            return None
        run = await self._runs.for_item(user_id, items[0].id)
        return await self._deadline_for(user_id, run, now) if run is not None else None

    async def _deadline_for(self, user_id: str, run: RoutineRun, now: datetime) -> datetime:
        cap = now + timedelta(hours=ROUTINE_ASK_MAX_WAIT_HOURS)
        routine = await self._routines.get(user_id, run.routine_id)
        if routine is None or routine.next_run_at is None:
            return cap
        return min(routine.next_run_at, cap)

    async def on_ask_expired(self, user_id: str, work_item_id: str, what: str) -> None:
        """No answer came in time: the slot is ``expired`` and a Report names the step that was skipped."""
        run = await self._runs.for_item(user_id, work_item_id)
        if run is None:
            return
        closed = await self.finish(user_id, run, "expired", note=EXPIRED_NOTE)
        routine = await self._routines.get(user_id, run.routine_id)
        if closed is None or routine is None:
            return
        await self._fail(user_id, run, routine, "expired", _NO_RESULT, text=expired_text(what))

    async def sweep_asks(self, user_id: str, now: datetime) -> None:
        """Expire this user's routine Ask cards that passed their deadline. Chat cards are never touched."""
        if self._cards is None or self._turns is None:
            return
        for card in await self._cards.list_open(user_id):
            try:
                await self._sweep_card(user_id, card, now)
            except Exception as exc:
                logger.warning("Expiring an Ask card of bot %s user %s failed: %s", card.bot_id, user_id,
                               type(exc).__name__)

    async def _sweep_card(self, user_id: str, card: ApprovalCard, now: datetime) -> None:
        run = await self._run_of_card(user_id, card)
        if run is None or run.state not in _OPEN:
            return
        opened = run.started_at or run.created_at    # the run's own clock, so the wait is the same in tests
        if now < await self._deadline_for(user_id, run, opened):
            return
        closed = await self._cards.close(user_id, card.id, CardState.EXPIRED)
        if closed is None:
            return    # answered a moment ago
        await publish_card(self._events, user_id, closed)
        await self.on_ask_expired(user_id, run.work_item_id or card.work_item_id or "", _what(closed))
        await self._turns.settle(user_id, card.bot_id)

    async def parked_on_card(self, user_id: str, run: RoutineRun) -> bool:
        """True while one of this user's open Ask cards belongs to ``run`` (so it is waiting, not lost)."""
        if self._cards is None:
            return False
        for card in await self._cards.list_open(user_id):
            owner = await self._run_of_card(user_id, card)
            if owner is not None and owner.id == run.id:
                return True
        return False

    async def _run_of_card(self, user_id: str, card: ApprovalCard) -> RoutineRun | None:
        """The routine run an Ask card belongs to: its own work item's run, or the run a card-answer item carried on."""
        item_id, seen = card.work_item_id, 0
        while item_id is not None and seen < 4:
            run = await self._runs.for_item(user_id, item_id)
            if run is not None:
                return run
            previous = await self._cards.card_for_answer(user_id, item_id)
            item_id, seen = (previous.work_item_id if previous is not None else None), seen + 1
        return None

    async def overlap_note(self, user_id: str, routine: Routine, text: str) -> None:
        """One quiet line in the bot's main chat: a slot was skipped because the last run was still going."""
        thread, _ = await self._talk.ensure_main_thread(user_id, routine.bot_id)
        await post_routine_note(self._talk, self._events, user_id, thread.id, routine.bot_id, "skipped",
                                routine.name, routine_id=routine.id, text=text)

    async def watch_failing(self, user_id: str, routine: Routine, kind: str) -> None:
        """One quiet line in the bot's main chat: its page watch could not check the page WATCH_FAILS_STUCK times in
        a row, and why (owner, 2026-11-10). Said once per streak; a good read starts a new one."""
        if routine.watch is None:
            return
        text = watch_failing_line(routine.name, routine.watch.host, kind, routine.watch.every_min)
        thread, _ = await self._talk.ensure_main_thread(user_id, routine.bot_id)
        await post_routine_note(self._talk, self._events, user_id, thread.id, routine.bot_id, "watch_failed",
                                routine.name, routine_id=routine.id, text=text)

    async def after_run(self, user_id: str, batch: ClaimedBatch, result: TurnResult, outcome: RunOutcome) -> None:
        """Close the runs of an all-routine batch (or of the card answers that carried a parked one on) and post
        their Report. A batch with any other item is ignored. A run that ended on an Ask card stays open."""
        try:
            pairs = await self._runs_of(user_id, batch)
        except Exception as exc:
            logger.warning("Finding routine runs failed for bot %s user %s: %s", batch.bot.id, user_id,
                           type(exc).__name__)
            return
        parked = outcome == "done" and (result.parked is not None or bool(result.plan))
        reported = False
        for item, run in pairs:
            try:
                if parked:
                    await self._runs.set_state(user_id, run.id, "running", expected=("queued",))
                    continue
                reported = await self._close(user_id, run, item, result, outcome, post=not reported) or reported
            except Exception as exc:
                logger.warning("Closing a routine run failed for bot %s user %s: %s",
                               batch.bot.id, user_id, type(exc).__name__)

    async def _runs_of(self, user_id: str, batch: ClaimedBatch) -> tuple[tuple[WorkItem, RoutineRun], ...]:
        if not batch.items or any(item.kind not in (WorkKind.ROUTINE, WorkKind.CARD_ANSWER) for item in batch.items):
            return ()
        pairs: list[tuple[WorkItem, RoutineRun]] = []
        for item in batch.items:
            run = await self._run_of_item(user_id, item)
            if run is not None and all(run.id != other.id for _, other in pairs):
                pairs.append((item, run))
        return tuple(pairs)

    async def _run_of_item(self, user_id: str, item: WorkItem) -> RoutineRun | None:
        if item.kind is WorkKind.ROUTINE:
            return await self._runs.for_item(user_id, item.id)
        if self._cards is None:
            return None
        card = await self._cards.card_for_answer(user_id, item.id)
        run = await self._run_of_card(user_id, card) if card is not None else None
        return run if run is not None and run.state in _OPEN else None

    async def _close(
        self, user_id: str, run: RoutineRun, item: WorkItem, result: TurnResult, outcome: RunOutcome, *, post: bool,
    ) -> bool:
        routine = await self._routines.get(user_id, run.routine_id)
        if outcome in ("stopped", "interrupted"):
            await self.finish(user_id, run, "skipped", note=STOPPED_NOTE)
            return False
        wall = result.block or result.wall
        if wall is None and routine is not None and routine.model is not None:
            await self._model_outcome(user_id, routine, ok=outcome == "done")
        if wall is not None:
            await self.finish(user_id, run, "error", note="Stuck")
            await self._go_stuck(user_id, run, routine, wall.host)
            return post and await self._fail(user_id, run, routine, "stuck", result, host=wall.host,
                                             text=_stuck_text(wall))
        if outcome == "error":
            if item.kind is WorkKind.ROUTINE and run.note != RETRY_NOTE and await self._retry(user_id, run, item):
                return False
            await self.finish(user_id, run, "error", note=outcome)
            await self._go_stuck(user_id, run, routine, "")
            return post and await self._fail(user_id, run, routine, "error", result, text=UNFINISHED_TWICE_TEXT
                                             if run.note == RETRY_NOTE else UNFINISHED_TEXT)
        if outcome != "done":
            await self.finish(user_id, run, "error", note=outcome)
            return post and await self._fail(user_id, run, routine, "error", result, text=UNFINISHED_TEXT)
        await self.finish(user_id, run, "done")
        return post and routine is not None and await self._report_reply(user_id, run, routine, result)

    async def _model_outcome(self, user_id: str, routine: Routine, *, ok: bool) -> None:
        """The routine's own model (owner, 2026-11-09): after ``ROUTINE_MODEL_FAILURES_MAX`` failed runs in a row it
        goes back to the bot's model, and the bot's chat says so. A Stuck run is not the model's fault: not counted."""
        counted = await self._routines.note_model_run(user_id, routine.id, ok=ok)
        if ok or counted is None or counted.model is None or counted.model_failures < ROUTINE_MODEL_FAILURES_MAX:
            return
        await self._routines.update(user_id, routine.id, RoutinePatch({"model": None}))
        thread, _ = await self._talk.ensure_main_thread(user_id, routine.bot_id)
        text = MODEL_FALLBACK_TEXT.format(name=routine.name, model=model_label(counted.model))
        await post_routine_note(self._talk, self._events, user_id, thread.id, routine.bot_id, "model_fallback",
                                routine.name, routine_id=routine.id, text=text)
        await self._events.publish(user_id, {"type": "routines_changed", "bot_id": routine.bot_id})

    async def _retry(self, user_id: str, run: RoutineRun, item: WorkItem) -> bool:
        """R1: an errored run is tried once more, as a new work item on the same run row. ``False`` when it can't be."""
        if self._turns is None:
            return False
        new_id = str(uuid4())
        if await self._runs.rebind(user_id, run.id, new_id, note=RETRY_NOTE) is None:
            return False
        await self._turns.submit(user_id, WorkDraft(
            bot_id=item.bot_id, thread_id=item.thread_id, kind=WorkKind.ROUTINE, origin=item.origin, body=item.body,
            tainted=item.tainted, message_id=item.message_id, link_scope=item.link_scope), item_id=new_id)
        return True

    async def _go_stuck(self, user_id: str, run: RoutineRun, routine: Routine | None, host: str) -> None:
        """R1: the bot shows Stuck with the one-line reason (no Stuck card: nobody is there to clear it)."""
        if self._bots is None or routine is None:
            return
        activity = routine_stuck_line(host, routine.name)
        await self._bots.set_status(user_id, run.bot_id, BotStatus.STUCK)
        await self._events.publish(user_id, {
            "type": "bot_status", "bot_id": run.bot_id, "status": BotStatus.STUCK.value, "activity": clip(activity)})

    async def _report_reply(self, user_id: str, run: RoutineRun, routine: Routine, result: TurnResult) -> bool:
        if is_quiet(result.reply):
            return False      # owner, 2026-11-05: nothing new leaves your chat alone (the reply is in the run log)
        body = report_body(result.reply, name=routine.name, routine_id=routine.id, run_id=run.id,
                           log_thread_id=routine.thread_id, tainted=result.tainted)
        return await post_report(self._talk, self._events, user_id, run.bot_id, body, runs=self._runs,
                                 now=self._clock()) is not None

    async def _fail(
        self, user_id: str, run: RoutineRun, routine: Routine | None, kind: str, result: TurnResult,
        *, text: str, host: str = "",
    ) -> bool:
        if routine is None:
            return False
        partial = result.reply.strip()
        title = headline(kind, routine.name, host)
        body = ReportBody(
            source="routine", headline=title, text=with_headline(title, f"{text}\n\n{partial}" if partial else text),
            routine_id=routine.id, run_id=run.id, log_thread_id=routine.thread_id,
            routine_name=clip(routine.name, ROUTINE_NAME_MAX), tainted=result.tainted)
        return await post_report(self._talk, self._events, user_id, run.bot_id, body, runs=self._runs,
                                 now=self._clock(), always=True) is not None

    async def finish(
        self, user_id: str, run: RoutineRun, state: RunState, *, note: str | None = None,
    ) -> RoutineRun | None:
        """Move an open run to ``state`` and tell the web. ``None`` when it was no longer open."""
        changed = await self._runs.set_state(user_id, run.id, state, expected=_OPEN, note=note)
        if changed is not None:
            await publish_run(self._events, user_id, changed)
            await self._note_last_error(user_id, changed, state)
        return changed

    async def watch_missing(self, user_id: str, routine: Routine, text: str) -> None:
        """One quiet line in the bot's chat: the watched part is not on the page, so nothing is compared."""
        thread, _ = await self._talk.ensure_main_thread(user_id, routine.bot_id)
        await post_routine_note(self._talk, self._events, user_id, thread.id, routine.bot_id, "watch_missing",
                                routine.name, routine_id=routine.id, text=text)

    async def _note_last_error(self, user_id: str, run: RoutineRun, state: RunState) -> None:
        """v47: a run that did not finish is the routine's last error; one that finished clears it."""
        if state == "error":
            await self._routines.set_last_error(user_id, run.routine_id, ROUTINE_ERROR_RUN, self._clock())
        elif state == "done":
            await self._routines.set_last_error(user_id, run.routine_id, None, None)

    async def publish(self, user_id: str, run: RoutineRun) -> None:
        await publish_run(self._events, user_id, run)

    async def report_slot(self, user_id: str, routine: Routine, run: RoutineRun, kind: str, text: str) -> None:
        """The always-posted Report of a slot that did not run (``kind``: missed, held or skipped)."""
        try:
            title = headline(kind, routine.name)
            body = ReportBody(
                source="routine", headline=title, text=with_headline(title, text), routine_id=routine.id,
                run_id=run.id, log_thread_id=routine.thread_id, routine_name=clip(routine.name, ROUTINE_NAME_MAX))
            await post_report(self._talk, self._events, user_id, routine.bot_id, body, runs=self._runs,
                              now=self._clock(), always=True)
        except Exception as exc:
            logger.warning("Posting a routine Report failed for routine %s bot %s user %s: %s",
                           routine.id, routine.bot_id, user_id, type(exc).__name__)


_NO_RESULT = TurnResult(reply="", tainted=False, capped=False)


def _what(card: ApprovalCard) -> str:
    return card.steps[0].title if card.steps else card.request


def _stuck_text(block: Block) -> str:
    return clip(block.note.strip() or STUCK_TEXT, REPORT_TEXT_MAX_CHARS)
