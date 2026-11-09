import { useEffect, useRef } from "react";
import type { BotOut, MessageOut } from "../api/types";
import { speakMessage } from "../store/speech";

const SPOKEN_KINDS = new Set(["text", "report"]);

// A stored bot reply or Report (a placeholder still being written has seq 0).
export function isSpokenReply(message: MessageOut): boolean {
  return message.role === "bot" && message.seq !== 0 && SPOKEN_KINDS.has(message.kind ?? "text");
}

function readsAloud(message: MessageOut, bots: Readonly<Record<string, BotOut>>, fallback: BotOut | null): boolean {
  const author = message.author_bot_id ? bots[message.author_bot_id] : undefined;
  return (author ?? fallback)?.voice?.read_aloud === true;
}

interface Seen {
  readonly threadId: string;
  readonly ids: Set<string>;
}

// Read replies aloud (voice plan V3): while this chat is open and the page is visible, a reply that arrives live (the
// live store's messages for this thread) from a bot whose voice has Read replies aloud on plays by itself. What the
// thread held when it opened never plays; each message plays at most once. A browser that blocks sound without a tap
// just leaves the speaker button as it was: no retry, no loop. While `paused` (a call is open and speaks the replies
// itself) nothing plays, and a reply that arrived meanwhile stays unplayed afterwards.
export function useReadAloud(
  threadId: string | undefined,
  liveMessages: readonly MessageOut[] | undefined,
  bots: Readonly<Record<string, BotOut>>,
  bot: BotOut | null,
  paused = false,
): void {
  const seen = useRef<Seen | null>(null);
  useEffect(() => {
    if (!threadId) return;
    const stored = (liveMessages ?? []).filter(isSpokenReply);
    if (seen.current?.threadId !== threadId) {
      seen.current = { threadId, ids: new Set(stored.map((message) => message.id)) };
      return;
    }
    const known = seen.current.ids;
    const fresh = stored.filter((message) => !known.has(message.id));
    fresh.forEach((message) => known.add(message.id));
    const newest = fresh.at(-1);
    if (!newest || paused || document.visibilityState !== "visible" || !readsAloud(newest, bots, bot)) return;
    speakMessage(threadId, newest.id).catch((err: unknown) => {
      console.info("A reply wasn't read aloud by itself; its speaker button still plays it.", err);
    });
  }, [threadId, liveMessages, bots, bot, paused]);
}
