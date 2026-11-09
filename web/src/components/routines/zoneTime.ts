import { zonedFormat } from "../../lib/timeZone";

// Routine times on the account's clock (appTimeZone; Madrid's until 2026-11-09). A time shows as the clock
// alone: the zone is the account's everywhere, so it is not said beside each one.
const stampFormat = () => zonedFormat("en-GB", {
  weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});
const clockOnly = () => zonedFormat("en-GB", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const dayKey = () => zonedFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit" });
const clockAndDay = () => zonedFormat("en-GB", { weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const WEEKDAY_SPAN_DAYS = 6; // within this many days the weekday says enough

const partsOf = (format: Intl.DateTimeFormat, when: Date): Record<string, string> =>
  Object.fromEntries(format.formatToParts(when).map((p) => [p.type, p.value]));

// "Wed 21 Oct 10:07" on the account's clock; "" for no time or one that does not parse.
export function zoneStamp(iso: string | null): string {
  if (!iso) return "";
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  const parts = partsOf(stampFormat(), when);
  return `${parts.weekday} ${parts.day} ${parts.month} ${parts.hour}:${parts.minute}`;
}

// Days from `from` to `to` on the account's calendar (0: the same day).
function daysBetween(from: Date, to: Date): number {
  const asUtc = (when: Date) => Date.parse(`${dayKey().format(when)}T00:00:00Z`);
  return Math.round((asUtc(to) - asUtc(from)) / DAY);
}

// "14:50" when `iso` is today, else "Wed 21 Oct 14:50"; "" for no time.
export function zoneClock(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "";
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  return daysBetween(when, now) === 0 ? clockOnly().format(when) : zoneStamp(iso);
}

// When a routine runs next, in words (owner, 2026-10-26, like Grok's "Next run: in 10 hr."): "in 30 min" or
// "in 3 h" while it is today, then "tomorrow 09:00", "Sat 09:00", or the date. "" for no time.
export function nextRunWords(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "";
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  const ahead = when.getTime() - now.getTime();
  if (ahead <= 0) return "now";
  const days = daysBetween(now, when);
  if (days === 0) {
    return ahead < HOUR ? `in ${Math.max(1, Math.ceil(ahead / MINUTE))} min` : `in ${Math.round(ahead / HOUR)} h`;
  }
  const parts = partsOf(clockAndDay(), when);
  const clock = `${parts.hour}:${parts.minute}`;
  if (days === 1) return `tomorrow ${clock}`;
  return days <= WEEKDAY_SPAN_DAYS ? `${parts.weekday} ${clock}` : zoneStamp(iso);
}
