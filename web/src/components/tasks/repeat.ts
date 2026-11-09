import type { SelectOption } from "../../ui/Select";
import { dueParts, pickerText, todayIn } from "../../ui/date/dates";
import { REPEAT_DEFAULT_TIME } from "./constants";

// A task's repeat as the drawer offers it (redesign P3). The gateway stores a cron on the account's time
// (roost/tasks/recurrence.py); the drawer builds one from the due's day and time, and names the crons it
// built. A cron a bot set that matches none of them is "Custom" and is kept as it is.
export type RepeatKind = "never" | "daily" | "weekdays" | "weekly" | "monthly" | "custom";

export const REPEAT_OPTIONS: ReadonlyArray<SelectOption<RepeatKind>> = [
  { value: "never", label: "Never" },
  { value: "daily", label: "Every day" },
  { value: "weekdays", label: "Every weekday" },
  { value: "weekly", label: "Every week" },
  { value: "monthly", label: "Every month" },
];
export const CUSTOM_OPTION: SelectOption<RepeatKind> = { value: "custom", label: "Custom" };

const CLOCK = String.raw`(\d{1,2}) (\d{1,2})`;
const PATTERNS: ReadonlyArray<readonly [RepeatKind, RegExp]> = [
  ["daily", new RegExp(`^${CLOCK} \\* \\* \\*$`)],
  ["weekdays", new RegExp(`^${CLOCK} \\* \\* 1-5$`)],
  ["weekly", new RegExp(`^${CLOCK} \\* \\* [0-6]$`)],
  ["monthly", new RegExp(`^${CLOCK} (\\d{1,2}) \\* \\*$`)],
];

/** Which of the drawer's repeats a stored cron is. */
export function repeatOf(cron: string | null): RepeatKind {
  if (!cron || !cron.trim()) return "never";
  const found = PATTERNS.find(([, pattern]) => pattern.test(cron.trim()));
  return found ? found[0] : "custom";
}

/** The cron for a repeat, at the due's wall time (09:00 without one), on the due's weekday or day of the
 * month (today's without a due). null for Never; "custom" is never built here. */
export function cronFor(kind: RepeatKind, due: string | null): string | null {
  if (kind === "never" || kind === "custom") return null;
  const parts = dueParts(pickerText(due)) ?? { day: todayIn(), time: null };
  const [hour, minute] = (parts.time ?? REPEAT_DEFAULT_TIME).split(":").map(Number);
  const [year, month, date] = parts.day.split("-").map(Number);
  const clock = `${minute} ${hour}`;
  if (kind === "daily") return `${clock} * * *`;
  if (kind === "weekdays") return `${clock} * * 1-5`;
  if (kind === "weekly") return `${clock} * * ${new Date(Date.UTC(year, month - 1, date)).getUTCDay()}`;
  return `${clock} ${date} * *`;
}
