// web/src/api/rooms.ts — rooms HTTP API (plan Task 6).
import { apiRequest } from "./client";
import type { MessageOut, RoomOut } from "./types";

export interface RoomDraftIn {
  name: string;
  member_ids: readonly string[];
  coordinator_id: string | null;
}

export interface RoomPostReceipt {
  message_id: string;
  routed_to: string[];
}

// Ids come from the server, but encoding keeps a stray "/" or "?" from
// ever reaching a different route.
function roomPath(roomId: string): string {
  return `/api/rooms/${encodeURIComponent(roomId)}`;
}

export function listRooms(): Promise<RoomOut[]> {
  return apiRequest<RoomOut[]>("GET", "/api/rooms");
}

export function getRoom(roomId: string): Promise<RoomOut> {
  return apiRequest<RoomOut>("GET", roomPath(roomId));
}

export function createRoom(draft: RoomDraftIn): Promise<RoomOut> {
  return apiRequest<RoomOut>("POST", "/api/rooms", draft);
}

export function listRoomMessages(roomId: string): Promise<MessageOut[]> {
  return apiRequest<MessageOut[]>("GET", `${roomPath(roomId)}/messages`);
}

export function postRoomMessage(roomId: string, text: string): Promise<RoomPostReceipt> {
  return apiRequest<RoomPostReceipt>("POST", `${roomPath(roomId)}/messages`, { text });
}
