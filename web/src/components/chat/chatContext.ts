import { createContext, useContext } from "react";
import type { MentionOption } from "../../lib/mentions";

// What a bot's chat page shares with its rows (2026-10-26): your projects (for the "#Name" chips in your bubbles
// and the project on a task card) and how to open a task's drawer from a card. Rooms and tests leave it empty.
export interface ChatShared {
  projects: readonly MentionOption[];
  openTask?: (taskId: string) => void;
}

const EMPTY: ChatShared = { projects: [] };

export const ChatContext = createContext<ChatShared>(EMPTY);

export function useChatShared(): ChatShared {
  return useContext(ChatContext);
}
