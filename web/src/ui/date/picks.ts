import { addDays, nextMonday, type IsoDay, type WallTime } from "./dates";

// A one-tap day: from the account's today to a day, or null for "No date".
export interface QuickPick {
  label: string;
  day: (today: IsoDay) => IsoDay | null;
}

// Due dates and project dates look ahead.
export const FUTURE_PICKS: readonly QuickPick[] = [
  { label: "Today", day: (today) => today },
  { label: "Tomorrow", day: (today) => addDays(today, 1) },
  { label: "Next week", day: (today) => nextMonday(today) },
  { label: "No date", day: () => null },
];

// An expense looks back; an empty day is today (the gateway's default), so there is no "No date".
export const PAST_PICKS: readonly QuickPick[] = [
  { label: "Today", day: (today) => today },
  { label: "Yesterday", day: (today) => addDays(today, -1) },
];

// The DateTimePicker's time chips, on the account's clock.
export const TIME_CHIPS: readonly WallTime[] = ["09:00", "12:00", "15:00", "18:00"];
