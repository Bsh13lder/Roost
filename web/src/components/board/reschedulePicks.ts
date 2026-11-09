import { addDays, dayText, dayToDate, nextMonday, type IsoDay } from "../../ui/date/dates";
import type { QuickPick } from "../../ui/date/picks";
import { DAYS_PER_WEEK, NEXT_WEEK_PICK_DAYS, PLUS_WEEK_DAYS, SATURDAY } from "./constants";

function thisWeekend(today: IsoDay): IsoDay {
  const weekday = dayToDate(today).getDay();
  return addDays(today, (SATURDAY - weekday + DAYS_PER_WEEK) % DAYS_PER_WEEK); // a Saturday is today
}

// The reschedule popover's quick picks, in the mockup's order: each is a day from the account's today, or null.
export const RESCHEDULE_PICKS: readonly QuickPick[] = [
  { label: "Today", day: (today) => today },
  { label: "Tomorrow", day: (today) => addDays(today, 1) },
  { label: "This weekend", day: thisWeekend },
  { label: "Next Monday", day: nextMonday },
  { label: "Next week", day: (today) => addDays(nextMonday(today), NEXT_WEEK_PICK_DAYS) },
  { label: "+1 week", day: (today) => addDays(today, PLUS_WEEK_DAYS) },
  { label: "No date", day: () => null },
];

/** A pick's short date, "Wed 21". */
export function pickLabel(day: IsoDay): string {
  const [weekday, date] = dayText(day, { weekday: true }).split(" ");
  return `${weekday} ${date}`;
}
