"""Skill proposals: the card a bot raises instead of writing a skill (Skills design §3).

``propose_skill`` and ``propose_skill_change`` never write a skill. They store a sealed ``SkillProposalPayload``
(``skill_proposals:payload``) and post a ``skill_proposal`` card; only the user's Save skill
(``POST /api/skill-proposals/{id}/save``) makes the server write it. A proposal remembers whether it came from a
tainted run or a routine's run, and a skill saved from a tainted proposal keeps ``tainted`` (only the user's editor
save clears it). A change remembers the skill's revision: Save is a compare-and-swap on it. Every statement names
``user_id``; another user's proposal is "no such proposal"."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.constants import SKILL_PROPOSALS_OPEN_PER_BOT_MAX, SKILLS_PER_USER_MAX
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.events.hub import EventHub
from roost.skills.models import ProposalAction, Skill, SkillDraft, SkillPatch, SkillProposal, SkillProposalPayload
from roost.skills.service import NoSuchSkill, SkillConflict, SkillRefused, SkillService
from roost.skills.texts import NOT_OPEN, SKILLS_FULL, STALE, TOO_MANY_OPEN
from roost.talk.store import TalkStore, message_out

_COLUMNS = ("id, user_id, bot_id, skill_id, action, payload, base_revision, tainted, from_routine, state, thread_id, "
            "message_id, created_at, decided_at")
_FIELDS = ("name", "use_when", "body")
PROPOSALS_CHANGED = "skill_proposals_changed"
MESSAGE_KIND = "skill_proposal"


class NoSuchSkillProposal(LookupError):
    """The proposal is not there, or not the user's."""


class SkillProposalRefused(ValueError):
    """A proposal that can't be made or saved; ``text`` is a plain sentence."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


class SkillProposalClosed(RuntimeError):
    """Another press decided it first (409)."""


@dataclass(frozen=True)
class SkillProposalView:
    proposal: SkillProposal
    skill_name: str | None           # the name the card shows (a new skill's, or the changed skill's current one)
    diff: tuple[dict, ...]           # [{field, before, after}] for a change


@dataclass(frozen=True)
class ProposalRequest:
    """One proposal from a run: what, for which bot, from which thread, and the run's marks."""
    user_id: str
    bot_id: str
    action: ProposalAction
    payload: SkillProposalPayload
    thread_id: str
    tainted: bool
    from_routine: bool
    skill: Skill | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str) -> bytes:
    return user_aad(user_id, "skill_proposals:payload")


def _to_proposal(row: aiosqlite.Row, dek: bytes) -> SkillProposal:
    user_id = row["user_id"]
    raw = decrypt_field(row["payload"], dek, _aad(user_id)) or "{}"
    return SkillProposal(
        id=row["id"], user_id=user_id, bot_id=row["bot_id"], skill_id=row["skill_id"], action=row["action"],
        payload=SkillProposalPayload.model_validate_json(raw), base_revision=row["base_revision"],
        tainted=bool(row["tainted"]), from_routine=bool(row["from_routine"]), state=row["state"],
        thread_id=row["thread_id"], message_id=row["message_id"], created_at=row["created_at"],
        decided_at=row["decided_at"])


class SkillProposalStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def create(self, request: ProposalRequest) -> SkillProposal:
        user_id = request.user_id
        dek = await get_user_dek(self._config, user_id)
        proposal_id = str(uuid4())
        skill = request.skill
        sealed = encrypt_field(request.payload.model_dump_json(exclude_none=True), dek, _aad(user_id))
        async with db_session(self._config) as db:
            await db.execute(
                f"INSERT INTO skill_proposals ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,'open',?,NULL,?,NULL)",
                (proposal_id, user_id, request.bot_id, skill.id if skill else None, request.action, sealed,
                 skill.revision if skill else None, int(request.tainted), int(request.from_routine),
                 request.thread_id, _now()))
            await db.commit()
        found = await self.get(user_id, proposal_id)
        if found is None:
            raise RuntimeError("The proposal could not be read back.")
        return found

    async def get(self, user_id: str, proposal_id: str) -> SkillProposal | None:
        found = await self._select(user_id, "AND id = ?", (proposal_id,))
        return found[0] if found else None

    async def list_open(self, user_id: str) -> tuple[SkillProposal, ...]:
        return await self._select(user_id, "AND state = 'open' ORDER BY created_at, rowid", ())

    async def count_open(self, user_id: str, bot_id: str) -> int:
        async with db_session(self._config) as db:
            row = await (await db.execute(
                "SELECT COUNT(*) FROM skill_proposals WHERE user_id = ? AND bot_id = ? AND state = 'open'",
                (user_id, bot_id))).fetchone()
        return int(row[0])

    async def set_message(self, user_id: str, proposal_id: str, message_id: str) -> None:
        async with db_session(self._config) as db:
            await db.execute("UPDATE skill_proposals SET message_id = ? WHERE id = ? AND user_id = ?",
                             (message_id, proposal_id, user_id))
            await db.commit()

    async def decide(self, user_id: str, proposal_id: str, state: str, *, expected: str = "open") -> SkillProposal | None:
        """Compare-and-set ``expected`` -> ``state``. ``None`` when it is not the user's or already decided."""
        decided = _now() if state != "open" else None
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE skill_proposals SET state = ?, decided_at = ? WHERE id = ? AND user_id = ? AND state = ?",
                (state, decided, proposal_id, user_id, expected))
            await db.commit()
        return await self.get(user_id, proposal_id) if cursor.rowcount == 1 else None

    async def _select(self, user_id: str, extra: str, params: tuple) -> tuple[SkillProposal, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {_COLUMNS} FROM skill_proposals WHERE user_id = ? {extra}", (user_id, *params))).fetchall()
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_to_proposal(row, dek) for row in rows)


class SkillProposalService:
    """Propose, list, save and decline. Save writes through ``SkillService``, the editor's own door."""

    def __init__(self, store: SkillProposalStore, skills: SkillService, talk: TalkStore, events: EventHub) -> None:
        self._store = store
        self._skills = skills
        self._talk = talk
        self._events = events

    async def propose(self, request: ProposalRequest) -> SkillProposal:
        """Store a sealed proposal and post its card. ``SkillProposalRefused`` past the open cap or a full list."""
        if await self._store.count_open(request.user_id, request.bot_id) >= SKILL_PROPOSALS_OPEN_PER_BOT_MAX:
            raise SkillProposalRefused(TOO_MANY_OPEN)
        if request.action == "create" and len(await self._skills.list(request.user_id)) >= SKILLS_PER_USER_MAX:
            raise SkillProposalRefused(SKILLS_FULL)
        proposal = await self._store.create(request)
        name = request.payload.name if request.action == "create" else (request.skill.name if request.skill else "")
        await self._post_card(proposal, name or "")
        await self._changed(proposal)
        return proposal

    async def list_open(self, user_id: str) -> tuple[SkillProposalView, ...]:
        return tuple([await self.view(user_id, p) for p in await self._store.list_open(user_id)])

    async def get(self, user_id: str, proposal_id: str) -> SkillProposalView:
        proposal = await self._store.get(user_id, proposal_id)
        if proposal is None:
            raise NoSuchSkillProposal(proposal_id)
        return await self.view(user_id, proposal)

    async def save(self, user_id: str, proposal_id: str) -> SkillProposalView:
        """Of two presses exactly one wins. On any refusal the proposal is open again."""
        proposal = await self._store.decide(user_id, proposal_id, "saved")
        if proposal is None:
            await self._missing_or_closed(user_id, proposal_id)
        try:
            await self._apply(proposal)
        except BaseException:
            await self._store.decide(user_id, proposal_id, "open", expected="saved")
            raise
        await self._changed(proposal)
        return await self.view(user_id, proposal)

    async def decline(self, user_id: str, proposal_id: str) -> SkillProposalView:
        proposal = await self._store.decide(user_id, proposal_id, "declined")
        if proposal is None:
            await self._missing_or_closed(user_id, proposal_id)
        await self._changed(proposal)
        return await self.view(user_id, proposal)

    async def view(self, user_id: str, proposal: SkillProposal) -> SkillProposalView:
        if proposal.action == "create":
            return SkillProposalView(proposal, proposal.payload.name, ())
        current = await self._skills.store.get(user_id, proposal.skill_id) if proposal.skill_id else None
        if current is None:
            return SkillProposalView(proposal, None, ())
        return SkillProposalView(proposal, current.name, _diff(current, proposal.payload))

    async def _apply(self, proposal: SkillProposal) -> None:
        payload = proposal.payload
        try:
            if proposal.action == "create":
                draft = SkillDraft(name=payload.name or "", use_when=payload.use_when or "", body=payload.body or "")
                await self._skills.add(proposal.user_id, draft, origin="bot", tainted=proposal.tainted,
                                       created_by_bot=proposal.bot_id)
                return
            await self._apply_change(proposal)
        except SkillRefused as refused:
            raise SkillProposalRefused(refused.text) from None

    async def _apply_change(self, proposal: SkillProposal) -> None:
        try:
            current = await self._skills.get(proposal.user_id, proposal.skill_id or "")
            if proposal.base_revision is None or current.revision != proposal.base_revision:
                raise SkillProposalRefused(STALE)
            patch = SkillPatch(**proposal.payload.model_dump(exclude_none=True))
            await self._skills.save(proposal.user_id, current.id, patch, base_revision=proposal.base_revision,
                                    tainted=current.tainted or proposal.tainted)
        except (NoSuchSkill, SkillConflict):
            raise SkillProposalRefused(STALE) from None

    async def _missing_or_closed(self, user_id: str, proposal_id: str):
        if await self._store.get(user_id, proposal_id) is None:
            raise NoSuchSkillProposal(proposal_id)
        raise SkillProposalClosed(NOT_OPEN)

    async def _post_card(self, proposal: SkillProposal, name: str) -> None:
        body = json.dumps({"proposal_id": proposal.id, "name": name})
        message = await self._card(proposal, proposal.thread_id, body)
        await self._store.set_message(proposal.user_id, proposal.id, message.id)
        main, _ = await self._talk.ensure_main_thread(proposal.user_id, proposal.bot_id)
        if main.id != proposal.thread_id:      # a routine's run log or a room: the bot's own chat shows it too
            await self._card(proposal, main.id, body)

    async def _card(self, proposal: SkillProposal, thread_id: str, body: str):
        message = await self._talk.add_message(proposal.user_id, thread_id, "bot", body, tainted=proposal.tainted,
                                               kind=MESSAGE_KIND, author_bot_id=proposal.bot_id)
        await self._events.publish(proposal.user_id, {"type": "message", "thread_id": thread_id,
                                                      "message": message_out(message)})
        return message

    async def _changed(self, proposal: SkillProposal) -> None:
        await self._events.publish(proposal.user_id, {"type": PROPOSALS_CHANGED, "bot_id": proposal.bot_id})


def _diff(current: Skill, payload: SkillProposalPayload) -> tuple[dict, ...]:
    return tuple({"field": field, "before": getattr(current, field), "after": getattr(payload, field)}
                 for field in _FIELDS
                 if getattr(payload, field) is not None and getattr(payload, field) != getattr(current, field))
