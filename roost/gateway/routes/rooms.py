"""Rooms HTTP API (D-E, spec §11 step 17). A foreign or unknown room id is
404; a refused room is 422 with a plain-language ``detail``."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from roost.constants import (
    MAX_MESSAGE_TEXT_LENGTH, MAX_ROOM_NAME_LENGTH, MIN_MESSAGE_TEXT_LENGTH, ROOM_MAX_MEMBERS, ROOM_MIN_MEMBERS,
)
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.rooms.models import Room
from roost.rooms.service import RoomRefused
from roost.rooms.store import room_out
from roost.talk.store import message_out

rooms_router = APIRouter(prefix="/api/rooms", tags=["rooms"])


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_ROOM_NAME_LENGTH)
    member_ids: list[str] = Field(min_length=ROOM_MIN_MEMBERS, max_length=ROOM_MAX_MEMBERS)
    coordinator_id: str | None = None


class RoomPost(BaseModel):
    text: str = Field(min_length=MIN_MESSAGE_TEXT_LENGTH, max_length=MAX_MESSAGE_TEXT_LENGTH)


async def _room_or_404(request: Request, user_id: str, room_id: str) -> Room:
    room = await request.app.state.room_service.rooms.get(user_id, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


@rooms_router.get("")
async def list_rooms(request: Request, user: CurrentUser):
    return [room_out(room) for room in await request.app.state.room_service.rooms.list(user.id)]


@rooms_router.post("", status_code=201, dependencies=[RequireOrigin])
async def create_room(body: RoomCreate, request: Request, user: CurrentUser):
    try:
        room = await request.app.state.room_service.create(user.id, body.name, body.member_ids, body.coordinator_id)
    except RoomRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return room_out(room)


@rooms_router.get("/{room_id}")
async def get_room(room_id: str, request: Request, user: CurrentUser):
    return room_out(await _room_or_404(request, user.id, room_id))


@rooms_router.get("/{room_id}/messages")
async def list_room_messages(room_id: str, request: Request, user: CurrentUser, after: int = 0):
    room = await _room_or_404(request, user.id, room_id)
    talk = request.app.state.talk
    if after:
        messages = await talk.list_messages(user.id, room.thread_id, after_seq=after)
    else:
        messages = await talk.list_latest_messages(user.id, room.thread_id)
    return [message_out(m) for m in messages]


@rooms_router.post("/{room_id}/messages", status_code=202, dependencies=[RequireOrigin])
async def post_room_message(room_id: str, body: RoomPost, request: Request, user: CurrentUser):
    room = await _room_or_404(request, user.id, room_id)
    receipt = await request.app.state.room_service.post(user.id, room, body.text)
    return {"message_id": receipt.message_id, "routed_to": list(receipt.routed_to)}
