import type { PermissionIn, StandingAction } from "../../api/standing";

export const STANDING_ACTIONS: ReadonlyArray<{ value: StandingAction; label: string }> = [
  { value: "post", label: "post" },
  { value: "send", label: "send" },
  { value: "submit", label: "submit" },
];
export const STANDING_MAX_PER_DAY = 20; // roost/standing/constants.py STANDING_MAX_PER_DAY_MAX
export const STANDING_UNTIL_MAX_DAYS = 30; // STANDING_UNTIL_MAX_DAYS
export const STANDING_DEFAULT_DAYS = 7;

// A bare day is already reckoned on the account's calendar: read at noon UTC, on UTC, it never moves.
const dayFormat = new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", weekday: "short", day: "numeric", month: "short" });

// "Sun 1 Nov" for a day "2026-11-01"; the text itself when it isn't one.
export function standingDay(day: string): string {
  const when = new Date(`${day}T12:00:00Z`);
  return Number.isNaN(when.getTime()) ? day : dayFormat.format(when);
}

// "Let it post on x.com up to 1 a day until Sun 1 Nov": the permission in the owner's own words.
export function permissionWords(permission: PermissionIn): string {
  return `Let it ${permission.action} on ${permission.host} up to ${permission.max_per_day} a day until ${standingDay(permission.until)}`;
}
