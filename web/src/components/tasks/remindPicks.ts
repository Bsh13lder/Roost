// Remind me's quick picks (phone notifications, 2026-10-23): times before a timed due, counted on the account's
// clock as the due is written, sent as account wall text the gateway reads ("2026-12-01 08:50").
import { addDays, dueParts, joinDue } from "../../ui/date/dates";

export interface RemindPick {
  label: string;
  text: string;
}

const MINUTES_PER_HOUR = 60;
const MINUTES_PER_DAY = 24 * MINUTES_PER_HOUR;
const PICKS: ReadonlyArray<readonly [string, number]> = [
  ["At the due time", 0], ["10 min before", 10], ["1 hour before", MINUTES_PER_HOUR], ["1 day before", MINUTES_PER_DAY],
];

const pad = (n: number) => String(n).padStart(2, "0");

// A wall time `minutes` earlier: days and clock apart, so no time zone and no summer-time hour is involved.
function before(day: string, time: string, minutes: number): string {
  const [hour, minute] = time.split(":").map(Number);
  const total = hour * MINUTES_PER_HOUR + minute - minutes;
  const daysBack = Math.floor(total / MINUTES_PER_DAY);
  const left = total - daysBack * MINUTES_PER_DAY;
  return joinDue(addDays(day, daysBack), `${pad(Math.floor(left / MINUTES_PER_HOUR))}:${pad(left % MINUTES_PER_HOUR)}`);
}

/** The picks for a due with a time; none for a day alone, words, or no due. */
export function remindPicks(due: string | null): RemindPick[] {
  const parts = dueParts(due ?? "");
  if (!parts?.time) return [];
  const { day, time } = parts;
  return PICKS.map(([label, minutes]) => ({ label, text: before(day, time, minutes) }));
}
