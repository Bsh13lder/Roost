"""``RoomService`` — creating rooms, routing posts, surviving retirements (D-E)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from roost.bots.models import Bot
from roost.bots.store import BotStore
from roost.rooms.mentions import parse_mentions, route_targets
from roost.rooms.models import Room
from roost.rooms.store import RoomStore
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from roost.work.models import WorkDraft, WorkKind, room_origin


class RoomRefused(ValueError):
    """A room can't be made as asked; ``str(exc)`` is the user-facing reason."""


@dataclass(frozen=True)
class PostReceipt:
    message_id: str
    routed_to: tuple[str, ...]


class RoomService:
    def __init__(self, bots: BotStore, talk: TalkStore, rooms: RoomStore, turns: TurnRunner) -> None:
        self._bots = bots
        self._talk = talk
        self._rooms = rooms
        self._turns = turns

    @property
    def rooms(self) -> RoomStore:
        return self._rooms

    async def create(self, user_id: str, name: str, member_ids: Sequence[str], coordinator_id: str | None = None) -> Room:
        if len(set(member_ids)) != len(member_ids):
            raise RoomRefused("Each bot can join a room once.")
        members = await self._load_members(user_id, member_ids)
        coordinator = await self._pick_coordinator(user_id, members, coordinator_id)
        thread = await self._talk.create_thread(user_id, coordinator.id, title=name, kind="room")
        return await self._rooms.create(user_id, name=name, member_ids=tuple(b.id for b in members),
                                        coordinator_id=coordinator.id, thread_id=thread.id)

    async def members(self, user_id: str, room: Room) -> tuple[Bot, ...]:
        bots = [await self._bots.get(user_id, bot_id) for bot_id in room.member_ids]
        return tuple(bot for bot in bots if bot is not None)

    async def post(self, user_id: str, room: Room, text: str) -> PostReceipt:
        members = await self.members(user_id, room)
        message = await self._talk.add_message(user_id, room.thread_id, role="user", body=text)
        targets = route_targets(parse_mentions(text, members), members, room.coordinator_id)
        for bot_id in targets:
            await self._turns.submit(user_id, WorkDraft(
                bot_id=bot_id, thread_id=room.thread_id, kind=WorkKind.ROOM_POST,
                origin=room_origin(room.name), body=text, message_id=message.id,
            ))
        return PostReceipt(message_id=message.id, routed_to=targets)

    async def on_bot_retiring(self, user_id: str, bot_id: str) -> None:
        """Call BEFORE deleting ``bot_id``: every room it coordinates gets a
        new coordinator (the main bot if it is a member, else the next
        member) and keeps its thread; a room left with no one goes away."""
        for room in await self._rooms.rooms_coordinated_by(user_id, bot_id):
            others = tuple(i for i in room.member_ids if i != bot_id)
            if not others:
                await self._rooms.delete(user_id, room.id)
                continue
            primary = await self._bots.get_primary(user_id)
            successor = primary.id if primary is not None and primary.id in others else others[0]
            await self._rooms.set_coordinator(user_id, room, successor)

    async def _load_members(self, user_id: str, member_ids: Sequence[str]) -> tuple[Bot, ...]:
        members: tuple[Bot, ...] = ()
        for bot_id in member_ids:
            bot = await self._bots.get(user_id, bot_id)
            if bot is None:
                raise RoomRefused("One of these bots isn't on your team.")
            if bot.off_duty:
                raise RoomRefused(f"{bot.name} is off duty.")
            members = (*members, bot)
        return members

    async def _pick_coordinator(self, user_id: str, members: tuple[Bot, ...], wanted: str | None) -> Bot:
        if wanted is not None:
            chosen = next((b for b in members if b.id == wanted), None)
            if chosen is None:
                raise RoomRefused("The coordinator must be one of the members.")
            return chosen
        return next((b for b in members if b.is_primary), members[0])
