"""Teach a task: start (takes control), record steps while teaching, stop (a skill proposal, or discard).

Only the person starts or stops teaching, over HTTP; no model tool reaches this. A teach session lives exactly as
long as the hold that started it: ``start`` takes control and keeps that hold's ``ControlLock.epoch``, and steps
are recorded only while that same hold is on. Giving the computer back any other way (I'm done, the Stuck card, a
gateway restart) stops recording at once, and the next ``status`` read or ``end`` throws the log away, so a later
ordinary Take control (a bank, webmail) is never recorded. A stop first stops recording, then drafts, proposes
(always marked from web content: titles and labels are web content), and only then deletes the log and gives the
computer back. A refused proposal keeps the log and arms recording again, so nothing you showed is lost."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from roost.bots.models import Bot
from roost.desk.control import ControlLock
from roost.llm.types import Model
from roost.skills.models import SkillProposalPayload
from roost.skills.proposals import ProposalRequest, SkillProposalRefused, SkillProposalService
from roost.talk.store import TalkStore
from roost.teach import texts
from roost.teach.draft import make_draft
from roost.teach.models import TeachOutcome, TeachRefused, TeachSession, TeachStep
from roost.teach.store import TeachStore
from roost.usage.scope import UsageRecorder, background_scope

_LINUX = "linux"


class NotTeaching(LookupError):
    """No teach session for this bot (or not the user's)."""


@dataclass(frozen=True)
class _Armed:
    user_id: str
    epoch: int          # the ControlLock epoch of the hold that started teaching


@dataclass(frozen=True)
class TeachStatus:
    teaching: bool
    steps: int
    capped: bool
    started_at: str | None


def _status(session: TeachSession | None) -> TeachStatus:
    if session is None:
        return TeachStatus(False, 0, False, None)
    return TeachStatus(True, len(session.steps), session.capped, session.started_at)


class TeachService:
    def __init__(self, store: TeachStore, proposals: SkillProposalService, talk: TalkStore, control: ControlLock,
                 worker: Model, usage: UsageRecorder | None = None) -> None:
        self._usage = usage     # token usage: the draft counts as the bot's background work
        self._store = store
        self._proposals = proposals
        self._talk = talk
        self._control = control
        self._worker = worker
        self._recording: Mapping[str, _Armed] = MappingProxyType({})     # bot id -> who and which hold
        self._locks: dict[str, asyncio.Lock] = {}

    def recording(self, bot_id: str) -> bool:
        """True only while the hold that started teaching is still on."""
        armed = self._recording.get(bot_id)
        return armed is not None and self._control.held(bot_id) is not None \
            and self._control.epoch(bot_id) == armed.epoch

    def _arm(self, bot_id: str, user_id: str) -> None:
        armed = _Armed(user_id, self._control.epoch(bot_id))
        self._recording = MappingProxyType({**self._recording, bot_id: armed})

    def _disarm(self, bot_id: str) -> None:
        self._recording = MappingProxyType({k: v for k, v in self._recording.items() if k != bot_id})

    def _lock(self, bot_id: str) -> asyncio.Lock:
        return self._locks.setdefault(bot_id, asyncio.Lock())

    async def status(self, user_id: str, bot_id: str) -> TeachStatus:
        """A log whose hold has ended (given back elsewhere, or a restart) is thrown away here."""
        async with self._lock(bot_id):
            session = await self._store.get(user_id, bot_id)
            if session is not None and not self.recording(bot_id):
                await self._drop(user_id, bot_id)
                session = None
        return _status(session)

    async def end(self, user_id: str, bot_id: str) -> None:
        """The computer was given back some other way: the recording, if any, is thrown away."""
        async with self._lock(bot_id):
            await self._drop(user_id, bot_id)

    async def start(self, user_id: str, bot: Bot) -> TeachStatus:
        """A fresh recording on the bot's Linux computer, and Take control."""
        if bot.computer != _LINUX:
            raise TeachRefused(texts.LINUX_ONLY)
        async with self._lock(bot.id):
            self._control.take(bot.id)
            session = await self._store.begin(user_id, bot.id)
            self._arm(bot.id, user_id)
        return _status(session)

    async def record(self, bot_id: str, step: TeachStep) -> bool:
        """Keep one step while the bot is being taught. False when it is not, or the step was not kept."""
        armed = self._recording.get(bot_id)
        if armed is None or not self.recording(bot_id):
            return False
        async with self._lock(bot_id):
            if not self.recording(bot_id):
                return False
            return await self._store.append(armed.user_id, bot_id, step)

    async def stop(self, user_id: str, bot_id: str, description: str | None, *, discard: bool) -> TeachOutcome:
        async with self._lock(bot_id):
            session = await self._store.get(user_id, bot_id)
            if session is None:
                raise NotTeaching(bot_id)
            if discard:
                await self._finish(user_id, bot_id)
                return TeachOutcome(None, len(session.steps), True)
            if not session.steps:
                raise TeachRefused(texts.NOTHING_RECORDED)
            self._disarm(bot_id)
            try:
                proposal_id = await self._propose(session, description)
            except BaseException:
                self._arm(bot_id, user_id)
                raise
            await self._finish(user_id, bot_id)
        return TeachOutcome(proposal_id, len(session.steps), False)

    async def _propose(self, session: TeachSession, description: str | None) -> str:
        with background_scope(self._usage, session.user_id, session.bot_id):
            draft = await make_draft(self._worker, session.steps, description)
        thread, _ = await self._talk.ensure_main_thread(session.user_id, session.bot_id)
        payload = SkillProposalPayload(name=draft.name, use_when=draft.use_when, body=draft.body)
        try:
            proposal = await self._proposals.propose(ProposalRequest(
                user_id=session.user_id, bot_id=session.bot_id, action="create", payload=payload,
                thread_id=thread.id, tainted=True, from_routine=False))
        except SkillProposalRefused as refused:
            raise TeachRefused(refused.text) from None
        return proposal.id

    async def _drop(self, user_id: str, bot_id: str) -> None:
        await self._store.delete(user_id, bot_id)
        self._disarm(bot_id)

    async def _finish(self, user_id: str, bot_id: str) -> None:
        await self._drop(user_id, bot_id)
        self._control.give_back(bot_id)
