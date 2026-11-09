import { zonedFormat } from "../../lib/timeZone";

// Days and wall times on the account's calendar (redesign P1; the zone is the account's since 2026-11-09).
// A picker never turns a day into an instant: "2026-10-16" is a day and "2026-10-16 09:00" is 09:00 on the
// account's clock, both exactly as the gateway reads them (roost/tasks/due.py). Only "today" needs the clock,
// and it asks the account's zone (appTimeZone).

export type IsoDay = string; // "YYYY-MM-DD"
export type WallTime = string; // "HH:MM"

/** A span being picked: the first day, and the last once it is chosen. */
export interface DayRangeValue {
  from: IsoDay | null;
  to: IsoDay | null;
}

export interface DueParts {
  day: IsoDay;
  time: WallTime | null;
}

const ISO_DAY = /^(\d{4})-(\d{2})-(\d{2})$/;
// A picked or stored timed due: "2026-10-16 09:00", "2026-10-16T09:00", "2026-10-16T09:00:00+02:00".
const ISO_DAY_TIME = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:Z|[+-]\d{2}:\d{2})?$/;
const dayFormat = () => zonedFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit" });
const DAYS_PER_WEEK = 7;
const MAX_HOUR = 23;
const MAX_MINUTE_OR_SECOND = 59;
// Fixed names, not Intl's: ICU spells September "Sept" in en-GB and the line under the box says "Sep".
const WEEKDAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;
const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const;

function utcNoon(day: IsoDay): Date {
  const [year, month, date] = day.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, date, 12));
}

export function isIsoDay(text: string): boolean {
  const match = ISO_DAY.exec(text);
  if (!match) return false;
  return utcNoon(text).toISOString().slice(0, 10) === text; // 2026-02-30 is not a day
}

const WALL_TIME = /^([01]?\d|2[0-3]):[0-5]\d$/;

/** A time of day typed as "9:30" or "09:30". */
export function isWallTime(text: string): boolean {
  return WALL_TIME.test(text);
}

/** Today on the account's calendar, whatever the browser's own zone. */
export function todayIn(now: Date = new Date()): IsoDay {
  const parts = dayFormat().formatToParts(now);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

/** Calendar arithmetic on days alone: no clock, so no time zone and no daylight saving. */
export function addDays(day: IsoDay, count: number): IsoDay {
  const moved = utcNoon(day);
  moved.setUTCDate(moved.getUTCDate() + count);
  return moved.toISOString().slice(0, 10);
}

/** The Monday after `day` (a Monday gives the next one). */
export function nextMonday(day: IsoDay): IsoDay {
  const weekday = (utcNoon(day).getUTCDay() + DAYS_PER_WEEK - 1) % DAYS_PER_WEEK; // Monday 0
  return addDays(day, DAYS_PER_WEEK - weekday);
}

/** The day and wall time a picked or stored value names, or null for words the gateway must read. */
export function dueParts(text: string): DueParts | null {
  const value = text.trim();
  if (isIsoDay(value)) return { day: value, time: null };
  const timed = ISO_DAY_TIME.exec(value);
  if (!timed || !isIsoDay(timed[1])) return null;
  const [, day, hour, minute, second = "0"] = timed;
  // "25:99" is no time, and "24:00" is the next day's midnight: the gateway says which, not this reader.
  if (Number(hour) > MAX_HOUR || Number(minute) > MAX_MINUTE_OR_SECOND || Number(second) > MAX_MINUTE_OR_SECOND) return null;
  return { day, time: `${hour}:${minute}` };
}

// A typed "…Z" or "…+00:00" names an instant. The gateway turns it into the account's clock, so only the
// gateway can say which day and time that is; it is not a wall time to read here.
const ZONE_SUFFIX = /(?:Z|[+-]\d{2}:\d{2})$/;

/** The day and wall time a value the user typed or picked names *as written*, or null when the gateway
 * must read it: words, and an ISO time with a zone (which it moves onto the account's clock). */
export function pickedParts(text: string): DueParts | null {
  const value = text.trim();
  return ZONE_SUFFIX.test(value) ? null : dueParts(value);
}

/** What a picker sends: "2026-10-16", or "2026-10-16 09:00" (account wall time, no offset). */
export function joinDue(day: IsoDay, time: WallTime | null): string {
  return time ? `${day} ${time}` : day;
}

const wallFormat = () => zonedFormat("en-CA", {
  year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

/** An instant (a UTC ISO time such as TaskOut.reminder_at) as the picker's text: the account's day and wall
 * time, "2026-11-30 20:00". "" for no instant or one that is not a time. */
export function wallText(iso: string | null): string {
  if (!iso) return "";
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  const parts = wallFormat().formatToParts(when);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")} ${part("hour")}:${part("minute")}`;
}

/** A stored due (TaskOut.due_date) as the picker's text: its day on the account's clock and wall time as written. */
export function pickerText(due: string | null): string {
  if (!due) return "";
  const parts = dueParts(due);
  return parts ? joinDue(parts.day, parts.time) : due;
}

export interface DayTextOptions {
  weekday?: boolean; // "Tue 13 Oct"
  year?: boolean; // "13 Oct 2026"
}

/** A day with the fixed names: "13 Oct", "Tue 13 Oct", "13 Oct 2026" or "Tue 13 Oct 2026". Anything that
 * is not a day comes back as it is. Every day label on the Board goes through here (redesign P3). */
export function dayText(day: string, { weekday = false, year = false }: DayTextOptions = {}): string {
  if (!isIsoDay(day)) return day;
  const noon = utcNoon(day);
  const named = `${noon.getUTCDate()} ${MONTH_NAMES[noon.getUTCMonth()]}`;
  const dated = year ? `${named} ${noon.getUTCFullYear()}` : named;
  return weekday ? `${WEEKDAY_NAMES[noon.getUTCDay()]} ${dated}` : dated;
}

/** "Fri 16 Oct 2026", or "Fri 16 Oct 2026, 09:00". */
export function friendlyDue(parts: DueParts, withTime = true): string {
  const day = dayText(parts.day, { weekday: true, year: true });
  return withTime && parts.time ? `${day}, ${parts.time}` : day;
}

// The calendar grid works in local Date objects: a day goes in as local noon and comes back by its
// local fields, so the browser's zone never moves it.
export function dayToDate(day: IsoDay): Date {
  const [year, month, date] = day.split("-").map(Number);
  return new Date(year, month - 1, date, 12);
}

export function dateToDay(date: Date): IsoDay {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
