import { CAL_FIRST_HOUR, CAL_HOUR_PX, CAL_HOURS } from "../constants";
import type { TaskRowOut } from "../../../api/tasks";
import { dayToDate, type IsoDay, type WallTime } from "../../../ui/date/dates";

const DAY_LENGTH = "YYYY-MM-DD".length;
const CLOCK_START = "YYYY-MM-DDT".length;
const CLOCK_END = "YYYY-MM-DDTHH:MM".length;
const MS_PER_DAY = 86_400_000;
const MINUTES_PER_HOUR = 60;
const SLOT_HEIGHT_PX = 38; // a timed task's block in the week grid
const UNTIMED_LAST = "99:99";

export const dueDay = (task: TaskRowOut): IsoDay | null => (task.due_date ? task.due_date.slice(0, DAY_LENGTH) : null);

/** The task's own time of day ("09:30"), or null for a plain day. */
export function dueTime(task: TaskRowOut): WallTime | null {
  return task.due_date && task.due_date.length > DAY_LENGTH ? task.due_date.slice(CLOCK_START, CLOCK_END) : null;
}

const isOpen = (task: TaskRowOut) => task.status === "todo" || task.status === "in_progress";

/** Open and due before today: the calendar sits it on today with a red tint. */
export function isLate(task: TaskRowOut, today: IsoDay): boolean {
  const day = dueDay(task);
  return isOpen(task) && day !== null && day < today;
}

/** How many days past due ("4d"), counted on the calendar alone. */
export function daysLate(task: TaskRowOut, today: IsoDay): number {
  const day = dueDay(task);
  if (day === null) return 0;
  return Math.max(0, Math.round((dayToDate(today).getTime() - dayToDate(day).getTime()) / MS_PER_DAY));
}

const closedLast = (a: TaskRowOut, b: TaskRowOut) => Number(!isOpen(a)) - Number(!isOpen(b));
const byTime = (a: TaskRowOut, b: TaskRowOut) => closedLast(a, b)
  || (dueTime(a) ?? UNTIMED_LAST).localeCompare(dueTime(b) ?? UNTIMED_LAST) || a.title.localeCompare(b.title);

/** The tasks by the visible day they sit on: their due day, or today for a late one when today is shown. Each
 * day's list has the open tasks first (so a full cell shows what is left to do), each part in time order, untimed
 * last. A task due outside the visible days is left out. */
export function placeTasks(tasks: readonly TaskRowOut[], today: IsoDay, visible: readonly IsoDay[]): Map<IsoDay, TaskRowOut[]> {
  const shown = new Set(visible);
  const placed = new Map<IsoDay, TaskRowOut[]>();
  for (const task of tasks) {
    const own = dueDay(task);
    const day = isLate(task, today) && shown.has(today) ? today : own;
    if (day === null || !shown.has(day)) continue;
    placed.set(day, [...(placed.get(day) ?? []), task]);
  }
  return new Map([...placed].map(([day, list]) => [day, [...list].sort(byTime)]));
}

/** Whether the week grid puts the task in an hour slot (its own day, with a time) or in the All day row. */
export const isTimed = (task: TaskRowOut, today: IsoDay): boolean => dueTime(task) !== null && !isLate(task, today);

/** The block's top edge in the week grid, in px, for a time like "09:30" (07:00 is 0). */
export function slotTop(time: WallTime): number {
  const [hour, minute] = time.split(":").map(Number);
  const top = (hour - CAL_FIRST_HOUR + minute / MINUTES_PER_HOUR) * CAL_HOUR_PX;
  return Math.min(Math.max(0, top), CAL_HOURS * CAL_HOUR_PX - SLOT_HEIGHT_PX);
}

/** Tasks that share a time share the width: each block's left and width in percent. */
export function slotShare(index: number, count: number): { left: number; width: number } {
  return { left: (index * 100) / count, width: 100 / count };
}
