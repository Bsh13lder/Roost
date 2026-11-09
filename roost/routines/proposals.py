"""Routine proposals: the small card a bot raises instead of writing a routine itself (design §3.4).

``propose_routine``, ``propose_routine_change`` and ``propose_routine_pause`` never write a routine.
They store a sealed ``ProposalPayload`` and post a ``routine_proposal`` card; only the user's Approve
(``POST /api/routine-proposals/{id}/approve``, behind ``RequireOrigin``) makes the server write it. A proposal
remembers whether it came from a tainted run or from a routine's run, and a routine saved from a tainted proposal
keeps ``tainted``. Every query names ``user_id`` (another user's proposal is "no such proposal")."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import uuid4

import aiosqlite

from roost.config import RoostConfig
from roost.constants import ROUTINE_CARD_PREVIEW_COUNT, ROUTINE_PROPOSALS_OPEN_PER_BOT_MAX, ROUTINES_PER_BOT_MAX
from roost.crypto.encryption import decrypt_field, encrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.events.hub import EventHub
from roost.routines.models import Clock, Proposal, ProposalAction, ProposalPayload, Routine
from roost.routines.runs import iso, parse_iso, utc_now
from roost.routines.schedule import readable, upcoming
from roost.routines.store import RoutineStore
from roost.routines.watch_models import parse_watch, watch_summary
from roost.standing.models import PermissionIn
from roost.standing.service import PermissionRefused, check_window
from roost.work.runs import madrid_today
from roost.talk.store import TalkStore, message_out
from roost.timezones import local_tz

_COLUMNS = ("id, user_id, bot_id, routine_id, action, payload, tainted, from_routine, state, thread_id, message_id, "
            "created_at, decided_at")
PROPOSAL_TAINTED_MARK = "This run read outside content."
PROPOSAL_FROM_ROUTINE_MARK = "A routine asked to change a routine."
TOO_MANY_OPEN_TEXT = f"There are already {ROUTINE_PROPOSALS_OPEN_PER_BOT_MAX} routine proposals waiting for the user."
BOT_FULL_TEXT = f"This bot already has {ROUTINES_PER_BOT_MAX} routines."
NOT_OPEN_TEXT = "Try again: that proposal was already decided."
STALE_TEXT = "That routine changed or is gone, so this proposal no longer fits."


class NoSuchProposal(LookupError):
    """The proposal is not there, or not the user's."""


class ProposalRefused(ValueError):
    """A proposal that can't be made or applied; ``text`` is a plain sentence."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


class ProposalClosed(RuntimeError):
    """Another press decided it first (409)."""


PROPOSED = "proposed"    # approve: keep the standing permission the bot proposed, as it is
Permit = PermissionIn | None | Literal["proposed"]


def _aad(user_id: str) -> bytes:
    return user_aad(user_id, "routine_proposals:payload")


def _to_proposal(row: aiosqlite.Row, dek: bytes) -> Proposal:
    user_id = row["user_id"]
    raw = decrypt_field(row["payload"], dek, _aad(user_id), fallback="") or ""
    try:
        payload = ProposalPayload.model_validate_json(raw) if raw else None
    except ValueError:
        payload = None
    return Proposal(
        id=row["id"], user_id=user_id, bot_id=row["bot_id"], routine_id=row["routine_id"], action=row["action"],
        payload=payload, tainted=bool(row["tainted"]), from_routine=bool(row["from_routine"]), state=row["state"],
        thread_id=row["thread_id"], message_id=row["message_id"], created_at=parse_iso(row["created_at"]),
        decided_at=parse_iso(row["decided_at"]))


class ProposalStore:
    def __init__(self, config: RoostConfig, *, clock: Clock = utc_now) -> None:
        self._config = config
        self._clock = clock

    async def create(
        self, user_id: str, bot_id: str, action: ProposalAction, payload: ProposalPayload | None,
        *, routine_id: str | None, thread_id: str, tainted: bool, from_routine: bool,
    ) -> Proposal:
        dek = await get_user_dek(self._config, user_id)
        proposal_id = str(uuid4())
        sealed = encrypt(payload.model_dump_json() if payload is not None else "", dek, _aad(user_id))
        async with db_session(self._config) as db:
            await db.execute(
                f"INSERT INTO routine_proposals ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,'open',?,NULL,?,NULL)",
                (proposal_id, user_id, bot_id, routine_id, action, sealed, int(tainted), int(from_routine),
                 thread_id, iso(self._clock())))
            await db.commit()
        found = await self.get(user_id, proposal_id)
        assert found is not None
        return found

    async def get(self, user_id: str, proposal_id: str) -> Proposal | None:
        found = await self._select(user_id, "WHERE id = ? AND user_id = ?", (proposal_id, user_id))
        return found[0] if found else None

    async def list_open(self, user_id: str) -> tuple[Proposal, ...]:
        return await self._select(
            user_id, "WHERE user_id = ? AND state = 'open' ORDER BY created_at, rowid", (user_id,))

    async def count_open(self, user_id: str, bot_id: str) -> int:
        async with db_session(self._config) as db:
            row = await (await db.execute(
                "SELECT COUNT(*) FROM routine_proposals WHERE user_id = ? AND bot_id = ? AND state = 'open'",
                (user_id, bot_id))).fetchone()
        return int(row[0])

    async def set_message(self, user_id: str, proposal_id: str, message_id: str) -> None:
        async with db_session(self._config) as db:
            await db.execute("UPDATE routine_proposals SET message_id = ? WHERE id = ? AND user_id = ?",
                             (message_id, proposal_id, user_id))
            await db.commit()

    async def decide(self, user_id: str, proposal_id: str, state: str, *, expected: str = "open") -> Proposal | None:
        """Compare-and-set ``expected`` -> ``state``. ``None`` when it is not the user's or already decided."""
        decided = iso(self._clock()) if state != "open" else None
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE routine_proposals SET state = ?, decided_at = ? WHERE id = ? AND user_id = ? AND state = ?",
                (state, decided, proposal_id, user_id, expected))
            await db.commit()
            changed = cursor.rowcount == 1
        return await self.get(user_id, proposal_id) if changed else None

    async def _select(self, user_id: str, where: str, params: tuple) -> tuple[Proposal, ...]:
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_COLUMNS} FROM routine_proposals {where}", params)).fetchall()
        return tuple(_to_proposal(row, dek) for row in rows)


@dataclass(frozen=True)
class ProposalView:
    proposal: Proposal
    words: str
    next: tuple[str, ...]            # the next fires, local ISO
    diff: tuple[dict, ...]           # [{field, before, after}] for a change
    routine_name: str | None


class ProposalService:
    """Propose, list, approve and decline. ``writer`` (a ``RoutineService``) is only needed to approve."""

    def __init__(
        self, store: ProposalStore, routines: RoutineStore, talk: TalkStore, events: EventHub, writer=None,
        *, clock: Clock = utc_now, standing=None,
    ) -> None:
        self._standing = standing     # a PermissionService: stores a standing permission the user approves
        self._store = store
        self._routines = routines
        self._talk = talk
        self._events = events
        self._writer = writer
        self._clock = clock

    async def propose(
        self, user_id: str, bot_id: str, action: ProposalAction, payload: ProposalPayload | None,
        *, routine_id: str | None, thread_id: str, tainted: bool, from_routine: bool,
    ) -> Proposal:
        """Store a sealed proposal and post its card. Raises ``ProposalRefused`` past a cap or for a routine that
        is not this bot's."""
        if await self._store.count_open(user_id, bot_id) >= ROUTINE_PROPOSALS_OPEN_PER_BOT_MAX:
            raise ProposalRefused(TOO_MANY_OPEN_TEXT)
        if action == "create":
            if await self._routines.count_for_bot(user_id, bot_id) >= ROUTINES_PER_BOT_MAX:
                raise ProposalRefused(BOT_FULL_TEXT)
        else:
            await self._own_routine(user_id, bot_id, routine_id)
        proposal = await self._store.create(
            user_id, bot_id, action, payload, routine_id=routine_id, thread_id=thread_id, tainted=tainted,
            from_routine=from_routine)
        await self._post_card(user_id, proposal, also_main=from_routine)
        await self._events.publish(user_id, {"type": "proposals_changed", "bot_id": bot_id})
        return proposal

    async def list_open(self, user_id: str) -> tuple[ProposalView, ...]:
        return tuple([await self.view(user_id, p) for p in await self._store.list_open(user_id)])

    async def get(self, user_id: str, proposal_id: str) -> ProposalView:
        proposal = await self._store.get(user_id, proposal_id)
        if proposal is None:
            raise NoSuchProposal(proposal_id)
        return await self.view(user_id, proposal)

    async def approve(self, user_id: str, proposal_id: str, *, permission: Permit = PROPOSED) -> ProposalView:
        """Of two presses exactly one wins. The routine is written by the server, for the proposal's own bot.
        ``permission``: the standing permission to store with a new routine (the user's own Approve): the proposed
        one, one the user changed, or None. It is checked before anything is written."""
        current = await self._store.get(user_id, proposal_id)
        chosen = self._chosen_permission(current, permission) if current is not None else None
        proposal = await self._store.decide(user_id, proposal_id, "approved")
        if proposal is None:
            await self._missing_or_closed(user_id, proposal_id)
            raise AssertionError("unreachable")
        try:
            await self._apply(user_id, proposal, chosen)
        except Exception:
            await self._store.decide(user_id, proposal_id, "open", expected="approved")
            raise
        await self._events.publish(user_id, {"type": "proposals_changed", "bot_id": proposal.bot_id})
        return await self.view(user_id, proposal)

    async def decline(self, user_id: str, proposal_id: str) -> ProposalView:
        proposal = await self._store.decide(user_id, proposal_id, "declined")
        if proposal is None:
            await self._missing_or_closed(user_id, proposal_id)
            raise AssertionError("unreachable")
        await self._events.publish(user_id, {"type": "proposals_changed", "bot_id": proposal.bot_id})
        return await self.view(user_id, proposal)

    async def view(self, user_id: str, proposal: Proposal) -> ProposalView:
        now = self._clock()
        current = await self._routines.get(user_id, proposal.routine_id) if proposal.routine_id else None
        payload = proposal.payload
        if payload is None:
            return ProposalView(proposal, readable(current.schedule, now=now) if current else "", (), (),
                                current.name if current else None)
        fires = upcoming(payload.schedule, now, ROUTINE_CARD_PREVIEW_COUNT) if payload.watch is None else ()
        return ProposalView(
            proposal, _payload_words(payload, now),
            tuple(f.astimezone(local_tz()).isoformat(timespec="minutes") for f in fires),
            _diff(current, payload, now) if proposal.action == "change" and current else (),
            current.name if current else None)

    def _chosen_permission(self, proposal: Proposal, permission: Permit) -> PermissionIn | None:
        """The permission Approve will store: only for a new routine, inside its date window, with a store."""
        proposed = proposal.payload.permission if proposal.payload is not None else None
        chosen = proposed if permission == PROPOSED else permission
        if chosen is None or proposal.action != "create" or not isinstance(chosen, PermissionIn):
            return None
        if self._standing is None:
            raise ProposalRefused("Standing permissions are not available here.")
        try:
            check_window(chosen, date.fromisoformat(madrid_today(self._clock())))
        except PermissionRefused as refused:
            raise ProposalRefused(refused.text) from None
        return chosen

    async def _apply(self, user_id: str, proposal: Proposal, permission: PermissionIn | None = None) -> None:
        if self._writer is None:
            raise RuntimeError("ProposalService has no routine writer")
        payload = proposal.payload
        if proposal.action == "create" and payload is not None:
            routine = await self._writer.create(
                user_id, proposal.bot_id, payload.name, payload.instructions, payload.schedule.model_dump(),
                created_by="bot", tainted=proposal.tainted, watch=payload.watch)
            if permission is not None and self._standing is not None:
                await self._standing.add(user_id, routine.id, permission)
            return
        routine = await self._own_routine(user_id, proposal.bot_id, proposal.routine_id, stale=True)
        if proposal.action == "pause":
            await self._writer.update(user_id, routine.id, {"enabled": False})
        elif payload is not None:
            await self._writer.update(user_id, routine.id, {
                "name": payload.name, "instructions": payload.instructions,
                "schedule": payload.schedule.model_dump(), "watch": payload.watch},
                tainted=routine.tainted or proposal.tainted)

    async def _own_routine(self, user_id: str, bot_id: str, routine_id: str | None, *, stale: bool = False) -> Routine:
        routine = await self._routines.get(user_id, routine_id) if routine_id else None
        if routine is None or routine.bot_id != bot_id:
            raise ProposalRefused(STALE_TEXT if stale else "That isn't one of this bot's routines.")
        return routine

    async def _missing_or_closed(self, user_id: str, proposal_id: str) -> None:
        if await self._store.get(user_id, proposal_id) is None:
            raise NoSuchProposal(proposal_id)
        raise ProposalClosed(NOT_OPEN_TEXT)

    async def _post_card(self, user_id: str, proposal: Proposal, *, also_main: bool) -> None:
        body = json.dumps({"proposal_id": proposal.id})
        message = await self._card_message(user_id, proposal.thread_id, proposal.bot_id, body, proposal.tainted)
        await self._store.set_message(user_id, proposal.id, message.id)
        if also_main:
            main, _ = await self._talk.ensure_main_thread(user_id, proposal.bot_id)
            if main.id != proposal.thread_id:
                await self._card_message(user_id, main.id, proposal.bot_id, body, proposal.tainted)

    async def _card_message(self, user_id: str, thread_id: str, bot_id: str, body: str, tainted: bool):
        message = await self._talk.add_message(
            user_id, thread_id, "bot", body, tainted=tainted, kind="routine_proposal", author_bot_id=bot_id)
        await self._events.publish(user_id, {"type": "message", "thread_id": thread_id,
                                             "message": message_out(message)})
        return message


def _payload_words(payload: ProposalPayload, now: datetime) -> str:
    watch = parse_watch(payload.watch) if payload.watch is not None else None
    return watch_summary(watch) if watch is not None else readable(payload.schedule, now=now)


def _diff(current: Routine, payload: ProposalPayload, now: datetime) -> tuple[dict, ...]:
    before = {"name": current.name, "instructions": current.instructions,
              "schedule": readable(current.schedule, now=now), "watch": watch_summary(current.watch)}
    after = {"name": payload.name, "instructions": payload.instructions,
             "schedule": readable(payload.schedule, now=now),
             "watch": watch_summary(parse_watch(payload.watch) if payload.watch is not None else None)}
    return tuple({"field": field, "before": before[field], "after": after[field]}
                 for field in before if before[field] != after[field])
