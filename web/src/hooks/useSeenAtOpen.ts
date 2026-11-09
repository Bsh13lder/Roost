import { useState } from "react";
import { readSeen } from "../lib/unread";

// The newest time you had seen in this chat when you opened it, kept until the chat changes (polish
// R1.10). Read while rendering a new chat id, before useUnread's effect marks the chat read.
export function useSeenAtOpen(chatId: string): string | null {
  const [snap, setSnap] = useState(() => ({ chatId, seen: readSeen()[chatId] ?? null }));
  if (snap.chatId !== chatId) {
    const next = { chatId, seen: readSeen()[chatId] ?? null };
    setSnap(next);
    return next.seen;
  }
  return snap.seen;
}
