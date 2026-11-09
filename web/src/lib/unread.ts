import type { ChatRowOut } from "../api/types";

// Unread dots on the chat list (redesign P2). For each chat, the time of the newest message you have
// seen. A row whose newest message is later, and not yours, has a dot until you open it. A chat seen for
// the first time counts as read, so a new browser starts with no dots. Kept in this browser only.
export type SeenTimes = Readonly<Record<string, string>>;
export type SeenStorage = Pick<Storage, "getItem" | "setItem">;

export const SEEN_STORAGE_KEY = "roost.chat-seen.v1";

const isSeenTimes = (value: unknown): value is SeenTimes =>
  typeof value === "object" && value !== null && !Array.isArray(value)
  && Object.values(value).every((time) => typeof time === "string");

const later = (time: string, than: string | undefined): boolean => than !== undefined && Date.parse(time) > Date.parse(than);

// The browser's storage; none when reading it throws (Safari with site data blocked).
function browserStorage(): SeenStorage | undefined {
  try {
    return window.localStorage;
  } catch (error) {
    console.warn("This browser keeps no site data here: unread dots last until the page reloads.", error);
    return undefined;
  }
}

// What this browser remembers. Nothing, never an error, when storage is refused or holds something else.
export function readSeen(storage: SeenStorage | undefined = browserStorage()): SeenTimes {
  try {
    const parsed: unknown = JSON.parse(storage?.getItem(SEEN_STORAGE_KEY) ?? "{}");
    return isSeenTimes(parsed) ? parsed : {};
  } catch (error) {
    console.warn("Could not read the chats you have seen; starting with none unread.", error);
    return {};
  }
}

export function writeSeen(seen: SeenTimes, storage: SeenStorage | undefined = browserStorage()): void {
  try {
    storage?.setItem(SEEN_STORAGE_KEY, JSON.stringify(seen));
  } catch (error) {
    console.warn("Could not remember the chats you have seen.", error);
  }
}

// The seen times after a look at the list: a chat seen for the first time counts as read, and the open
// chat, or one whose newest message is yours, is read up to its newest message. The same object when
// nothing changed, so a caller can tell.
export function markSeen(rows: readonly ChatRowOut[], seen: SeenTimes, openId: string | null): SeenTimes {
  const updates = rows.filter((row) => !(row.id in seen) || ((row.id === openId || row.from_you) && later(row.last_at, seen[row.id])));
  return updates.length === 0 ? seen : { ...seen, ...Object.fromEntries(updates.map((row) => [row.id, row.last_at])) };
}

// The chats with a newer message than the one you saw, and not yours. The open chat never has a dot.
export function unreadChats(rows: readonly ChatRowOut[], seen: SeenTimes, openId: string | null): ReadonlySet<string> {
  return new Set(rows
    .filter((row) => row.id !== openId && !row.from_you && later(row.last_at, seen[row.id]))
    .map((row) => row.id));
}
