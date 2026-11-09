"""Room domain model — frozen dataclasses only."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Room:
    id: str
    user_id: str
    name: str
    coordinator_id: str | None
    member_ids: tuple[str, ...]
    thread_id: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class RoomMember:
    id: str
    name: str
    job: str


@dataclass(frozen=True)
class RoomContext:
    """What a run in a room thread needs to know (spec §6.1: "where this run came from")."""

    room_id: str
    name: str
    members: tuple[RoomMember, ...]
    coordinator_id: str | None
