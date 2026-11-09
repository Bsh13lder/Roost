import type { BotOut } from "../../api/types";
import { formatClock } from "../../lib/chatTime";
import { dayText, todayIn } from "../../ui/date/dates";

// Who wrote a comment or made a task, and when, in the drawer's words (redesign P3).
export const USER_AUTHOR = "user";
export const RETIRED_BOT = "A retired bot";

/** "You", the bot's name, or "A retired bot" for a bot id the user no longer has. */
export function authorName(author: string, bots: Readonly<Record<string, BotOut>>): string {
  if (author === USER_AUTHOR) return "You";
  return bots[author]?.name ?? RETIRED_BOT;
}

/** A moment on the account's calendar and clock: "Thu 15 Oct, 10:00". "" for one that is not a time. */
export function momentText(iso: string | null): string {
  if (!iso) return "";
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  return `${dayText(todayIn(when), { weekday: true })}, ${formatClock(iso)}`;
}
