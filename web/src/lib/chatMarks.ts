import type { MessageOut } from "../api/types";
import { formatDayLabel, zoneDayKey } from "./chatTime";

// What the chat draws, in order: a day line before the first message of each day on the account's calendar, the New line
// above the first reply you have not seen, and the messages themselves.
export type ChatItem =
  | { kind: "day"; id: string; label: string }
  | { kind: "new"; id: string }
  | { kind: "message"; message: MessageOut; index: number; dayStart: boolean };

function dayKeyOf(iso: string): string | null {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? null : zoneDayKey(when);
}

// The first stored message that is not yours and is newer than the time you last saw this chat.
// Null on a first visit (no seen time), and while nothing is newer.
export function firstUnreadId(messages: readonly MessageOut[], newAfter: string | null): string | null {
  if (newAfter === null) return null;
  const seen = Date.parse(newAfter);
  if (Number.isNaN(seen)) return null;
  // An english_fix line is about your own words: it never counts as unread.
  const found = messages.find((message) => message.seq > 0 && message.role !== "user" && message.kind !== "english_fix"
    && Date.parse(message.created_at) > seen);
  return found?.id ?? null;
}

// A message with no readable time (a reply still streaming) joins the day before.
export function chatMarks(messages: readonly MessageOut[], newAfter: string | null, now: Date = new Date()): ChatItem[] {
  const unreadId = firstUnreadId(messages, newAfter);
  let shownDay: string | null = null;
  return messages.flatMap((message, index): ChatItem[] => {
    const marks: ChatItem[] = [];
    const day = dayKeyOf(message.created_at);
    const dayStart = day !== null && day !== shownDay;
    if (dayStart) {
      shownDay = day;
      marks.push({ kind: "day", id: `day-${message.id}`, label: formatDayLabel(message.created_at, now) });
    }
    if (message.id === unreadId) marks.push({ kind: "new", id: `new-${message.id}` });
    marks.push({ kind: "message", message, index, dayStart });
    return marks;
  });
}
