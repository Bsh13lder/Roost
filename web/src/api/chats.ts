import { apiRequest } from "./client";
import type { ChatRowOut } from "./types";

export function listChats(): Promise<ChatRowOut[]> {
  return apiRequest<ChatRowOut[]>("GET", "/api/chats");
}
