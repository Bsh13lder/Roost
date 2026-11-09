// SPDX-License-Identifier: MIT
// The due chip and reminder words are harvested from LazyClaw web/src/components/tasks/taskHelpers.ts
// @ 21e1002, adapted for Roost. dueWords / dueTone are Roost's own: the one-line row's due column (G3).

import type { TaskOut } from "../../api/types";
import { dayText, dayToDate, type IsoDay } from "../../ui/date/dates";
import { appTimeZone } from "../../lib/timeZone";

type Priority = TaskOut["priority"];

export type DueTone = "overdue" | "soon" | "future" | "none";

export interface DueChip {
  label: string;
  tone: DueTone;
}

export const PRIORITY_RANK: Record<Priority, number> = {
  urgent: 0,
  high: 1,
  medium: 2,
  low: 3,
};
export const PRIORITY_LABEL: Record<Priority, string> = {
  urgent: "URGENT",
  high: "HIGH",
  medium: "MED",
  low: "LOW",
};

const CLOCK: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit" };

export function formatClock(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { ...CLOCK, timeZone: appTimeZone() });
}

// Roost: a timed due_date ("2026-10-14T09:00:00+02:00") is a moment too.
function timedDue(dueDate: string | null): string | null {
  return dueDate && dueDate.includes("T") ? dueDate : null;
}

/**
 * Format a due_date (YYYY-MM-DD, or a timed ISO) + optional reminder_at (ISO)
 * into a tight human-readable chip like "in 2h", "today 09:00", "tomorrow",
 * "3d overdue". Roost: the chip is about the DUE — a reminder stands in only
 * when there is no due at all (the row shows the reminder in its own chip).
 */
export function formatDueChip(dueDate: string | null, reminderAt: string | null): DueChip {
  if (!dueDate && !reminderAt) return { label: "", tone: "none" };

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const instant = timedDue(dueDate) ?? (dueDate ? null : reminderAt);
  if (instant) {
    const when = new Date(instant);
    if (!Number.isNaN(when.getTime())) return momentChip(when, today);
  }

  if (dueDate) return dayChip(dueDate, today);

  return { label: "", tone: "none" };
}

// LazyClaw's reminder_at branch, unchanged.
function momentChip(when: Date, today: Date): DueChip {
  const diffMs = when.getTime() - Date.now();
  const abs = Math.abs(diffMs);
  if (diffMs < 0) {
    if (abs < 3_600_000) return { label: `${Math.round(abs / 60_000)}m overdue`, tone: "overdue" };
    if (abs < 864e5) return { label: `${Math.round(abs / 3_600_000)}h overdue`, tone: "overdue" };
    return { label: `${Math.round(abs / 864e5)}d overdue`, tone: "overdue" };
  }
  const timeStr = when.toLocaleTimeString(undefined, { ...CLOCK, timeZone: appTimeZone() });
  if (abs < 3_600_000) return { label: `in ${Math.max(1, Math.round(abs / 60_000))}m`, tone: "soon" };
  if (abs < 24 * 3_600_000) {
    const sameDay = when.toDateString() === new Date().toDateString();
    return { label: sameDay ? `today ${timeStr}` : `in ${Math.round(abs / 3_600_000)}h`, tone: "soon" };
  }
  if (abs < 7 * 864e5) {
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    if (when.toDateString() === tomorrow.toDateString()) {
      return { label: `tomorrow ${timeStr}`, tone: "soon" };
    }
    return {
      label: when.toLocaleDateString(undefined, { weekday: "short", timeZone: appTimeZone() }) + " " + timeStr,
      tone: "future",
    };
  }
  return {
    label: when.toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: appTimeZone() }),
    tone: "future",
  };
}

// LazyClaw's date-only due_date branch, unchanged.
function dayChip(dueDate: string, today: Date): DueChip {
  const d = new Date(`${dueDate}T00:00:00`);
  if (Number.isNaN(d.getTime())) return { label: dueDate, tone: "none" };
  const diffDays = Math.round((d.getTime() - today.getTime()) / 864e5);
  if (diffDays < 0) return { label: `${Math.abs(diffDays)}d overdue`, tone: "overdue" };
  if (diffDays === 0) return { label: "today", tone: "soon" };
  if (diffDays === 1) return { label: "tomorrow", tone: "soon" };
  if (diffDays < 7) return { label: `in ${diffDays}d`, tone: "future" };
  return {
    label: d.toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: appTimeZone() }),
    tone: "future",
  };
}

// Roost: "Reminder 09:00" when it rings on the due's day (or today), else
// with its day, so a reminder the day before never reads as the due day.
export function formatReminder(reminderAt: string, dueDate: string | null): string {
  const when = new Date(reminderAt);
  if (Number.isNaN(when.getTime())) return "Reminder";
  const anchor = dueDate ? new Date(dueDate.includes("T") ? dueDate : `${dueDate}T00:00:00`) : new Date();
  const sameDay = when.toDateString() === anchor.toDateString();
  const day = when.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", timeZone: appTimeZone() });
  return sameDay ? `Reminder ${formatClock(reminderAt)}` : `Reminder ${day} ${formatClock(reminderAt)}`;
}

// Roost: advance reminders as offsets from the reminder ("30m, 2h before");
// with no reminder to measure from, just how many there are.
export function formatEarly(preReminders: readonly string[], reminderAt: string | null): string | null {
  if (preReminders.length === 0) return null;
  const ring = reminderAt ? new Date(reminderAt).getTime() : Number.NaN;
  if (Number.isNaN(ring)) return `${preReminders.length} early`;
  const offsets = preReminders.map((early) => Math.round((ring - new Date(early).getTime()) / 60_000));
  if (offsets.some((minutes) => !(minutes > 0))) return `${preReminders.length} early`;
  return `${offsets.map(offsetText).join(", ")} before`;
}

function offsetText(minutes: number): string {
  if (minutes < 60 || minutes % 60 !== 0) return `${minutes}m`;
  if (minutes < 1440 || minutes % 1440 !== 0) return `${minutes / 60}h`;
  return `${minutes / 1440}d`;
}

export type RowDueTone = "over" | "today" | "soon" | "later";

const DAY_LENGTH = "YYYY-MM-DD".length;
const WEEK_DAYS = 7;
const MS_PER_DAY = 864e5;

// Days from `today` to the due's day (negative: late). The due may be a plain day or an account-local moment.
export function daysAhead(due: string, today: IsoDay): number {
  return Math.round((dayToDate(due.slice(0, DAY_LENGTH)).getTime() - dayToDate(today).getTime()) / MS_PER_DAY);
}

/** The row's due column in words: "Yesterday", "4d overdue", "Today", "Tomorrow", "Fri" (within a week),
 * "29 Oct". A done task shows its day in full, "Tue 20 Oct". No due: "". `today` is the account's. */
export function dueWords(due: string | null, today: IsoDay, done: boolean): string {
  if (!due) return "";
  const day = due.slice(0, DAY_LENGTH);
  if (done) return dayText(day, { weekday: true });
  const ahead = daysAhead(due, today);
  if (ahead === -1) return "Yesterday";
  if (ahead < 0) return `${-ahead}d overdue`;
  if (ahead === 0) return "Today";
  if (ahead === 1) return "Tomorrow";
  return ahead < WEEK_DAYS ? dayText(day, { weekday: true }).split(" ")[0] : dayText(day);
}

/** The due column's tone, matching its words: late is red, today green, tomorrow amber, the rest quiet. */
export function dueTone(due: string | null, today: IsoDay): RowDueTone {
  if (!due) return "later";
  const ahead = daysAhead(due, today);
  if (ahead < 0) return "over";
  return ahead === 0 ? "today" : ahead === 1 ? "soon" : "later";
}
