import { addDays, dayText, type IsoDay } from "../../ui/date/dates";

// The Money date filter's ranges (Board redesign G10), on the account's calendar and nothing else: a range is two
// days, and the server (GET /api/money/range) filters and adds. Nothing here sums.
export type RangePreset = "today" | "week" | "month" | "last" | "custom";

export interface DayRange {
  from: IsoDay;
  to: IsoDay;
}

export const RANGE_PRESETS: ReadonlyArray<{ id: RangePreset; label: string }> = [
  { id: "today", label: "Today" }, { id: "week", label: "This week" }, { id: "month", label: "This month" },
  { id: "last", label: "Last month" }, { id: "custom", label: "Custom range" },
];

const DAYS_PER_WEEK = 7;
const MONDAY_FIRST = 6; // (weekday + 6) % 7 is 0 on a Monday

const weekdayOf = (day: IsoDay): number => new Date(`${day}T12:00:00Z`).getUTCDay();
const firstOfMonth = (day: IsoDay): IsoDay => `${day.slice(0, 7)}-01`;

/** The days a preset covers when today is `today`: this week is Monday to today, this month the 1st to today,
 * last month the whole previous month. */
export function rangeFor(preset: Exclude<RangePreset, "custom">, today: IsoDay): DayRange {
  switch (preset) {
    case "today": return { from: today, to: today };
    case "week": return { from: addDays(today, -((weekdayOf(today) + MONDAY_FIRST) % DAYS_PER_WEEK)), to: today };
    case "month": return { from: firstOfMonth(today), to: today };
    case "last": {
      const lastDay = addDays(firstOfMonth(today), -1);
      return { from: firstOfMonth(lastDay), to: lastDay };
    }
  }
}

/** "this week" for the summary line; a custom range reads "12 Oct–18 Oct" (one day: "12 Oct"). */
export function rangeLabel(preset: RangePreset, range: DayRange): string {
  switch (preset) {
    case "today": return "today";
    case "week": return "this week";
    case "month": return "this month";
    case "last": return "last month";
    case "custom": return range.from === range.to ? dayText(range.from) : `${dayText(range.from)}–${dayText(range.to)}`;
  }
}
