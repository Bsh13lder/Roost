import { useEffect, useMemo, useState } from "react";
import { useMatch } from "react-router-dom";
import type { ChatRowOut } from "../api/types";
import { markSeen, readSeen, unreadChats, writeSeen, type SeenTimes } from "../lib/unread";

// The chat on screen: a bot's chat or a room, by its id.
function useOpenChatId(): string | null {
  const bot = useMatch("/bots/:botId")?.params.botId;
  const room = useMatch("/rooms/:roomId")?.params.roomId;
  return bot ?? room ?? null;
}

// The chats with a message you have not seen (redesign P2), remembered in this browser (lib/unread.ts).
export function useUnread(rows: readonly ChatRowOut[]): ReadonlySet<string> {
  const openId = useOpenChatId();
  const [seen, setSeen] = useState<SeenTimes>(() => readSeen());
  useEffect(() => {
    const next = markSeen(rows, seen, openId);
    if (next === seen) return;
    setSeen(next);
    writeSeen(next);
  }, [rows, seen, openId]);
  return useMemo(() => unreadChats(rows, seen, openId), [rows, seen, openId]);
}
