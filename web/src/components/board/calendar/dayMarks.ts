// The clean calendar (2026-10-26): what each day cell marks and what a picked day lists, as pure data. A task sits on
// its due day on the account's calendar (a late open one on today, placeTasks); a reminder fires on the account's day of reminder_at and of
// each advance reminder (an instant, or an offset like -30m against reminder_at), for open tasks only; routines come
// grouped per day. The phone app reckons the same way (mobile/lib/workspace/calendar/day_marks.dart).
import { dueTime, isLate } from "./taskPlacement";
import type { ProjectLook } from "./calendarProps";
import type { TaskRowOut } from "../../../api/tasks";
import type { RoutineDayEntry, RoutineDays } from "../../../lib/routineDays";
import { dayText, wallText, type IsoDay, type WallTime } from "../../../ui/date/dates";

export const CELL_MAX_DOTS = 3;
export const CELL_MAX_BOTS = 2;
export const LATE_WORD = "Late";
export const ALL_DAY_WORD = "All day";

const OFFSET = /^-\s*(?:(\d+)\s*d)?\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?$/i;
const MS_PER_MINUTE = 60_000;
const MINUTES_PER_HOUR = 60;
const MINUTES_PER_DAY = 1_440;
const OPEN = new Set(["todo", "in_progress"]);

export interface ReminderFire {
  day: IsoDay;
  time: WallTime;
}

function offsetMinutes(entry: string): number | null {
  const match = OFFSET.exec(entry.trim());
  if (!match) return null;
  const [days, hours, minutes] = [match[1], match[2], match[3]].map((part) => Number(part ?? 0));
  const total = days * MINUTES_PER_DAY + hours * MINUTES_PER_HOUR + minutes;
  return total > 0 ? total : null;
}

function fireInstant(entry: string, base: Date): Date | null {
  const minutes = offsetMinutes(entry);
  if (minutes !== null) return new Date(base.getTime() - minutes * MS_PER_MINUTE);
  const at = new Date(entry);
  return Number.isNaN(at.getTime()) ? null : at;
}

/** The days and times (on the account's clock) an open task's reminder and advance reminders fire, earliest first, once each. */
export function reminderFires(task: TaskRowOut): ReminderFire[] {
  if (!OPEN.has(task.status) || !task.reminder_at) return [];
  const base = new Date(task.reminder_at);
  if (Number.isNaN(base.getTime())) return [];
  const instants = [base, ...(task.pre_reminders ?? []).map((entry) => fireInstant(entry, base))];
  const walls = instants.flatMap((at) => (at ? [wallText(at.toISOString())] : [])).filter(Boolean);
  return [...new Set(walls)].sort().map((wall) => ({ day: wall.slice(0, 10), time: wall.slice(11, 16) }));
}

export interface DayMark {
  tasks: readonly TaskRowOut[]; // as placed: open first, by time
  reminders: number; // tasks whose reminder fires that day
  routines: number;
  botIds: readonly string[]; // the bots behind the day's tasks and routines, at most CELL_MAX_BOTS
}

export interface DayMarksInput {
  placed: ReadonlyMap<IsoDay, readonly TaskRowOut[]>;
  tasks: readonly TaskRowOut[]; // every shown task, for the reminders
  routines: RoutineDays;
}

/** Each day's tasks per day (by reminder day). */
function remindersByDay(tasks: readonly TaskRowOut[]): Map<IsoDay, TaskRowOut[]> {
  const byDay = new Map<IsoDay, TaskRowOut[]>();
  for (const task of tasks) {
    for (const day of new Set(reminderFires(task).map((fire) => fire.day))) {
      byDay.set(day, [...(byDay.get(day) ?? []), task]);
    }
  }
  return byDay;
}

/** What every day with something in it marks: its tasks, reminder and routine counts and its bots. */
export function buildDayMarks({ placed, tasks, routines }: DayMarksInput): ReadonlyMap<IsoDay, DayMark> {
  const reminders = remindersByDay(tasks);
  const days = new Set([...placed.keys(), ...reminders.keys(), ...routines.keys()]);
  return new Map([...days].map((day) => {
    const dayTasks = placed.get(day) ?? [];
    const runs = routines.get(day) ?? [];
    const bots = [...dayTasks.flatMap((task) => (task.created_by_bot ? [task.created_by_bot] : [])), ...runs.map((run) => run.botId)];
    const botIds = [...new Set(bots.filter(Boolean))].slice(0, CELL_MAX_BOTS);
    return [day, { tasks: dayTasks, reminders: reminders.get(day)?.length ?? 0, routines: runs.length, botIds }];
  }));
}

const counted = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** "Thu 22 Oct: 2 tasks, 1 reminder, 1 routine", or the date alone: the cell's words for a screen reader. */
export function cellWords(day: IsoDay, mark: DayMark | undefined): string {
  const name = dayText(day, { weekday: true });
  if (!mark) return name;
  const parts = [
    mark.tasks.length ? counted(mark.tasks.length, "task") : "",
    mark.reminders ? counted(mark.reminders, "reminder") : "",
    mark.routines ? counted(mark.routines, "routine") : "",
  ].filter(Boolean);
  return parts.length ? `${name}: ${parts.join(", ")}` : name;
}

export type DotTone =
  | { kind: "late" | "urgent" | "high" | "plain" | "done" }
  | { kind: "project"; color: string };

/** A task dot's look: late red, then urgent or high, then its project's colour; a done task is a ring. */
export function dotTone(task: TaskRowOut, today: IsoDay, project: ProjectLook | undefined): DotTone {
  if (task.status === "done") return { kind: "done" };
  if (isLate(task, today)) return { kind: "late" };
  if (task.priority === "urgent" || task.priority === "high") return { kind: task.priority };
  return project ? { kind: "project", color: project.color } : { kind: "plain" };
}

export interface PlanTaskRow {
  task: TaskRowOut;
  time: string; // "09:30", "All day" or "Late"
}

export interface PlanReminderRow {
  task: TaskRowOut;
  time: WallTime; // its first fire that day
  more: number; // how many more fire that day
}

export interface DayPlan {
  tasks: readonly PlanTaskRow[];
  reminders: readonly PlanReminderRow[];
  routines: readonly RoutineDayEntry[];
}

const rank = (row: PlanTaskRow) => (row.time === LATE_WORD ? 0 : row.time === ALL_DAY_WORD ? 2 : 1);

/** One picked day as three lists: its tasks (Late first, then by time, All day last), its reminders by time and
 *  its routines. */
export function dayPlan(day: IsoDay, input: DayMarksInput & { today: IsoDay }): DayPlan {
  const tasks = (input.placed.get(day) ?? []).map((task) => ({
    task, time: isLate(task, input.today) ? LATE_WORD : dueTime(task) ?? ALL_DAY_WORD,
  }));
  tasks.sort((a, b) => rank(a) - rank(b) || (rank(a) === 1 ? a.time.localeCompare(b.time) : 0));
  const reminders = input.tasks.flatMap((task) => {
    const fires = reminderFires(task).filter((fire) => fire.day === day);
    return fires.length ? [{ task, time: fires[0].time, more: fires.length - 1 }] : [];
  }).sort((a, b) => a.time.localeCompare(b.time));
  return { tasks, reminders, routines: input.routines.get(day) ?? [] };
}
