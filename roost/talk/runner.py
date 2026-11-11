"""``TurnRunner`` — one drain loop per bot over the durable work queue
(spec §4.2 "Work queue", §11 step 5; decision D-A).

Replaces Night-1's in-memory ``_pending`` map, which kept only the newest
thread per bot (MORNING.md: two chats of one bot during a run — only the
newest got answered). Every message is a durable ``work_items`` row:
``submit`` stores it and ``kick``s the bot; the bot's drain loop claims
the oldest items for ONE thread at a time (items in a row for the same
thread become one turn) and runs them, so a busy bot accepts work at once
and nothing is lost across chats or restarts.

Still the error boundary ``run_turn`` relies on: an unexpected exception
becomes a "something went wrong" notice, a hung turn hits the wall-time
cap, and the bot always settles back to Resting (Stuck while one of its
Stuck cards is open, Off duty when it is off duty).

Stuck flow (Piece A): a chat run that ended on a block leaves a Stuck card
(``_on_block``); a continue run blocked again on the same host marks its
card blocked instead (rung 4).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from functools import partial
from typing import Any, Awaitable, Callable, Sequence
from uuid import uuid4

from roost.approvals import announce as approval_announce
from roost.approvals.models import ApprovalDraft, ApprovalState, CardTooBig
from roost.approvals.texts import PLAN_WAITS_LINE
from roost.approvals.wiring import ApprovalWiring
from roost.computer_use.run_fence import routine_chat_sites
from roost.media.pictures import owner_pictures
from roost.media.store import ChatMediaStore
from roost.computer_use.runner import ScreenKit
from roost.computer_use.session import ComputerUseLease
from roost.bots.models import Bot, BotStatus
from roost.bots.service import bot_out
from roost.bots.status import ActivityBoard
from roost.choices.decisions import DecisionBook
from roost.bots.store import BotStore
from roost.config import Config
from roost.constants import (
    COMPUTER_RESTARTED_LINE, COMPUTER_WAITING_LINE,
    DAILY_RUN_CAP, HANDOFF_TIMEOUT_S, MAX_HANDOFF_DEPTH, MAX_RUN_SECONDS, STEER_DEBOUNCE_SECONDS,
    STUCK_REQUEST_MAX_CHARS,
)
from roost.desk import DeskFactory, RoomHooks
from roost.desk.control import ControlLock
from roost.events.hub import EventHub
from roost.helpers.tools import HelperTools
from roost.lessons.service import LessonService, lesson_run
from roost.lessons.signals import LessonSignals
from roost.llm.types import Model, ModelUnreachable
from roost.mac.models import FolderLine
from roost.memory.capture import FinishedRun
from roost.memory.hooks import MemoryHooks
from roost.money.project_store import ProjectStore
from roost.vault.store import VaultStore
from roost.rooms.models import RoomContext, RoomMember
from roost.rooms.store import RoomStore
from roost.plan.service import PlanService
from roost.skills.service import SkillService
from roost.routines.hooks import RoutineHooks
from roost.routines.models import Clock, RoutineSection
from roost.routines.runs import utc_now
from roost.routines.watch import WatchChecker, is_watch_batch
from roost.signin.cards import sign_in_block_for
from roost.signin.service import SignInService
from roost.stuck.announce import post_bot_line, publish_card
from roost.stuck.models import CardDraft, StuckCard
from roost.stuck.store import StuckStore
from roost.stuck.typed_reply import stuck_reply_for
from roost.stuck.texts import already_waiting_line, blocked_line, stuck_message_body, stuck_status_line
from roost.talk.carry import keep_sites
from roost.talk.domain_tools import DomainTools, build_domain_tools
from roost.talk.gate import Gate
from roost.talk.limits import LimitState
from roost.talk.notices import daily_limit_note, interrupted_note, off_duty_note, post_notice, restart_dropped_note
from roost.talk.recent_groups import RecentGroups
from roost.talk.steer import RunRestart, RunSteer
from roost.talk.stop_flow import StopFlow
from roost.talk.store import TalkStore
from roost.talk.turn import EMPTY_RESULT, RunInputs, TurnResult, _may_open_cards, _routine_run
from roost.models_check.store import SeenModelStore
from roost.talk.turn import run_turn as run_one_turn
from roost.usage.reading import NoUsageSource, UsageSource, full_limit_active, in_reserve
from roost.usage.scope import UsageRecorder, UsageScope, kind_for_work, usage_scope
from roost.usage.store import TokenUsageStore
from roost.voice.calls import CallRegistry
from roost.voice.tasks import TrackedTasks
from roost.work.models import ClaimedBatch, HandoffResult, RunOutcome, WorkDraft, WorkItem, WorkKind
from roost.work.queue import WorkQueue
from roost.work.runs import RunLog, madrid_today, seconds_until_madrid_midnight

logger = logging.getLogger(__name__)

_ERROR_TEXT = "Something went wrong on my side. Please try again."
_UNREACHABLE_TEXT = "I can't reach Claude right now: the internet or Claude's service is down. Send it again in a minute."
# The spec's 20-minute wall-time cap, enforced around the WHOLE turn.
_TIMEOUT_TEXT = "Took too long — say continue."


def _with_taken(items: tuple[WorkItem, ...], taken: tuple[WorkItem, ...]) -> tuple[WorkItem, ...]:
    """The run's items and the messages it took mid-work, each once."""
    known = {item.id for item in items}
    return (*items, *(item for item in taken if item.id not in known))


def _request_text(items: Sequence[WorkItem]) -> str:
    """What a new Stuck card keeps to carry on with: the run's own items,
    oldest first, capped at ``STUCK_REQUEST_MAX_CHARS``."""
    return "\n".join(item.body for item in items)[:STUCK_REQUEST_MAX_CHARS]


@dataclass(frozen=True)
class _Waiter:
    """One open handoff: ``asker_bot_id``'s run waits on ``bot_id``."""

    asker_bot_id: str
    bot_id: str
    future: "asyncio.Future[HandoffResult]"


class TurnRunner(StopFlow):
    def __init__(
        self, config: Config, bots: BotStore, talk: TalkStore, events: EventHub,
        desks: DeskFactory, model: Model, activity: ActivityBoard,
        *, queue: WorkQueue | None = None, runs: RunLog | None = None, rooms: RoomStore | None = None,
        domain: DomainTools | None = None, control: ControlLock | None = None, stuck: StuckStore | None = None,
        memory: MemoryHooks | None = None, seen_models: SeenModelStore | None = None,
        approvals: ApprovalWiring | None = None, decisions: DecisionBook | None = None,
        routines: RoutineHooks | None = None, vault: VaultStore | None = None,
        usage: UsageSource | None = None, clock: Clock = utc_now, plan: PlanService | None = None,
        cu_leases: ComputerUseLease | None = None,
        skills: SkillService | None = None, debounce_s: float | None = None,
        signin: SignInService | None = None, calls: CallRegistry | None = None,
        lessons: LessonService | None = None, lesson_signals: LessonSignals | None = None,
        token_usage: UsageRecorder | None = None, watch: WatchChecker | None = None,
    ) -> None:
        # Token usage: every model call of a run (its steps, helpers and worker jobs) is summed for its bot.
        self._token_usage = token_usage if token_usage is not None else TokenUsageStore(config)
        self._watch = watch             # None: a routine's page check (a trigger item) is closed unread
        self._watching: frozenset[str] = frozenset()    # bots reading a watched page right now (no model)
        self._lessons = lessons         # None: a run that went wrong offers no lesson
        # Voice calls (§3): which threads are in a call; None: no thread ever is.
        self._calls = calls
        # Work nobody waits for (a call turn's memory capture), kept until it ends.
        self._background = TrackedTasks()
        # Steer: each live run's steer by bot (its thread and handle), bots being stopped, and the burst debounce.
        self._steers: dict[str, tuple[str, RunSteer]] = {}
        self._stopping: frozenset[str] = frozenset()
        self._gathering: dict[str, str] = {}
        configured = config.steer_debounce_seconds
        self._debounce_s = debounce_s if debounce_s is not None else (
            configured if configured is not None else STEER_DEBOUNCE_SECONDS)
        # C3: one screen loop per computer (app.state.cu_leases), handed to each run with the config.
        self._screen = ScreenKit(config, cu_leases if cu_leases is not None else ComputerUseLease(),
                                 signals=lesson_signals)
        self._skills = skills           # None: no Skills index in the bot's prompt
        self._signin = signin           # None: no "No, this time" sign-in is cleared after a run
        self._plan = plan               # None: the bot's Plan is not in its prompt and no "Updated plan" line is posted
        self._usage = usage if usage is not None else NoUsageSource()
        self._clock = clock
        self._vault = vault
        self._decisions = decisions
        self._routines = routines       # None: routine runs close nothing and post no Reports
        self._config = config
        self._approvals = approvals     # None: today's verdicts, no Ask cards
        self._memory = memory
        self._seen_models = seen_models if seen_models is not None else SeenModelStore(config)
        self._bots = bots
        self._talk = talk
        self._events = events
        self._desks = desks
        self._run_users: dict[str, str] = {}    # bot id -> the user whose run it is (to say "waiting" to)
        self._model = model
        self._activity = activity
        self._gate = Gate(config)
        self._control = control if control is not None else ControlLock()
        if hasattr(desks, "set_room_hooks"):
            desks.set_room_hooks(RoomHooks(busy=self.busy_ids, on_wait=self._say_waiting,
                                           control_mark=self._control.mark, on_healed=self._say_restarted))
        self._domain = domain if domain is not None else build_domain_tools(config, events, desks=desks)
        self._queue = queue if queue is not None else WorkQueue(config)
        self._runs = runs if runs is not None else RunLog(config)
        self._rooms = rooms if rooms is not None else RoomStore(config)
        self._stuck = stuck if stuck is not None else StuckStore(config)
        self._tasks: dict[str, "asyncio.Task[None]"] = {}
        # R9: settles that run after a drain task ended, kept until they finish so none is garbage-collected.
        self._settling: frozenset["asyncio.Task[None]"] = frozenset()
        # Bots in a Stuck stay: announced as Stuck and not settled to anything else since (M8).
        self._stuck_bots: frozenset[str] = frozenset()
        self._lock = asyncio.Lock()
        self._recent_groups = RecentGroups()   # the tool groups each thread's last runs used (§4, in memory only)
        self._limit_noticed: dict[str, str] = {}
        self._waiters: dict[str, _Waiter] = {}

    @property
    def queue(self) -> WorkQueue:
        return self._queue

    def set_watch(self, watch: WatchChecker) -> None:
        """The page watch is built after the runner (its launcher queues on it), so it is handed over here."""
        self._watch = watch

    @property
    def domain(self) -> DomainTools:
        return self._domain

    async def runs_today(self, user_id: str, bot_id: str) -> int:
        """How many runs the bot has started since local midnight."""
        return await self._runs.count_today(user_id, bot_id)

    async def limit_state(self, user_id: str, bot: Bot) -> LimitState:
        """Where ``bot`` stands against today's run cap."""
        count = await self.runs_today(user_id, bot.id)
        reading = await self._usage.read()
        return LimitState(
            count=count, cap=DAILY_RUN_CAP, at_cap=count >= DAILY_RUN_CAP,
            full_limit=full_limit_active(bot, reading, self._clock()), in_reserve=in_reserve(reading), reading=reading)

    async def submit(self, user_id: str, draft: WorkDraft, *, item_id: str | None = None) -> WorkItem:
        """Durably queue ``draft`` and make sure its bot is draining. Returns
        at once even when the bot is busy ("a busy bot still accepts messages")."""
        item = await self._queue.enqueue(user_id, draft, item_id=item_id)
        bot = await self._bots.get(user_id, draft.bot_id)
        if bot is not None and bot.off_duty:
            await post_notice(self._talk, self._events, user_id, draft.thread_id, off_duty_note(bot.name))
        await self.kick(user_id, draft.bot_id)
        return item

    async def hand_off(
        self, user_id: str, asker_bot_id: str, target_bot_id: str, prepare: Callable[[], Awaitable[WorkDraft]],
    ) -> HandoffResult:
        """D-C: queue the draft ``prepare`` builds in the target's work queue
        and wait for its answer (``HANDOFF_TIMEOUT_S``). Refused when the
        target already waits on the asker, directly or through other bots —
        from a nested chain, an independent run, a sibling or an @everyone
        post — since both would sit out the timeout (Review Focus #4). The
        check and the waiter's registration share one tick (no await
        between), so two runs can't both pass it; ``prepare`` posts the
        handoff lines only after that, and the waiter exists before the
        item, so even an instant answer can't be missed."""
        if self._waits_on(target_bot_id, asker_bot_id):
            return HandoffResult(status="refused")
        item_id = str(uuid4())
        future: "asyncio.Future[HandoffResult]" = asyncio.get_running_loop().create_future()
        self._waiters = {**self._waiters, item_id: _Waiter(asker_bot_id, target_bot_id, future)}
        try:
            await self.submit(user_id, await prepare(), item_id=item_id)
            return await asyncio.wait_for(asyncio.shield(future), timeout=HANDOFF_TIMEOUT_S)
        except TimeoutError:
            return HandoffResult(status="timeout")
        finally:
            self._waiters = {k: w for k, w in self._waiters.items() if k != item_id}

    def _waits_on(self, start: str, goal: str) -> bool:
        """Whether ``start`` already waits on ``goal`` along the open
        handoffs (asker → target edges), however many bots lie between."""
        seen: frozenset[str] = frozenset()
        frontier = frozenset({start})
        while frontier and goal not in frontier:
            seen = seen | frontier
            frontier = frozenset(w.bot_id for w in self._waiters.values() if w.asker_bot_id in frontier) - seen
        return goal in frontier

    def _resolve(self, item_ids: Sequence[str], result: HandoffResult) -> None:
        for item_id in item_ids:
            waiter = self._waiters.get(item_id)
            if waiter is not None and not waiter.future.done():
                waiter.future.set_result(result)

    async def _ancestor_bots(self, user_id: str, items: Sequence[WorkItem]) -> frozenset[str]:
        """Bots up the handoff chain of ``items`` — all of them are waiting."""
        found: frozenset[str] = frozenset()
        parent_ids = tuple(i.parent_item_id for i in items if i.parent_item_id)
        for _ in range(MAX_HANDOFF_DEPTH):
            parents = [p for p in [await self._queue.get(user_id, pid) for pid in parent_ids] if p is not None]
            found = found | {p.bot_id for p in parents}
            parent_ids = tuple(p.parent_item_id for p in parents if p.parent_item_id)
            if not parent_ids:
                break
        return found

    async def set_off_duty(self, user_id: str, bot_id: str, off_duty: bool) -> Bot | None:
        bot = await self._bots.set_off_duty(user_id, bot_id, off_duty)
        if bot is None:
            return None
        if off_duty and self._approvals is not None:
            self._approvals.sessions.end_for_bot(user_id, bot_id)   # a session OK ends when the bot goes off duty
        if not off_duty:
            # R9: back on duty with an open Stuck card shows Stuck, not Resting. Settle BEFORE the
            # kick, so it shows at once: once a drain task exists, settle waits for it to end.
            await self.settle(user_id, bot_id)
            bot = await self._bots.get(user_id, bot_id) or bot
        await self._events.publish(user_id, {"type": "bot_updated", "bot": bot_out(bot, self._activity.get(bot_id))})
        if not off_duty:
            await self.kick(user_id, bot_id)
        return bot

    async def kick(self, user_id: str, bot_id: str) -> None:
        async with self._lock:
            running = self._tasks.get(bot_id)
            if running is not None and not running.done():
                return  # the running drain loop picks the new item up
            self._tasks[bot_id] = asyncio.create_task(self._drain(user_id, bot_id))

    def busy_ids(self) -> frozenset[str]:
        """The bots that are On it right now: the keeper never evicts their computers to make room."""
        return frozenset(bot_id for bot_id, task in self._tasks.items() if not task.done())

    def note_run_user(self, user_id: str, bot_id: str) -> None:
        self._run_users = {**self._run_users, bot_id: user_id}

    async def _say_waiting(self, bot_id: str) -> None:
        """The activity line while a bot's computer waits for room. Nobody to tell, nothing to say."""
        user_id = self._run_users.get(bot_id)
        if user_id is None:
            return
        self._activity.set(bot_id, COMPUTER_WAITING_LINE)
        await self._events.publish(user_id, {
            "type": "bot_status", "bot_id": bot_id, "status": BotStatus.ON_IT.value, "activity": COMPUTER_WAITING_LINE,
        })

    async def _say_restarted(self, bot_id: str) -> None:
        """One plain line in the bot's main chat after its hung computer was restarted (owner, 2026-11-10). The desk
        says it at most once per restart cooldown; with nobody's run to tell, nothing is said."""
        user_id = self._run_users.get(bot_id)
        if user_id is None:
            return
        thread, _created = await self._talk.ensure_main_thread(user_id, bot_id)
        await post_notice(self._talk, self._events, user_id, thread.id, COMPUTER_RESTARTED_LINE,
                          kind="computer_restart")

    async def cancel(self, bot_id: str) -> None:
        """``delete_bot``: stop the bot's run and answer everyone waiting on
        it — its items vanish with the bot row, so nothing else would."""
        await self._cancel_task(bot_id)
        self._resolve(tuple(k for k, w in self._waiters.items() if w.bot_id == bot_id), HandoffResult(status="dropped"))

    async def recover_on_boot(self) -> None:
        """Gateway start: close runs the old process left open, re-queue its
        claimed items, drop its open handoffs, and say so in each thread."""
        await self._runs.close_open_on_boot()
        report = await self._queue.recover_on_boot()
        for item in report.interrupted:
            await post_notice(self._talk, self._events, item.user_id, item.thread_id,
                              interrupted_note(item.inflight or ""), kind="interrupted")
        for item in report.dropped_handoffs:
            await post_notice(self._talk, self._events, item.user_id, item.thread_id,
                              restart_dropped_note(item.body), kind="dropped")

    async def resume_all(self) -> None:
        for user_id, bot_id in await self._queue.bots_with_queued():
            await self.kick(user_id, bot_id)

    async def restore_stuck_on_boot(self) -> None:
        """R9 / Review Focus #5: after a restart, a bot whose Stuck card is
        still open shows Stuck again. The old process may have died between
        opening the card and settling. An off-duty bot stays Off duty."""
        for user_id, bot_id in await self._stuck.open_bots():
            await self._settle_status(user_id, bot_id)

    async def restore_asking_on_boot(self) -> None:
        """After a restart, a bot whose Ask card is still open shows Asking you again."""
        if self._approvals is None:
            return
        for user_id, bot_id in await self._approvals.store.open_bots():
            await self._settle_status(user_id, bot_id)

    async def settle(self, user_id: str, bot_id: str) -> None:
        """R9: put the bot's status right after one of its cards changed
        (``/clear``, ``/give-up``, back on duty). With no drain task running it
        settles at once. While one runs, it settles once that task ends: the
        run settles its own status, but a card closed after that (Give up
        pressed while the run was ending) would leave the bot Stuck with no
        open card."""
        running = self._tasks.get(bot_id)
        if running is not None and not running.done():
            running.add_done_callback(partial(self._settle_after, user_id, bot_id))
            return
        await self._settle_status(user_id, bot_id)

    def _settle_after(self, user_id: str, bot_id: str, finished: "asyncio.Task[None]") -> None:
        """``settle``'s done-callback on a drain task. A callback can't await, so
        the settle runs in a task of its own, kept in ``_settling`` until it ends
        so it is never garbage-collected (the tests' ``wait_idle`` waits on it)."""
        task = finished.get_loop().create_task(self._settle_logged(user_id, bot_id))
        self._settling = self._settling | {task}
        task.add_done_callback(self._forget_settle)

    def _forget_settle(self, task: "asyncio.Task[None]") -> None:
        self._settling = self._settling - {task}

    async def _settle_logged(self, user_id: str, bot_id: str) -> None:
        """``settle`` again, not ``_settle_status`` straight away: a drain task
        kicked in the meantime is waited for in turn, so its On it run is never
        shown Resting. Nobody awaits this task, so an error is logged here."""
        try:
            await self.settle(user_id, bot_id)
        except Exception:
            logger.exception("Settling the status after a run failed for bot %s", bot_id)

    async def run_turn(self, user_id: str, bot_id: str, thread_id: str) -> None:
        """One turn outside the queue (direct callers and tests)."""
        bot = await self._bots.get(user_id, bot_id)
        if bot is None:
            return  # the bot was deleted
        inputs = RunInputs(handoff=self, room=await self._room_context(user_id, thread_id), domain=self._domain,
                           control=self._control, memory=self._memory, vault=self._vault, screen=self._screen)
        kind = kind_for_work(WorkKind.ROOM_POST if inputs.room is not None else WorkKind.MESSAGE)
        with usage_scope(UsageScope(self._token_usage, user_id, bot.id, kind)):
            await self._execute(user_id, bot, thread_id, await self._with_approval(user_id, bot, inputs))

    async def _room_context(self, user_id: str, thread_id: str) -> RoomContext | None:
        room = await self._rooms.get_by_thread(user_id, thread_id)
        if room is None:
            return None
        bots = [await self._bots.get(user_id, bot_id) for bot_id in room.member_ids]
        members = tuple(RoomMember(b.id, b.name, b.job) for b in bots if b is not None)
        return RoomContext(room_id=room.id, name=room.name, members=members, coordinator_id=room.coordinator_id)

    async def _cancel_task(self, bot_id: str) -> None:
        async with self._lock:
            task = self._tasks.pop(bot_id, None)
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _drain(self, user_id: str, bot_id: str) -> None:
        try:
            waited = await self.debounce(user_id, bot_id)
            while (batch := await self._claim_next(user_id, bot_id)) is not None:
                await (self._check_watch(user_id, batch) if is_watch_batch(batch.items)
                       else self._run_batch(user_id, batch))
                waited = await self.debounce(user_id, bot_id)
            if waited:
                await self._settle_status(user_id, bot_id)   # it said On it while waiting, and nothing ran
        except Exception:
            logger.exception("Work queue drain failed for bot %s", bot_id)

    async def _claim_next(self, user_id: str, bot_id: str) -> ClaimedBatch | None:
        # Claiming and "nothing left, unregister" happen under the same lock
        # ``kick`` takes, so an item queued in between is never stranded.
        async with self._lock:
            batch = await self._next_batch(user_id, bot_id)
            if batch is None and self._tasks.get(bot_id) is asyncio.current_task():
                del self._tasks[bot_id]
            return batch

    async def _next_batch(self, user_id: str, bot_id: str) -> ClaimedBatch | None:
        bot = await self._bots.get(user_id, bot_id)
        if bot is None or bot.off_duty or bot_id in self._stopping:
            return None
        limit = await self.limit_state(user_id, bot)
        if limit.capped:
            await self._hit_daily_limit(user_id, bot)
            return None
        # Inside the 10% reserve only your own work runs: a routine's item waits.
        skip = frozenset({WorkKind.ROUTINE}) if limit.in_reserve else frozenset()
        run_id = str(uuid4())
        items = await self._queue.claim_batch(user_id, bot_id, run_id, exclude_kinds=skip)
        if not items:
            return None
        if not is_watch_batch(items):     # a page check runs no model: it is no run of the day
            await self._runs.start(user_id, bot_id, items[0].thread_id, run_id)
        return ClaimedBatch(run_id=run_id, bot=bot, thread_id=items[0].thread_id, items=items)

    async def _check_watch(self, user_id: str, batch: ClaimedBatch) -> None:
        """A routine's page check, in the bot's own drain loop so it never overlaps the bot's runs (no model)."""
        self._watching = self._watching | {batch.bot.id}
        self.note_run_user(user_id, batch.bot.id)      # a restart during a check still gets its chat line
        try:
            if self._watch is not None:
                await self._watch.check(user_id, batch.bot, batch.items[0])
        except Exception:
            logger.exception("A page watch check failed for bot %s", batch.bot.id)
        finally:
            self._watching = self._watching - {batch.bot.id}
            await self._queue.complete(user_id, batch.run_id, "", False)

    async def _hit_daily_limit(self, user_id: str, bot: Bot) -> None:
        """One "daily limit reached" notice per bot per local day, in the
        thread of its oldest waiting item; the items stay queued and a kick
        is scheduled for just after midnight."""
        now = datetime.now(timezone.utc)
        today = madrid_today(now)
        first = await self._queue.first_queued(user_id, bot.id)
        if first is None or self._limit_noticed.get(bot.id) == today:
            return
        self._limit_noticed = {**self._limit_noticed, bot.id: today}
        await post_notice(self._talk, self._events, user_id, first.thread_id,
                          daily_limit_note(bot.name, DAILY_RUN_CAP), kind="daily_limit")
        loop = asyncio.get_running_loop()
        loop.call_later(seconds_until_madrid_midnight(now) + 1,
                        lambda: loop.create_task(self.kick(user_id, bot.id)))

    async def _inputs(self, user_id: str, batch: ClaimedBatch) -> RunInputs:
        inputs = RunInputs(
            items=batch.items, record_inflight=partial(self._queue.set_inflight, user_id, batch.run_id),
            handoff=self, ancestors=await self._ancestor_bots(user_id, batch.items),
            room=await self._room_context(user_id, batch.thread_id), domain=self._domain,
            control=self._control, memory=self._memory, run_id=batch.run_id, vault=self._vault,
            routine_section=await self._routine_section(user_id, batch.items), plan=self._plan,
            screen=self._screen,
            skills=self._skills, projects=ProjectStore(self._config).list,
            call=self._calls is not None and self._calls.active(batch.thread_id),
            stuck_reply=await stuck_reply_for(self._stuck, user_id, batch.items),
            routine_sites=await self._routine_sites(user_id, batch),
            chat_thread=await self._chat_thread(user_id, batch.thread_id),
            pictures=await owner_pictures(ChatMediaStore(self._config), user_id, batch.items),
            recent_groups=self._recent_groups.for_thread(batch.thread_id),
        )
        return await self._with_approval(user_id, batch.bot, inputs)

    async def _routine_sites(self, user_id: str, batch: ClaimedBatch) -> tuple[str, ...]:
        """A routine run's sites that its bot opened from your own chat (owner, 2026-11-05)."""
        if not batch.items or any(item.kind is not WorkKind.ROUTINE for item in batch.items):
            return ()
        return await routine_chat_sites(self._config, user_id, batch.thread_id)

    async def _chat_thread(self, user_id: str, thread_id: str) -> bool:
        """Whether the thread is a bot's 1:1 chat (a routine's run log or a room is not)."""
        thread = await self._talk.get_thread(user_id, thread_id)
        return thread is not None and thread.kind == "chat"

    async def _routine_section(self, user_id: str, items: tuple[WorkItem, ...]) -> RoutineSection | None:
        return await self._routines.prompt_section(user_id, items) if self._routines is not None else None

    async def _with_approval(self, user_id: str, bot: Bot, inputs: RunInputs) -> RunInputs:
        """This run's approval state: the bot's mode and topic switches, the Mac writes it has made lately,
        its live session OKs, and whether the run may park on a card (only your own chat may)."""
        inputs = replace(inputs, decisions=self._decisions)
        wiring = self._approvals
        if wiring is None:
            return inputs
        state = ApprovalState(
            mode=bot.approval.mode, ask_topics=bot.approval.ask_topics,
            cards=_may_open_cards(inputs) or _routine_run(inputs),
            mac_writes=wiring.limits.writes(bot.id) if wiring.limits is not None else 0,
            session_folders=wiring.sessions.folders(user_id, bot.id),
            standing=await self._routines.standing_for(user_id, inputs.items) if self._routines is not None else None,
            auto_review=bot.approval.auto_review and _may_open_cards(inputs),   # Full auto: your own chat only
        )
        live = (lambda: wiring.limits.writes(bot.id)) if wiring.limits is not None else None
        return replace(inputs, approval=state, mac_writes_now=live, mac_folders=await self._mac_folders(user_id, bot.id))

    async def _mac_folders(self, user_id: str, bot_id: str) -> tuple[FolderLine, ...]:
        grants = self._approvals.grants if self._approvals is not None else None
        found = await grants.for_bot(user_id, bot_id) if grants is not None else None
        return tuple(FolderLine(g.label, g.access, g.read_policy) for g in found or ())

    def _helper_tools(self, user_id: str, bot: Bot, thread_id: str, inputs: RunInputs) -> HelperTools:
        """This run's helpers: its own gate, model, activity and domain; the bot's one computer."""
        return HelperTools(
            user_id=user_id, bot_id=bot.id, bot_name=bot.name, thread_id=thread_id,
            run_id=inputs.run_id or str(uuid4()), runs=self._runs, gate=self._gate, model=self._model,
            desk=self._desks.for_bot(bot.id, bot.computer), activity=self._activity, events=self._events,
            domain=inputs.domain, control=inputs.control,
        )

    async def _run_batch(self, user_id: str, batch: ClaimedBatch) -> None:
        """One claimed batch, its tokens counted for its bot under the first item's kind."""
        kind = kind_for_work(batch.items[0].kind) if batch.items else kind_for_work(WorkKind.MESSAGE)
        with usage_scope(UsageScope(self._token_usage, user_id, batch.bot.id, kind)):
            await self._run_claimed(user_id, batch)

    async def _run_claimed(self, user_id: str, batch: ClaimedBatch) -> None:
        inputs = await self._inputs(user_id, batch)
        # Steer: only your own 1:1 chat runs read new messages mid-work; routines, handoffs and rooms never do.
        steer = RunSteer(take=partial(self.take_messages, user_id, batch.bot.id, batch.thread_id, batch.run_id),
                         steerable=_may_open_cards(inputs))
        self._steers = {**self._steers, batch.bot.id: (batch.thread_id, steer)}
        try:
            batch, inputs, result, outcome = await self._run_steered(user_id, batch, inputs, steer)
        finally:
            self._steers = {k: v for k, v in self._steers.items() if k != batch.bot.id}
        batch = replace(batch, items=_with_taken(batch.items, steer.taken))
        self._recent_groups = self._recent_groups.noted(batch.thread_id, result.used_groups)   # §4: the next run's preload
        done_ids = await self._queue.complete(user_id, batch.run_id, result.reply, result.tainted)
        await self._runs.finish(user_id, batch.run_id, outcome)
        answered = outcome in ("done", "step_cap")
        self._resolve(done_ids, HandoffResult(status="done", text=result.reply, tainted=result.tainted,
                                              link_scope=result.link_scope)
                      if answered else HandoffResult(status="failed"))
        await self._after_run(user_id, batch, inputs, result, outcome)

    async def _run_steered(
        self, user_id: str, batch: ClaimedBatch, inputs: RunInputs, steer: RunSteer,
    ) -> tuple[ClaimedBatch, RunInputs, TurnResult, RunOutcome]:
        """Run the batch; a run that did nothing yet and got new messages starts over under the SAME run id
        with them (one run per turn), keeping its steer (so a Stop pressed meanwhile still holds)."""
        while True:
            try:
                result, outcome = await self._execute(user_id, batch.bot, batch.thread_id, replace(inputs, steer=steer))
                return batch, inputs, result, outcome
            except RunRestart as restart:
                steer.restarted()
                batch = replace(batch, items=(*batch.items, *restart.items))
                inputs = await self._inputs(user_id, batch)

    async def _after_run(
        self, user_id: str, batch: ClaimedBatch, inputs: RunInputs, result: TurnResult, outcome: RunOutcome,
    ) -> None:
        if self._plan is not None:
            await self._plan.flush_run_note(user_id, batch.bot.id, batch.thread_id, batch.run_id)
        if self._signin is not None:
            await self._signin.after_run(user_id, batch.bot.id)
        await self._domain.finish_run(user_id, batch.bot.id, batch.run_id)
        if self._routines is not None:
            await self._routines.after_run(user_id, batch, result, outcome)
        if self._lessons is not None:   # nobody waits for a lesson: it runs on its own (it skips non-chat runs)
            self._background.spawn(self._lessons.after_run(lesson_run(user_id, batch, inputs)),
                                   name=f"lesson after run {batch.run_id}")
        if self._memory is None:
            return
        capture = self._memory.after_run(FinishedRun(
            user_id=user_id, bot_id=batch.bot.id, thread_id=batch.thread_id, items=batch.items,
            in_room=inputs.room is not None, tainted=result.tainted, answered=outcome in ("done", "step_cap"),
            blocked=result.block is not None,
        ))
        if inputs.call:
            # A call's next turn must not wait for the worker model: the capture runs on its own.
            self._background.spawn(capture, name=f"memory after call turn {batch.run_id}")
            return
        await capture

    async def _execute(
        self, user_id: str, bot: Bot, thread_id: str, inputs: RunInputs,
    ) -> tuple[TurnResult, RunOutcome]:
        inputs = replace(inputs, helpers=self._helper_tools(user_id, bot, thread_id, inputs))
        self.note_run_user(user_id, bot.id)
        try:
            async with asyncio.timeout(MAX_RUN_SECONDS):
                result = await run_one_turn(
                    user_id=user_id, bot=bot, thread_id=thread_id, bots=self._bots, talk=self._talk,
                    events=self._events, desk=self._desks.for_bot(bot.id, bot.computer), model=self._model,
                    activity=self._activity, gate=self._gate, inputs=inputs,
                    seen_ids=await self._seen_models.ids(), seen_models=self._seen_models,
                )
            outcome: RunOutcome = "stopped" if result.stopped else "step_cap" if result.capped else "done"
            if result.block is not None or result.parked is not None or result.plan:
                await keep_sites(self._queue, user_id, inputs.items, result.own_sites)   # the run after the card
            # D-A5: the card exists before the status settles below, so the bot settles to Stuck.
            await self._on_block(user_id, bot.id, thread_id, inputs.items, result, computer=bot.computer)
            await self._on_park(user_id, bot.id, thread_id, inputs.items, result)
        except RunRestart:
            raise   # the run starts over (``_run_steered``): no notice, and the bot stays On it
        except TimeoutError:
            logger.warning("Turn timed out after %ss for bot %s thread %s", MAX_RUN_SECONDS, bot.id, thread_id)
            await post_notice(self._talk, self._events, user_id, thread_id, _TIMEOUT_TEXT)
            result, outcome = EMPTY_RESULT, "time_cap"
        except ModelUnreachable as exc:
            logger.warning("The model was unreachable for bot %s thread %s: %s", bot.id, thread_id, exc)
            await post_notice(self._talk, self._events, user_id, thread_id, _UNREACHABLE_TEXT)
            result, outcome = EMPTY_RESULT, "error"
        except Exception:
            logger.exception("Unhandled error during turn for bot %s thread %s", bot.id, thread_id)
            await post_notice(self._talk, self._events, user_id, thread_id, _ERROR_TEXT)
            result, outcome = EMPTY_RESULT, "error"
        await self._settle_status(user_id, bot.id)
        return result, outcome

    async def _on_block(
        self, user_id: str, bot_id: str, thread_id: str, items: tuple[WorkItem, ...], result: TurnResult,
        *, computer: str = "mac_brave",
    ) -> None:
        """D-A5: a chat run that ended on a block leaves a Stuck card: a row,
        a ``kind="stuck"`` bot message and a ``stuck_card`` frame. Rung 4: a
        continue run blocked again by the same kind of block (same site, same
        reason; R12) opens no new card. That card becomes blocked and the bot
        names what it didn't finish. Any other block, such as a different wall on
        the same site, the bot asking for help, or any block after the user did
        the step in their main Brave (R13), opens a new card with the first
        request. A run blocked while another of the bot's cards is open opens no
        card of its own: it shows that card and says what it didn't finish."""
        if result.block is None:
            return
        block, sign_in = sign_in_block_for(result.block, computer)   # a Linux bot's sign-in: the Sign-in card
        prior = await self._answered_card(user_id, items)
        if prior is not None and prior.is_met_again_by(block):
            await self._block_card(user_id, prior)
            return
        draft = CardDraft(
            bot_id=bot_id, thread_id=thread_id, work_item_id=items[0].id if items else None, block=block,
            request=prior.request if prior is not None else _request_text(items), tainted=result.tainted,
            sign_in=sign_in,
        )
        card = await self._stuck.open(user_id, draft)
        # One open card per bot: while an older card is open, open() returns it. It is shown in THIS
        # run's chat, so a run blocked in another chat never ends there with nothing said.
        shown = replace(card, thread_id=thread_id)
        if card.work_item_id != draft.work_item_id:
            await self._say_already_waiting(user_id, shown, draft)
        await post_bot_line(self._talk, self._events, user_id, shown, stuck_message_body(card), kind="stuck")
        await publish_card(self._events, user_id, card)

    async def _on_park(
        self, user_id: str, bot_id: str, thread_id: str, items: tuple[WorkItem, ...], result: TurnResult,
    ) -> None:
        """A chat run that ended on a step that asked leaves an Ask card; one that ended with plan steps and
        no ask leaves one Proposal card. An ask in the same run wins and its plan steps are dropped, with a
        line saying so. Each card is a row, a ``kind="approval"`` bot message and an ``approval_card`` frame.
        One open card per bot: an older one is closed as expired first, and its frame says so."""
        wiring = self._approvals
        if wiring is None or (result.parked is None and not result.plan):
            return
        if result.parked is not None:
            if result.plan:
                await post_notice(self._talk, self._events, user_id, thread_id, PLAN_WAITS_LINE)
            steps, kind, offer = (result.parked,), "ask", result.parked.session_offer
        else:
            steps, kind, offer = result.plan, "plan", False
        draft = ApprovalDraft(
            bot_id=bot_id, thread_id=thread_id, work_item_id=items[0].id if items else None, kind=kind,
            steps=steps, request=_request_text(items), tainted=result.tainted, session_offer=offer,
        )
        await self._open_card(user_id, bot_id, draft)

    async def _open_card(self, user_id: str, bot_id: str, draft: ApprovalDraft) -> None:
        wiring = self._approvals
        older = await wiring.store.open_for_bot(user_id, bot_id)
        try:
            card = await wiring.store.open(user_id, draft)
        except (CardTooBig, ValueError):
            logger.warning("Could not open an approval card for bot %s", bot_id)
            return
        if older is not None:
            expired = await wiring.store.get(user_id, older.id)
            if expired is not None:
                await approval_announce.publish_card(self._events, user_id, expired)
        await approval_announce.post_card_message(self._talk, self._events, user_id, card)
        await approval_announce.publish_card(self._events, user_id, card)

    async def _say_already_waiting(self, user_id: str, shown: StuckCard, draft: CardDraft) -> None:
        """This run's own block opened no card (an older one is open), so its task is not
        dropped silently: the bot names the card it waits on and what it didn't finish."""
        said = replace(shown, tainted=shown.tainted or draft.tainted)
        await post_bot_line(self._talk, self._events, user_id, said,
                            already_waiting_line(shown.host, draft.request), kind="text")

    async def _answered_card(self, user_id: str, items: Sequence[WorkItem]) -> StuckCard | None:
        """The card a claimed continue item answers (its ``answer_item_id``), if any."""
        for item in items:
            if item.kind is not WorkKind.CARD_ANSWER:
                continue
            card = await self._stuck.card_for_answer(user_id, item.id)
            if card is not None:
                return card
        return None

    async def _block_card(self, user_id: str, prior: StuckCard) -> None:
        """Rung 4, never an empty result: the card says Blocked and the bot says what it didn't finish."""
        card = await self._stuck.mark_blocked(user_id, prior.id) or prior
        await post_bot_line(self._talk, self._events, user_id, card, blocked_line(card.host, card.request),
                            kind="text")
        await publish_card(self._events, user_id, card)

    async def _settle_status(self, user_id: str, bot_id: str) -> None:
        bot = await self._bots.get(user_id, bot_id)
        if bot is None:
            self._stuck_bots = self._stuck_bots - {bot_id}
            return
        status, card = await self._idle_status(user_id, bot)
        self._activity.set(bot_id, None)
        await self._bots.set_status(user_id, bot_id, status)
        await self._events.publish(user_id, self._status_frame(bot, status, card))

    def _status_frame(self, bot: Bot, status: BotStatus, card: StuckCard | None) -> dict[str, Any]:
        """The ``bot_status`` frame a settle publishes. A Stuck frame always carries ``stuck_status_line(card)``
        (the reason and the next step), whether the stay begins now, the bot was Stuck before its run, or this
        is a settle or a restart. The face announces a stay once by itself, from the status change."""
        frame: dict[str, Any] = {"type": "bot_status", "bot_id": bot.id, "status": status.value, "activity": None}
        if status is not BotStatus.STUCK:
            self._stuck_bots = self._stuck_bots - {bot.id}
            return frame
        self._stuck_bots = self._stuck_bots | {bot.id}
        return {**frame, "activity": stuck_status_line(card)} if card is not None else frame

    async def _idle_status(self, user_id: str, bot: Bot) -> tuple[BotStatus, StuckCard | None]:
        """Off duty first; then Stuck while one of its Stuck cards is open (R9); then Asking you while an Ask
        card is open; else Resting."""
        if bot.off_duty:
            return BotStatus.OFF_DUTY, None
        card = await self._stuck.open_for_bot(user_id, bot.id)
        if card is not None:
            return BotStatus.STUCK, card
        if self._approvals is not None and await self._approvals.store.open_for_bot(user_id, bot.id) is not None:
            return BotStatus.ASKING_YOU, None
        return BotStatus.RESTING, None
