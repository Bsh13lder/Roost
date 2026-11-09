"""``LessonService``: after a run of your own chat that went wrong, at most one Skill card (lessons plan §1, §3).

``after_run`` always takes the run's signals and step lines (so nothing waits in memory), then checks L4: your own
1:1 chat (messages and card answers only; never a room, a call, a routine, a handoff or a room post), at least one
signal, your own untainted words, and fewer than ``LESSONS_PER_DAY_PER_BOT`` lessons today. The worker is asked once
with trusted text only (``prompt.py``); its lesson is checked like a bot's ``propose_skill`` / ``propose_skill_change``
(name free, the skill clean and on for this bot) and posted through ``SkillProposalService.propose`` untainted. It
never raises: a lesson problem must not touch the run that just finished."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from roost.lessons.constants import (
    LESSON_AGENT, LESSON_ASKING_PHRASES, LESSON_OWNER_CHARS_MAX, LESSON_SKILLS_MAX, LESSON_TIMEOUT_S,
    LESSONS_PER_DAY_PER_BOT,
)
from roost.computer_use.reruns import card_signal_key
from roost.lessons.declined import DeclinedCards, ItemReader, answered_cards, declined_in_run, parked_items
from roost.lessons.parse import Lesson, LessonCreate, parse_lesson
from roost.lessons.prompt import LESSON_SYSTEM, lesson_input
from roost.lessons.signals import LessonSignal, LessonSignals
from roost.lessons.steps import LessonSteps
from roost.llm.types import Model
from roost.memory.worker import ask_worker
from roost.skills.models import Skill, SkillProposal, SkillProposalPayload
from roost.skills.proposals import ProposalRequest, SkillProposalRefused, SkillProposalService
from roost.skills.service import SkillService
from roost.work.models import ORIGIN_YOU, WorkItem, WorkKind
from roost.work.runs import madrid_today

logger = logging.getLogger(__name__)

_CHAT_KINDS = frozenset({WorkKind.MESSAGE, WorkKind.CARD_ANSWER})


@dataclass(frozen=True)
class FinishedLessonRun:
    user_id: str
    bot_id: str
    thread_id: str
    run_id: str
    items: tuple[WorkItem, ...]
    in_room: bool
    call: bool


def lesson_run(user_id: str, batch: Any, inputs: Any) -> FinishedLessonRun:
    """The runner's finished batch (``ClaimedBatch``) and its ``RunInputs`` as a lesson's run."""
    return FinishedLessonRun(user_id=user_id, bot_id=batch.bot.id, thread_id=batch.thread_id, run_id=batch.run_id,
                             items=batch.items, in_room=inputs.room is not None, call=bool(inputs.call))


def chat_run(run: FinishedLessonRun) -> bool:
    """L4: your own 1:1 chat only, never a room, a call, a routine, a handoff or a room post."""
    return (not run.in_room and not run.call and bool(run.items)
            and all(item.kind in _CHAT_KINDS for item in run.items))


def owner_words(items: tuple[WorkItem, ...]) -> str:
    """Your own untainted messages, each once, the newest kept when they are long."""
    mine = {i.id: i.body for i in items if i.kind is WorkKind.MESSAGE and i.origin == ORIGIN_YOU and not i.tainted}
    return "\n".join(body for body in mine.values() if body.strip())[-LESSON_OWNER_CHARS_MAX:]


def _merged(*groups: tuple[LessonSignal, ...]) -> tuple[LessonSignal, ...]:
    merged = LessonSignals()
    for signal in (s for group in groups for s in group):
        merged.record("run", signal)
    return merged.take("run")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def teaches_asking(payload: SkillProposalPayload) -> bool:
    """A lesson whose words teach the bot to stop and ask you (owner, 2026-11-07: only paying asks)."""
    words = " ".join(part or "" for part in (payload.name, payload.use_when, payload.body)).lower()
    return any(phrase in words for phrase in LESSON_ASKING_PHRASES)


def written_on(skill: Skill, day: str) -> bool:
    """The skill was created or changed on this local day (a lesson changes one skill at most once a day)."""
    try:
        return madrid_today(datetime.fromisoformat(skill.updated_at)) == day
    except ValueError:
        return False


class LessonService:
    def __init__(
        self, *, signals: LessonSignals, steps: LessonSteps, skills: SkillService, proposals: SkillProposalService,
        worker: Model, approvals: DeclinedCards | None = None, queue: ItemReader | None = None,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._signals = signals
        self._steps = steps
        self._skills = skills
        self._proposals = proposals
        self._worker = worker
        self._approvals = approvals
        self._queue = queue
        self._clock = clock
        self._posted: dict[tuple[str, str, str], int] = {}    # (user, bot, local day) -> lessons posted

    async def after_run(self, run: FinishedLessonRun) -> SkillProposal | None:
        signals, steps = self._signals.take(run.run_id), self._steps.take(run.run_id)
        if not chat_run(run):
            return None
        try:
            cards = await answered_cards(self._approvals, run.user_id, run.items)
            signals = _merged(signals, *(self._signals.take(card_signal_key(card.id)) for card in cards))
            parked = await parked_items(self._queue, run.user_id, run.thread_id, cards)
            return await self._lesson(run, signals, steps, parked)
        except asyncio.CancelledError:
            raise
        except Exception as exc:     # ids and the type only: a message may repeat your words
            logger.warning("A lesson failed for user %s bot %s run %s: %s",
                           run.user_id, run.bot_id, run.run_id, type(exc).__name__)
            return None

    async def _lesson(self, run: FinishedLessonRun, signals: tuple[LessonSignal, ...],
                      steps: tuple[str, ...], parked: tuple[WorkItem, ...]) -> SkillProposal | None:
        declined = await declined_in_run(self._approvals, self._queue, run.user_id, run.thread_id, run.items)
        signals = _merged(signals, declined.signals)
        words = owner_words((*parked, *declined.items, *run.items))
        key = (run.user_id, run.bot_id, madrid_today(self._clock()))
        if not signals or not words or self._posted.get(key, 0) >= LESSONS_PER_DAY_PER_BOT:
            return None
        skills = await self._clean_skills(run)
        reply = await ask_worker(self._worker, agent=LESSON_AGENT, system=LESSON_SYSTEM, timeout_s=LESSON_TIMEOUT_S,
                                 text=lesson_input(words, steps, signals, [(s.name, s.use_when) for s in skills]))
        lesson = parse_lesson(reply)
        request = await self._request(run, lesson, skills) if lesson is not None else None
        if request is None or teaches_asking(request.payload):
            return None
        try:
            proposal = await self._proposals.propose(request)
        except SkillProposalRefused:
            logger.info("A lesson was refused for user %s bot %s (open proposals or a full list)",
                        run.user_id, run.bot_id)
            return None
        self._posted = {**{k: v for k, v in self._posted.items() if k[2] == key[2]}, key: self._posted.get(key, 0) + 1}
        return proposal

    async def _clean_skills(self, run: FinishedLessonRun) -> tuple[Skill, ...]:
        on = await self._skills.on_for_bot(run.user_id, run.bot_id)
        return tuple(s for s in on if not s.tainted)[:LESSON_SKILLS_MAX]

    async def _request(self, run: FinishedLessonRun, lesson: Lesson,
                       skills: tuple[Skill, ...]) -> ProposalRequest | None:
        """The checks of ``propose_skill`` / ``propose_skill_change``: a new name is free; a change names a clean
        skill on for this bot."""
        if isinstance(lesson, LessonCreate):
            draft = lesson.draft
            if await self._skills.find(run.user_id, draft.name) is not None:
                return None
            payload = SkillProposalPayload(name=draft.name, use_when=draft.use_when, body=draft.body)
            return self._proposal(run, "create", payload, None)
        skill = await self._skills.find(run.user_id, lesson.skill)
        if skill is None or skill.id not in {s.id for s in skills} or written_on(skill, madrid_today(self._clock())):
            return None
        payload = SkillProposalPayload(**lesson.patch.model_dump(exclude_none=True))
        return self._proposal(run, "change", payload, skill)

    @staticmethod
    def _proposal(run: FinishedLessonRun, action: Any, payload: SkillProposalPayload,
                  skill: Skill | None) -> ProposalRequest:
        return ProposalRequest(user_id=run.user_id, bot_id=run.bot_id, action=action, payload=payload,
                               thread_id=run.thread_id, tainted=False, from_routine=False, skill=skill)
