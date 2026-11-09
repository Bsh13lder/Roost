// The gateway's project limits and palette (roost/constants.py PROJECT_COLORS,
// DEFAULT_PROJECT_COLOR, MAX_CATEGORY_NAME_LENGTH, TOPUP_SOURCE_MAX_CHARS,
// CURRENCY_PATTERN): the inputs stop there, and the gateway checks again.
// Like board/money.ts, nothing here adds amounts: the server sends every number.
import { formatMoney } from "../board/money";
import { dayText, todayIn } from "../../ui/date/dates";
import type { ProjectProgressOut, TopupOut } from "../../api/types";

// The nine colours of H16, in the server's order (the first is the default), with the names a screen reader says.
export const PROJECT_COLORS: ReadonlyArray<readonly [string, string]> = [
  ["#64748b", "Slate"], ["#ef4444", "Red"], ["#f97316", "Orange"], ["#eab308", "Yellow"], ["#22c55e", "Green"],
  ["#14b8a6", "Teal"], ["#3b82f6", "Blue"], ["#8b5cf6", "Violet"], ["#ec4899", "Pink"],
];
export const DEFAULT_PROJECT_COLOR = PROJECT_COLORS[0][0];
export const DEFAULT_CURRENCY = "EUR";
export const MAX_PROJECT_NAME = 40;
export const MAX_TOPUP_SOURCE = 120;
export const CURRENCY_LENGTH = 3;
export const FULL_PERCENT = 100;
export const GENERAL_PROJECT_NAME = "General"; // roost/constants.py: where an expense with no project goes (H2)
export const CURRENCY_HELP = "A currency is three letters, like EUR.";

const CURRENCY_CODE = /^[A-Z]{3}$/;

const folded = (name: string) => name.trim().split(/\s+/).join(" ").toLowerCase();

/** General (H2) is the project whose name, case and spacing ignored, is "General". It is never listed,
 *  and the server refuses to change or delete it, so its page (reachable by address) offers neither. */
export function isGeneral(project: { name: string }): boolean {
  return folded(project.name) === folded(GENERAL_PROJECT_NAME);
}

/** "eur " → "EUR"; anything that is not three letters → null. */
export function readCurrency(text: string): string | null {
  const code = text.trim().toUpperCase();
  return CURRENCY_CODE.test(code) ? code : null;
}

/** A history row's name (H4): a top-up, a change to one, or the budget set by hand. */
export function topupLabel(topup: TopupOut): string {
  if (topup.kind === "credit") return "Top-up";
  return topup.topup_id ? "Top-up changed" : "Budget set";
}

/** A change to a budget with its sign, as the server wrote it: "+€20.00", "-€20.00". */
export function signedMoney(amount: string, currency: string): string {
  return amount.startsWith("-") ? formatMoney(amount, currency) : `+${formatMoney(amount, currency)}`;
}

/** A moment (UTC ISO) → its day on the account's calendar, "10 Oct 2026". */
export function momentDay(iso: string): string {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? iso : dayText(todayIn(when), { year: true });
}

/** A plain day ("2026-12-20") → "20 Dec 2026", with the fixed month names. */
export function dateLabel(day: string): string {
  return dayText(day, { year: true });
}

/** "3 of 5 done" (the server leaves cancelled tasks out of the total), or "No tasks yet". */
export function progressText(progress: ProjectProgressOut): string {
  return progress.total === 0 ? "No tasks yet" : `${progress.done} of ${progress.total} done`;
}

const MS_PER_DAY = 86_400_000;
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const utcDay = (day: string): number => {
  const [year, month, date] = day.split("-").map(Number);
  return Date.UTC(year, month - 1, date);
};

/** Whole days from `from` to `to` (both "YYYY-MM-DD"); negative when `to` is earlier. Calendar days only. */
export function daysBetween(from: string, to: string): number {
  return Math.round((utcDay(to) - utcDay(from)) / MS_PER_DAY);
}

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** The due date against the account's today: "120 days left", "due today", "ended 3 days ago". */
export function daysLeftText(due: string, today: string): string {
  const left = daysBetween(today, due);
  if (left === 0) return "due today";
  return left > 0 ? `${plural(left, "day")} left` : `ended ${plural(-left, "day")} ago`;
}

/** Days left in today's month, counting from tomorrow: "11 days to go", or "last day" on the 31st. */
export function monthToGoText(today: string): string {
  const [year, month] = today.split("-").map(Number);
  const last = `${today.slice(0, 8)}${String(new Date(Date.UTC(year, month, 0)).getUTCDate()).padStart(2, "0")}`;
  const left = daysBetween(today, last);
  return left === 0 ? "last day of the month" : `${plural(left, "day")} to go`;
}

/** 1 → "1st", 2 → "2nd", 5 → "5th", 21 → "21st". */
export function ordinal(value: number): string {
  const tens = value % 100;
  if (tens >= 11 && tens <= 13) return `${value}th`;
  return `${value}${["th", "st", "nd", "rd"][value % 10] ?? "th"}`;
}

/** How often a repeating charge falls, from its anchor day: "monthly, 5th", "weekly, Mon", "yearly, 5 Nov". */
export function cadenceText(cadence: string, anchorDay: string): string {
  const [, month, date] = anchorDay.split("-").map(Number);
  if (cadence === "monthly") return `monthly, ${ordinal(date)}`;
  if (cadence === "weekly") return `weekly, ${WEEKDAYS[new Date(utcDay(anchorDay)).getUTCDay()]}`;
  return `${cadence}, ${dayText(`2000-${String(month).padStart(2, "0")}-${String(date).padStart(2, "0")}`)}`;
}
