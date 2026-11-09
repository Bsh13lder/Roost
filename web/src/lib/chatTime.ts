// Chat-list times, as a messenger shows them, on the account's clock (appTimeZone):
// 14:19 today, Yesterday, the weekday within a week, then "Oct 4".
import { zonedFormat } from "./timeZone";

const DAY_MS = 86_400_000;
const dayKeyFormat = () => zonedFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit" });
const clockFormat = () => zonedFormat("en-GB", { hour: "2-digit", minute: "2-digit" });
const weekdayFormat = () => zonedFormat("en-GB", { weekday: "long" });
const dateFormat = () => zonedFormat("en-US", { month: "short", day: "numeric" });
const dayLabelFormat = () => zonedFormat("en-GB", { weekday: "long", day: "numeric", month: "long" });

/** The account's calendar day a moment falls on, "2026-10-14". */
export function zoneDayKey(date: Date): string {
  return dayKeyFormat().format(date);
}

function daysBetween(earlier: Date, later: Date): number {
  return Math.round((Date.parse(zoneDayKey(later)) - Date.parse(zoneDayKey(earlier))) / DAY_MS);
}

// A message's own time (redesign P2): 14:19 on the account's clock, the chat's one time format.
export function formatClock(iso: string): string {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? "" : clockFormat().format(when);
}

export function formatChatTime(iso: string, now: Date = new Date()): string {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  const days = daysBetween(when, now);
  if (days <= 0) return formatClock(iso);
  if (days === 1) return "Yesterday";
  if (days < 7) return weekdayFormat().format(when);
  return dateFormat().format(when);
}

// A chat's date separator (S1.5): Today, Yesterday, then "Monday 12 October".
export function formatDayLabel(iso: string, now: Date = new Date()): string {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  const days = daysBetween(when, now);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  return dayLabelFormat().format(when);
}
