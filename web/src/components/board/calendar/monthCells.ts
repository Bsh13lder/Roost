import { DAYS_PER_WEEK } from "../constants";
import { addDays, type IsoDay } from "../../../ui/date/dates";

const WEEKEND_FROM = 5; // Monday is 0: Saturday is 5, Sunday 6

// 0 = Monday ... 6 = Sunday, for a plain day (no clock, so no time zone).
export function weekdayIndex(day: IsoDay): number {
  const [year, month, date] = day.split("-").map(Number);
  return (new Date(Date.UTC(year, month - 1, date)).getUTCDay() + DAYS_PER_WEEK - 1) % DAYS_PER_WEEK;
}

export function isWeekend(day: IsoDay): boolean {
  return weekdayIndex(day) >= WEEKEND_FROM;
}

/** The Monday of the week a day falls in. */
export function mondayOf(day: IsoDay): IsoDay {
  return addDays(day, -weekdayIndex(day));
}

/** The seven days of a day's week, Monday first. */
export function weekDays(day: IsoDay): IsoDay[] {
  const monday = mondayOf(day);
  return Array.from({ length: DAYS_PER_WEEK }, (_, index) => addDays(monday, index));
}

/** A month's grid ("2026-10"): whole weeks, Monday first, so 5 or 6 of them, with the days of the months beside it. */
export function monthDays(month: string): IsoDay[] {
  const [year, number] = month.split("-").map(Number);
  const first = `${month}-01`;
  const length = new Date(Date.UTC(year, number, 0)).getUTCDate();
  const weeks = Math.ceil((weekdayIndex(first) + length) / DAYS_PER_WEEK);
  const monday = mondayOf(first);
  return Array.from({ length: weeks * DAYS_PER_WEEK }, (_, index) => addDays(monday, index));
}

/** The "YYYY-MM" a day falls in. */
export const monthOfDay = (day: IsoDay): string => day.slice(0, "YYYY-MM".length);
